# Review prep: Compliance Advisor

Everything you can show the reviewer, what to say about it, and where the code is. Paths are relative to the project root; links jump to the line in VS Code's Markdown preview and on GitHub. The checklist to tick off is at the end.

Checked on 2026-10-30: `uv run pytest -q` gives **108 passed** (the README still says 105), and `npx tsc --noEmit` and `npm run lint` in `frontend/` are clean.

---

## 0. The pitch (30 seconds)

> "A research assistant for compliance officers at banks and insurers supervised in Germany. It answers from 18 official sources (EU regulations, German acts, BaFin circulars), cites the exact provision for every statement, and computes thresholds and deadlines with rule checks written in code, not guessed by the model. Python/FastAPI with LangChain against OpenRouter, Postgres with pgvector, Next.js frontend, everything in Docker."

Domain words to use consistently ([CONTEXT.md](CONTEXT.md)): Source, Passage (= chunk), Provision, Regulatory Layer, Firm Profile, Rule Check (= tool), Answer Model, Pre-Check, Refusal, Search Strategy, Answer Trace.

## 1. Suggested order for the review

1. **Pitch** (section 0) and the architecture diagram in the [README](README.md#how-it-works) (sequence diagram).
2. **Live demo**, following [docs/DEMO.md](docs/DEMO.md): DORA incident question (RAG, tool call, progress, citations), obligations to CSV, the AI Act question, "Which regimes apply to us?", the trust features, two refusals, then the dashboard.
3. **Code walkthrough** of one question from end to end (section 4).
4. **Tool calling** in code (section 5).
5. **Optional tasks**: show 3 or 4 strongly, name the rest (section 3).
6. **Evaluation figures** (section 8) and **weaknesses and improvements** (section 10).

---

## 2. Core requirements (hard requirements H1 to H5)

### H1. RAG implementation

| Aspect | What to say | Where |
|---|---|---|
| Knowledge base for the domain | 18 Sources across 6 Regimes (DORA, AML, payments, insurance, banking, digital), 5,596 Passages; each entry has its layer, language, legal status, version and dated milestones | [config/sources.yaml](config/sources.yaml), model in [registry.py:23](backend/src/compliance_advisor/registry.py#L23) |
| Download from official publishers | robots.txt checked (RFC 9309), honest User-Agent, SHA-256 of every file kept in `meta.json` | [fetch.py:42](backend/src/compliance_advisor/fetch.py#L42) `robots_allows`, [fetch.py:113](backend/src/compliance_advisor/fetch.py#L113) `save_meta` |
| Loaders, one per format | EU XHTML, German gesetze-im-internet XML, BaFin PDF (headings from the table of contents), BaFin web pages | [loaders.py:94](backend/src/compliance_advisor/loaders.py#L94), [:149](backend/src/compliance_advisor/loaders.py#L149), [:221](backend/src/compliance_advisor/loaders.py#L221), [:308](backend/src/compliance_advisor/loaders.py#L308); dispatch [loaders.py:342](backend/src/compliance_advisor/loaders.py#L342) |
| Chunking strategy | **Structure-aware chunking**: one Passage per Provision (article, §, guideline section); long ones split with `RecursiveCharacterTextSplitter` (2,500 characters, 200 overlap), and every part keeps the Provision label as its first line. Number tables are dropped. The naive baseline (1,000 characters / 150 overlap) is kept for comparison | [chunker.py:48](backend/src/compliance_advisor/chunker.py#L48) `chunk_provisions`, label prefix [chunker.py:73](backend/src/compliance_advisor/chunker.py#L73), [chunker.py:42](backend/src/compliance_advisor/chunker.py#L42) `mostly_text`, baseline [chunker.py:34](backend/src/compliance_advisor/chunker.py#L34) |
| Deterministic ids | A hash of source, position and text, so re-runs never duplicate | [chunker.py:18](backend/src/compliance_advisor/chunker.py#L18) |
| Embeddings | `openai/text-embedding-3-small` (1,536 dimensions) via LangChain `OpenAIEmbeddings` against OpenRouter's base URL | [embeddings.py:8](backend/src/compliance_advisor/embeddings.py#L8) |
| Vector DB | Postgres 17 + pgvector through `langchain_postgres.PGVector`; one collection per embedding model and chunker, so indexes never mix | [store.py:28](backend/src/compliance_advisor/store.py#L28), [settings.py:55](backend/src/compliance_advisor/settings.py#L55) |
| Ingest | Embed first, then replace the Source's Passages in one transaction, so a failed API call keeps the old Passages. `--dry-run` works without a key or database | [ingest.py:70-82](backend/src/compliance_advisor/ingest.py#L70), [store.py:64](backend/src/compliance_advisor/store.py#L64) |
| Similarity search | Cosine distance from pgvector, shown as similarity = 1 − distance; top 6 | [retriever.py:105-110](backend/src/compliance_advisor/retriever.py#L105) |
| Structured retrieval | Provisions named in the question ("§ 25a KWG", "Art. 6 AI Act") are extracted with a regex and looked up with a **metadata filter**, and take up to half the slots | [retriever.py:41](backend/src/compliance_advisor/retriever.py#L41) `named_provisions`, [retriever.py:146-149](backend/src/compliance_advisor/retriever.py#L146), [:161](backend/src/compliance_advisor/retriever.py#L161) |

### H2. Tool calling (4 tools, all domain-specific)

| Tool | What it does | Where |
|---|---|---|
| `check_applicability` | Which Regimes apply to the Firm, with the reason and the deciding provision (DORA Art. 2, § 2 GwG, AMLR, § 1 ZAG, Solvency II Art. 4, MaRisk AT 2.1, AI Act) | [tools.py:69](backend/src/compliance_advisor/tools.py#L69) |
| `compliance_timeline` | Dated milestones, past and upcoming, per Regime | [tools.py:350](backend/src/compliance_advisor/tools.py#L350) |
| `classify_dora_incident` | Major incident yes/no/undetermined from the RTS 2024/1772 thresholds, plus reporting deadlines (RTS 2025/301 Art. 5) | [tools.py:449](backend/src/compliance_advisor/tools.py#L449), deadlines [tools.py:546-559](backend/src/compliance_advisor/tools.py#L546) |
| `check_ai_act_use_case` | AI Act risk class (Annex III, Art. 6(3), Art. 50), duties, application dates | [tools.py:627](backend/src/compliance_advisor/tools.py#L627) |
| LangChain wiring | `StructuredTool.from_function` with Pydantic `args_schema`; the descriptions tell the model when to call each tool | [tools.py:757-805](backend/src/compliance_advisor/tools.py#L757) |
| Bound to the request | A tool factory per question injects the Firm Profile and today's date, and links each provision to its indexed text | [rulechecks.py:43](backend/src/compliance_advisor/rulechecks.py#L43), [rulechecks.py:17](backend/src/compliance_advisor/rulechecks.py#L17) |
| The tool loop | See section 5 | [answer.py:144](backend/src/compliance_advisor/answer.py#L144) |

Key line: *"Tools are plain code, not model output. A tool never fills in a missing fact; it returns a `missing` list instead."*

### H3. Domain specialisation

| Aspect | Where |
|---|---|
| Domain prompt: cite every statement with [n], separate binding law from supervisory expectation, "applies later" is not current law, say what is not covered, answer in the question's language, no compliance verdicts | [prompt.py:12-32](backend/src/compliance_advisor/prompt.py#L12) |
| Passages handed over with their layer, issuer, legal status and language | [prompt.py:49](backend/src/compliance_advisor/prompt.py#L49) `format_passages`, labels [prompt.py:34-46](backend/src/compliance_advisor/prompt.py#L34) |
| Question language detected in code and stated to the model | [prompt.py:131](backend/src/compliance_advisor/prompt.py#L131), [prompt.py:139](backend/src/compliance_advisor/prompt.py#L139) |
| Firm Profile with six presets (insurance group, reinsurer, life insurer, significant bank, less significant bank, payment institution) | [profile.py:37](backend/src/compliance_advisor/profile.py#L37), presets [profile.py:58](backend/src/compliance_advisor/profile.py#L58) |
| Coverage line ("Coverage: full/partial/none") parsed and shown above the answer | [answer.py:70-78](backend/src/compliance_advisor/answer.py#L70), [AnswerView.tsx:57](frontend/src/components/AnswerView.tsx#L57) |
| "Not legal advice" notice on every response | [prompt.py:7](backend/src/compliance_advisor/prompt.py#L7), [ADR 0003](docs/adr/0003-regulatory-information-not-legal-advice.md) |
| Domain security measures | Section 6 |

### H4. Technical implementation

| Aspect | Where |
|---|---|
| LangChain + OpenRouter: `ChatOpenAI` with OpenRouter's base URL, `usage.include` for the cost, provider pinning for the EU model | [models.py:36-49](backend/src/compliance_advisor/models.py#L36) |
| LangChain pieces used: `ChatOpenAI`, `OpenAIEmbeddings`, `PGVector`, `RecursiveCharacterTextSplitter`, `StructuredTool`, `bind_tools`, `ToolMessage`, `with_structured_output` (obligations) | [answer.py](backend/src/compliance_advisor/answer.py), [obligations.py:60](backend/src/compliance_advisor/obligations.py#L60) |
| Error handling | Section 7 |
| Input validation: question 3 to 2,000 characters and stripped, `top_k` 1 to 20, `strategy` an enum, Firm Profile with `extra="forbid"`; a clean 422 message | [schemas.py:11-21](backend/src/compliance_advisor/schemas.py#L11), [api.py:306](backend/src/compliance_advisor/api.py#L306) |
| Validation in the browser too: minimum length and `maxLength=2000` | [Composer.tsx:23](frontend/src/components/Composer.tsx#L23), [Composer.tsx:44](frontend/src/components/Composer.tsx#L44) |
| Config files validated (unknown keys stop the command) | [registry.py:23](backend/src/compliance_advisor/registry.py#L23), [models.py:14](backend/src/compliance_advisor/models.py#L14), [limits.py:40](backend/src/compliance_advisor/limits.py#L40) |

### H5. User interface (Next.js 16, React 19, Tailwind 4)

| Aspect | Where |
|---|---|
| Main app, view switch, ask flow | [App.tsx:193](frontend/src/components/App.tsx#L193) `submit` |
| **Context and sources**: numbered passages, the cited ones marked, a click on a citation highlights the passage, a link to the exact article | [PassageList.tsx:29](frontend/src/components/PassageList.tsx#L29), [AnswerView.tsx:13](frontend/src/components/AnswerView.tsx#L13) `linkCitations` |
| Regulatory layer glyph and strip (binding law solid, BaFin practice outlined) | [LayerGlyph.tsx:8](frontend/src/components/LayerGlyph.tsx#L8), [LayerStrip.tsx:6](frontend/src/components/LayerStrip.tsx#L6) |
| **Tool call results** as cards per Rule Check | [ToolCards.tsx:171](frontend/src/components/ToolCards.tsx#L171) (incident [:91](frontend/src/components/ToolCards.tsx#L91), AI Act [:138](frontend/src/components/ToolCards.tsx#L138)) |
| **Progress indicators**: real steps from server-sent events, elapsed seconds, the answer appearing as it is written | [Progress.tsx:35-40](frontend/src/components/Progress.tsx#L35), [api.ts:73](frontend/src/lib/api.ts#L73) `askStream`, backend [api.py:385](backend/src/compliance_advisor/api.py#L385) |
| Why the steps really stream: the `no-transform` header (the Next.js proxy compressed and buffered them) | [api.py:433-434](backend/src/compliance_advisor/api.py#L433) |
| Sources tab with legal status and download date | [Sidebar.tsx:30](frontend/src/components/Sidebar.tsx#L30), [api.py:958](backend/src/compliance_advisor/api.py#L958) |
| Proxy `/api/*` to the backend, 120-second timeout | [next.config.ts](frontend/next.config.ts) |

---

## 3. Optional tasks: status

Bonus needs at least 2 medium and 1 hard; you have far more. **Show 3 or 4 well, name the rest.** Good ones to show: prompt injection (medium), multi-model with cost (medium), RAGAs evaluation (hard), hybrid search measured (hard), MCP server (hard).

### Easy

| Task | Status | Where |
|---|---|---|
| History and export | ✅ History per account or browser, with search; export as Markdown, JSON, PDF (print) | [Sidebar.tsx:13](frontend/src/components/Sidebar.tsx#L13), [api.py:514](backend/src/compliance_advisor/api.py#L514), [api.py:682](backend/src/compliance_advisor/api.py#L682), [audit.py:260](backend/src/compliance_advisor/audit.py#L260), [AnswerView.tsx:115-121](frontend/src/components/AnswerView.tsx#L115) |
| Visualisation of the RAG process | ✅ Answer Trace: pre-check, named lookup, vector/keyword candidates with scores, how each passage was found, tools, model, tokens, cost, seconds | [retriever.py:170-191](backend/src/compliance_advisor/retriever.py#L170), [schemas.py:65](backend/src/compliance_advisor/schemas.py#L65), [AnswerTrace.tsx:12](frontend/src/components/AnswerTrace.tsx#L12) |
| Source citations | ✅ [n] linked to the passage; invalid numbers are dropped | [answer.py:37](backend/src/compliance_advisor/answer.py#L37) `cited_numbers` |
| Interactive help / guide | ⚠️ Partial only: example questions on the start screen, a note per model and Search Strategy, refusals with the reason. No dedicated help feature | [App.tsx:399](frontend/src/components/App.tsx#L399), [i18n.ts](frontend/src/lib/i18n.ts) |

### Medium

| Task | Status | Where |
|---|---|---|
| Multi-model support | ✅ GPT-6 Luna (default), Mistral Large 4 pinned to Mistral's EU servers, Claude Sonnet 5.5 | [config/models.yaml](config/models.yaml), [models.py:36](backend/src/compliance_advisor/models.py#L36), [Composer.tsx:57](frontend/src/components/Composer.tsx#L57) |
| Real-time data updates | ✅ "Check now" for operators starts an Update Run | [api.py:636](backend/src/compliance_advisor/api.py#L636), [update.py:305](backend/src/compliance_advisor/update.py#L305) |
| Prompt injection protection | ✅ Pre-Check screening plus "data, not instructions" in the prompt; measured | Section 6 |
| Authentication and personalisation | ✅ Accounts (scrypt, httpOnly session cookie), saved Firm Profile, private answers, dashboard | [accounts.py:70](backend/src/compliance_advisor/accounts.py#L70), [api.py:709-755](backend/src/compliance_advisor/api.py#L709), [ADR 0005](docs/adr/0005-optional-accounts-private-answers.md) |
| Token usage and cost | ✅ Per answer, reported by OpenRouter, or computed from list prices for streamed replies | [answer.py:52](backend/src/compliance_advisor/answer.py#L52), [models.py:55](backend/src/compliance_advisor/models.py#L55), [AnswerView.tsx:110](frontend/src/components/AnswerView.tsx#L110) |
| Visualisation of tool results | ✅ Rule Check cards | [ToolCards.tsx](frontend/src/components/ToolCards.tsx) |
| Export in several formats | ✅ Markdown, JSON, PDF (answer); CSV for Excel (obligations) | [api.py:682](backend/src/compliance_advisor/api.py#L682), [csv.ts](frontend/src/lib/csv.ts), [Obligations.tsx:33](frontend/src/components/Obligations.tsx#L33) |
| Tools from a public remote MCP server | ❌ Not done (the app *serves* MCP; it does not consume one) | listed as "after the submission" in [ROADMAP.md](docs/ROADMAP.md) |
| Rate limiting and API keys | ✅ Guest 10/h per signed browser cookie, account 30/h and 200/day, registrations and logins limited, $5 daily cost ceiling; keys hashed, may only ask and run Rule Checks | [limits.py:55](backend/src/compliance_advisor/limits.py#L55), [config/limits.yaml](config/limits.yaml), [api.py:241](backend/src/compliance_advisor/api.py#L241), [apikeys.py:41](backend/src/compliance_advisor/apikeys.py#L41), [KeysSection.tsx](frontend/src/components/KeysSection.tsx) |
| Logging and monitoring | ✅ JSON logs with counts only; operator page with figures across all accounts, never question texts | [monitoring.py:35](backend/src/compliance_advisor/monitoring.py#L35), [monitoring.py:110](backend/src/compliance_advisor/monitoring.py#L110), [OperatorSection.tsx](frontend/src/components/OperatorSection.tsx), [ADR 0006](docs/adr/0006-operator-sees-figures-not-questions.md) |

### Hard

| Task | Status | Where |
|---|---|---|
| Hybrid search | ✅ Postgres full-text search (German and English stemming, generated `tsvector` column) merged with vector search by reciprocal rank fusion; **measured, lost, kept as an option** | [store.py:17](backend/src/compliance_advisor/store.py#L17), [retriever.py:17](backend/src/compliance_advisor/retriever.py#L17), [retriever.py:63](backend/src/compliance_advisor/retriever.py#L63) `merge_ranked` |
| A/B testing of RAG strategies | ⚠️ Offline: 8 retrieval set-ups compared on the Golden Set with a tuning and a held-out half; the Search Strategy is chosen per question and recorded, and the operator page splits cost by strategy. No live random user split | [evaluation.py:1-19](backend/src/compliance_advisor/evaluation.py#L1), [evaluation.py:65](backend/src/compliance_advisor/evaluation.py#L65) `half_of` |
| Automated knowledge-base updates | ✅ Nightly scheduler (`UPDATE_RUNS=true`, off by default); only Sources whose text changed are re-embedded; Change Records; "your sources have changed" on the dashboard | [update.py:373](backend/src/compliance_advisor/update.py#L373), [update.py:231](backend/src/compliance_advisor/update.py#L231), [api.py:991](backend/src/compliance_advisor/api.py#L991), [api.py:645](backend/src/compliance_advisor/api.py#L645) |
| Multi-language support | ✅ German and English interface; answers in the question's language; Sources in German and English (cross-lingual through the embeddings) | [i18n.ts:580](frontend/src/lib/i18n.ts#L580), [Header.tsx:98](frontend/src/components/Header.tsx#L98), [prompt.py:131](backend/src/compliance_advisor/prompt.py#L131), [ADR 0002](docs/adr/0002-sources-kept-in-official-language.md) |
| Advanced analytics dashboard | ✅ Period switch, questions per day, regimes, most-cited provisions, **blind spots**, click-through to the questions | [analytics.py:57](backend/src/compliance_advisor/analytics.py#L57), [analytics.py:75](backend/src/compliance_advisor/analytics.py#L75), [api.py:849](backend/src/compliance_advisor/api.py#L849), [Dashboard.tsx:27](frontend/src/components/Dashboard.tsx#L27), [Charts.tsx](frontend/src/components/Charts.tsx) |
| Tools as MCP servers | ✅ The 4 Rule Checks plus `search_corpus` at `/mcp` (streamable HTTP), API key required, rate-limited, questions redacted | [mcp_server.py:64](backend/src/compliance_advisor/mcp_server.py#L64), auth [mcp_server.py:38](backend/src/compliance_advisor/mcp_server.py#L38), mount [api.py:114-120](backend/src/compliance_advisor/api.py#L114) |
| RAG evaluation (RAGAs) | ✅ Own retrieval metrics (hit@6, recall@6, MRR) on 214 questions, and RAGAs faithfulness and factual correctness with a grader from another model family, under a cost cap | [evaluation.py:119](backend/src/compliance_advisor/evaluation.py#L119), [ragas_eval.py:29-30](backend/src/compliance_advisor/ragas_eval.py#L29), [docs/EVALUATION.md](docs/EVALUATION.md) |

Also built beyond the list: obligation extraction ([obligations.py:50](backend/src/compliance_advisor/obligations.py#L50), [api.py:439](backend/src/compliance_advisor/api.py#L439)), timeline view ([TimelinePanel.tsx](frontend/src/components/TimelinePanel.tsx), [api.py:477](backend/src/compliance_advisor/api.py#L477)), audit trail with source versions ([audit.py:47](backend/src/compliance_advisor/audit.py#L47), [audit.py:93](backend/src/compliance_advisor/audit.py#L93)), dark mode, phone layout, 7 ADRs.

---

## 4. One question from end to end (the core-concept walkthrough)

Open these in order and narrate:

1. **Endpoint**: `POST /api/ask/stream`, rate limit first, then the work runs in a thread that puts events in a queue → [api.py:385-435](backend/src/compliance_advisor/api.py#L385)
2. **Orchestration**: [answer.py:178](backend/src/compliance_advisor/answer.py#L178) `AnswerService.ask`
3. **Pre-Check**: redact IBAN, email, phone → [precheck.py:23](backend/src/compliance_advisor/precheck.py#L23); screening call → [precheck.py:57](backend/src/compliance_advisor/precheck.py#L57); refusal returned early → [answer.py:196-218](backend/src/compliance_advisor/answer.py#L196)
4. **Retrieval**: [retriever.py:139](backend/src/compliance_advisor/retriever.py#L139) `search`: embed once (145), named provisions by metadata filter (146-149), vector top-k (152), optional hybrid with RRF (154-159), merge (161-164), trace (170)
5. **Prompt**: [prompt.py:139](backend/src/compliance_advisor/prompt.py#L139): system rules + Firm Profile + passages as `<passage n=… provision=… layer=… status=…>` + `<question>`
6. **Tool round**: [answer.py:144](backend/src/compliance_advisor/answer.py#L144) (section 5)
7. **Streaming**: [answer.py:127](backend/src/compliance_advisor/answer.py#L127) `_call` passes each token on as a `delta` event; the browser parses SSE in [api.ts:100-113](frontend/src/lib/api.ts#L100) and updates state in [App.tsx:207-228](frontend/src/components/App.tsx#L207)
8. **Post-processing**: coverage line split off ([answer.py:73](backend/src/compliance_advisor/answer.py#L73)), citations validated ([answer.py:37](backend/src/compliance_advisor/answer.py#L37)), tokens and cost ([answer.py:52](backend/src/compliance_advisor/answer.py#L52)), log line with counts only ([answer.py:283](backend/src/compliance_advisor/answer.py#L283))
9. **Audit trail**: stored with passages and source versions → [audit.py:93](backend/src/compliance_advisor/audit.py#L93), [api.py:344](backend/src/compliance_advisor/api.py#L344)

## 5. Tool calling, explained

In [answer.py:144-176](backend/src/compliance_advisor/answer.py#L144):

1. The tools for this request are built with the Firm Profile bound in (line 147).
2. `model.bind_tools(tools)` → first call (line 152). If the reply has no `tool_calls`, it *is* the answer.
3. Otherwise each call (at most `MAX_TOOL_CALLS = 4`, [line 26](backend/src/compliance_advisor/answer.py#L26)) is executed **in Python**, and the JSON result goes back as a `ToolMessage` with the matching `tool_call_id` (lines 159-170).
4. Invalid arguments become an error JSON for the model, not a crash (lines 165-166). An unknown tool name gets `{"error": "unknown tool"}`.
5. The second call uses `tool_choice="none"` (line 175), so there are **at most two model calls** per question: bounded cost and latency.
6. The prompt tells the model to cite tool results as "(rule check: name)", never with a passage number ([prompt.py:26-30](backend/src/compliance_advisor/prompt.py#L26)).

Why one round and not an agent loop: it is predictable, cheap and testable, and the four checks are independent. An agentic loop is on the roadmap as a *measured* alternative.

## 6. Security measures (domain-relevant)

| Measure | Where | Limit to admit |
|---|---|---|
| Personal data removed before anything leaves the app (IBAN, email, phone) | [precheck.py:13-30](backend/src/compliance_advisor/precheck.py#L13) | Names are not detected |
| Screening against manipulation and off-topic questions, with the reason shown | [precheck.py:35-83](backend/src/compliance_advisor/precheck.py#L35), [ADR 0007](docs/adr/0007-pre-check-screens-every-question.md) | **Fails open**: if the screening call fails, the question passes (logged) |
| EU-hosted model screens its own questions (data never goes to another provider) | [api.py:102](backend/src/compliance_advisor/api.py#L102) `screeners` | |
| Passages and question marked as data, not instructions; XML-like delimiters | [prompt.py:22](backend/src/compliance_advisor/prompt.py#L22), [prompt.py:57](backend/src/compliance_advisor/prompt.py#L57), [precheck.py:64](backend/src/compliance_advisor/precheck.py#L64) | A prompt convention, not a hard boundary |
| Citations checked against the given passages | [answer.py:37](backend/src/compliance_advisor/answer.py#L37) | A valid citation can still support a statement poorly (RAGAs measures that) |
| Rule Checks in code, not model guesses; missing facts listed | [tools.py:1-6](backend/src/compliance_advisor/tools.py#L1) | |
| Passwords as salted scrypt; session tokens and API keys stored only as hashes; httpOnly SameSite cookie | [accounts.py:70](backend/src/compliance_advisor/accounts.py#L70), [accounts.py:87](backend/src/compliance_advisor/accounts.py#L87), [apikeys.py:41](backend/src/compliance_advisor/apikeys.py#L41), [api.py:709-719](backend/src/compliance_advisor/api.py#L709) | No email verification or password reset |
| API keys may only ask and run Rule Checks (403 elsewhere) | [api.py:223](backend/src/compliance_advisor/api.py#L223) `session_user` | |
| Answers private: someone else's answer gives 404, not 403 | [api.py:535](backend/src/compliance_advisor/api.py#L535) `_owns` | |
| Rate limits and daily cost ceiling | [api.py:241](backend/src/compliance_advisor/api.py#L241), [limits.py:55](backend/src/compliance_advisor/limits.py#L55) | Counters live in memory (one backend) |
| Guest cookie signed with HMAC; `x-forwarded-for` trusted only when configured | [limits.py:93-141](backend/src/compliance_advisor/limits.py#L93) | Clearing cookies gives a fresh quota (address bucket and cost ceiling are the backstop) |
| Operators see figures, never question texts; logs carry counts only | [ADR 0006](docs/adr/0006-operator-sees-figures-not-questions.md), [answer.py:283-295](backend/src/compliance_advisor/answer.py#L283) | |
| 500s never show the exception text | [api.py:326](backend/src/compliance_advisor/api.py#L326) | |
| Public sources only, no uploads | [ADR 0004](docs/adr/0004-public-sources-only-no-firm-documents.md) | |

**Measured** with [config/precheck_set.yaml](config/precheck_set.yaml) via [precheck_eval.py](backend/src/compliance_advisor/precheck_eval.py): 30 of 30 attacks refused (18 manipulation, 12 off-topic), 0 of 30 tricky legitimate questions and 0 of 214 Golden Set questions wrongly refused.

## 7. Error handling and edge cases

| Scenario | Behaviour | Where |
|---|---|---|
| Invalid input | 422 with a readable message | [api.py:306-317](backend/src/compliance_advisor/api.py#L306) |
| OpenRouter down (embedding or model) | `UpstreamError` → 502 | [answer.py:227-230](backend/src/compliance_advisor/answer.py#L227), [answer.py:246-247](backend/src/compliance_advisor/answer.py#L246), [api.py:320](backend/src/compliance_advisor/api.py#L320) |
| Database down | `DatabaseError` → 503, counted in memory (the DB cannot record it) | [api.py:188](backend/src/compliance_advisor/api.py#L188), [api.py:335](backend/src/compliance_advisor/api.py#L335) |
| Error during streaming | An `error` event with a status, never a hanging stream (`finally` closes it) | [api.py:409-422](backend/src/compliance_advisor/api.py#L409) |
| Missing API key | Clear message instead of a crash | [settings.py:75](backend/src/compliance_advisor/settings.py#L75), [api.py:277](backend/src/compliance_advisor/api.py#L277) |
| Model passes bad tool arguments / too many calls | Error JSON back to the model | [answer.py:159-174](backend/src/compliance_advisor/answer.py#L159) |
| Model cites [9] with only 6 passages | Ignored | [answer.py:47](backend/src/compliance_advisor/answer.py#L47) |
| Screening model fails | Question passes, warning logged | [precheck.py:66-70](backend/src/compliance_advisor/precheck.py#L66) |
| Answer could not be stored | Answer still returned, warning logged | [api.py:361-363](backend/src/compliance_advisor/api.py#L361) |
| Rate limit / cost ceiling | 429 with `Retry-After` and `X-Limit`; the page shows the time | [api.py:241-269](backend/src/compliance_advisor/api.py#L241), [App.tsx:231-239](frontend/src/components/App.tsx#L231) |
| "Check now" pressed twice | Process lock → 409 | [update.py:206](backend/src/compliance_advisor/update.py#L206) |
| Update fails halfway | Old Passages kept, run row always finished | [update.py:305-362](backend/src/compliance_advisor/update.py#L305) |
| Incident question without key facts | Rule Check says "undetermined" and lists the missing facts | [tools.py:522-533](backend/src/compliance_advisor/tools.py#L522) |
| Question outside the Corpus but on regulation | Not refused; a coverage notice instead | [AnswerView.tsx:57](frontend/src/components/AnswerView.tsx#L57) |
| Session expired | The frontend signs out on a 401 | [api.ts:16](frontend/src/lib/api.ts#L16) |

**Tests**: 108 in [backend/tests/](backend/tests/), no network and no database (models and embeddings mocked). Largest: [test_answering.py](backend/tests/test_answering.py) (17), [test_tools.py](backend/tests/test_tools.py) (11), [test_limits_and_keys.py](backend/tests/test_limits_and_keys.py) (10), [test_audit_and_stream.py](backend/tests/test_audit_and_stream.py) (10).

## 8. Figures to know by heart

| What | Figure |
|---|---|
| Corpus | 18 Sources, 6 Regimes, 5,596 Passages; ingest takes about 3 minutes and costs about 6 cents |
| Retrieval, vector (the app), 214 questions | hit@6 **0.85**, recall@6 0.69, MRR 0.67 |
| Naive baseline vs per provision (100 seed questions) | hit@6 0.82 → 0.87 |
| Hybrid search | 0.79 (full weight), 0.81 (half weight); held-out half 0.81 vs 0.83 for vector → vector stays the default |
| Cross-lingual (German question, English EU act) | 0.73 vs 0.93 same-language: **the weakest kind** |
| RAGAs, 50 questions, grader Gemma 4 31B | faithfulness **0.96**, factual correctness **0.51** |
| Mistral Large 4 vs Luna (20 questions) | faithfulness 0.90 vs 0.96; about $0.02 per answer, 20 times Luna's |
| Pre-Check | 30/30 attacks refused, 0/30 + 0/214 legitimate questions refused |
| Golden Set | 214 questions (131 DE, 83 EN), 37 from official Q&As; status *draft* (not yet reviewed by a compliance professional) |
| Per answer (Luna) | about 10 to 30 seconds, well under 1 cent |

Sources: [docs/EVALUATION.md](docs/EVALUATION.md), [evaluation/results.jsonl](evaluation/results.jsonl).

---

## 9. Questions the reviewer may ask

**"Where is query translation?"** The task's intro mentions it. What exists: the named-provision lookup (the question is turned into a metadata filter, a form of query structuring) and code-side language detection. There is **no LLM rewriting** of the question (multi-query, HyDE, step-back). The evaluation shows exactly where it would pay off: cross-lingual questions (0.73). Next step: translate the question into the Source's language and merge the results, then measure it like hybrid search.

**"Can I ask a follow-up?"** No, each question is answered on its own (single-turn); [prompt.py:139](backend/src/compliance_advisor/prompt.py#L139) sends no earlier turns. Why: every answer is an audit-trail record that stands alone with its sources. How to add it: condense the follow-up and the last turn into a standalone question before retrieval (also a form of query translation), and keep the audit record per turn.

**"Why chunk per provision?"** A citation must point to a provision; a fixed-size chunk cuts through articles. It was measured: hit@6 0.82 → 0.87 on the seed questions.

**"Why is hybrid search not the default?"** It lost on both halves of the Golden Set: keyword search brings in German texts for German questions about English acts, and recitals that repeat the act's name. The variant was chosen on one half and confirmed on the other, so it was not tuned to these very questions.

**"How do you know the model does not hallucinate?"** Citations are checked, the prompt says to report what is not covered, and RAGAs faithfulness is 0.96. Thresholds and deadlines come from code, not from the model.

**"Why pgvector and not Chroma/FAISS?"** One database for vectors, accounts, the audit trail and keyword search (`tsvector`); transactions for replacing a Source's Passages; it runs in the same Docker setup.

**"What happens if OpenRouter is down?"** 502 with a message; the steps stop with an error event; the operator page counts the failures.

**"How does the MCP server work?"** Show [mcp_server.py](backend/src/compliance_advisor/mcp_server.py) and call it with the command in section 11.

**"How is cost controlled?"** At most 2 model calls per question, a cheap default model, a daily cost ceiling, rate limits, and a cost cap on every eval run.

**"What would you do differently?"** Section 10.

## 10. Weaknesses and improvements (reflection criterion)

| Weakness | Improvement |
|---|---|
| Cross-lingual retrieval is the weakest kind (0.73) | Query translation into the Source's language, measured on the Golden Set |
| Factual correctness 0.51: mostly the search missing the right provision (the answers say so) | Query translation, re-ranking with a cross-encoder, a better Golden Set |
| Single-turn, no follow-up questions | Condense a follow-up into a standalone question |
| Golden Set is a draft, not reviewed by a professional | Review by a compliance professional |
| Screening fails open; the test set holds only attacks its author thought of | Add every new attack to `precheck_set.yaml`; consider failing closed for API keys |
| Names and case facts are not redacted | NER-based redaction (for example Presidio) |
| Rate-limit counters in memory, one backend only | Redis for several backends |
| No email verification or password reset | Add both, or an identity provider (Entra ID) |
| `api.py` is one file of about 1,000 lines; `Dashboard.tsx` about 700 | Split into FastAPI routers and smaller components |
| The DORA deadline highlight in `ToolCards.tsx` matches the backend's English sentence | Return the deadline as a structured field |
| Rule Check details are English in the German interface | Structured results with translated labels |
| No consumption of an external MCP server; no live A/B split | Roadmap "after the submission" |

---

## 11. Before the review

```bash
docker compose up -d --build                                   # postgres, backend, frontend
curl -s http://localhost:8010/api/health                       # backend and database ok?
cd backend && uv run pytest -q                                 # 108 passed
cd ../frontend && npx tsc --noEmit && npm run lint             # clean
```

MCP call to show (create a key under Dashboard → Konto → API-Schlüssel first):

```bash
curl -s -X POST http://localhost:8010/mcp/ \
  -H "Authorization: Bearer ca_..." \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

Test this command once before the review: it uses the same request shape as [test_mcp.py](backend/tests/test_mcp.py), but has not been run against the live app today.

---

## 12. Checklist

### Setup (the day before)
- [ ] `docker compose up -d --build` runs; http://localhost:3010 opens
- [ ] `/api/health` reports the database as reachable
- [ ] The Sources tab shows all 18 Sources with passage counts (index populated)
- [ ] Enough OpenRouter credit (about $2 were left on 2026-10-28)
- [ ] An account with a saved Firm Profile and a few questions; operator role granted (`uv run compliance-advisor-accounts operator grant <email>`)
- [ ] A private window ready for the guest flow
- [ ] The DEMO.md questions in a text file to paste
- [ ] An API key created and the MCP curl command tested
- [ ] One warm-up question asked, so the first live answer is not slow
- [ ] `uv run pytest -q` → 108 passed
- [ ] Fix the README test count ([README.md:233](README.md#L233) says 105, is 108)
- [ ] Decide what to do with the test account `ops-verify@example.org`

### Core requirements I can show and explain
- [ ] H1 knowledge base: sources.yaml, loaders, official publishers, robots.txt
- [ ] H1 chunking per provision, and why (measured against the naive baseline)
- [ ] H1 embeddings and pgvector; cosine similarity; top 6
- [ ] H1 named-provision lookup (structured retrieval)
- [ ] H2 the four Rule Checks and what each one computes
- [ ] H2 the tool loop in `answer.py` (bind_tools → ToolMessage → tool_choice none)
- [ ] H3 the domain prompt and its rules
- [ ] H3 Firm Profile and presets
- [ ] H3 domain security measures
- [ ] H4 LangChain with OpenRouter (`ChatOpenAI`/`OpenAIEmbeddings` with base_url)
- [ ] H4 error handling (502/503/422/429/500, stream error events)
- [ ] H4 input validation (backend schema and frontend)
- [ ] H5 citations → highlighted passage → official text
- [ ] H5 Rule Check cards
- [ ] H5 live progress steps and streamed answer (SSE, `no-transform`)

### Optional tasks to show (pick 3 or 4)
- [ ] Prompt injection: Lasagne question and "ignore all previous instructions", with the measured figures
- [ ] Multi-model with tokens and cost per answer; the EU-hosted model
- [ ] Answer Trace (RAG visualisation)
- [ ] History and export (Markdown, JSON, PDF), obligations as CSV
- [ ] Accounts, dashboard, blind spots, most-cited provisions
- [ ] Rate limits and API keys
- [ ] Operator page and JSON logs
- [ ] Update Runs and "your sources have changed"
- [ ] MCP server called with an API key
- [ ] Hybrid search, and why it is not the default
- [ ] RAGAs evaluation and EVALUATION.md
- [ ] German/English switch

### Concepts I can explain without notes
- [ ] The RAG flow end to end (section 4)
- [ ] How tool calling works, and why one round
- [ ] Reciprocal rank fusion
- [ ] hit@6, recall@6, MRR; faithfulness vs factual correctness
- [ ] Why the grader is from another model family
- [ ] Tuning half vs held-out half
- [ ] Why the screening fails open
- [ ] Why operators never see question texts

### Questions I have an answer ready for
- [ ] Where is query translation?
- [ ] Can I ask a follow-up?
- [ ] Why pgvector?
- [ ] How do you prevent hallucination?
- [ ] What if OpenRouter or the database is down?
- [ ] How is cost controlled?

### Reflection
- [ ] Three weaknesses with their improvements (cross-lingual, single-turn, Golden Set draft)
- [ ] Optional tasks not done: external MCP client, live A/B, dedicated help feature
- [ ] Code organisation I would change (`api.py` routers, `Dashboard.tsx`)
