# Roadmap

The Compliance Advisor is built step by step, one or more sessions per step, and every step leaves a working app. Status values: `todo`, `in progress`, `done`.

`hard_requirements.txt` (H1 to H5) and `soft_requirements.txt` (A easy, B medium, C hard) are the bootcamp's requirements. Each step lists what it delivers against them, so nothing is forgotten.

## Working agreements

- Build only the current step. Later ideas go into this file, not into the code.
- Ask before downloading any Source; the registry entry is agreed first.
- Say explicitly when a config file such as `.env.example` or `.env` is created, so it can be filled in.
- No code, docs or wording are reused from other projects. This project stands on its own.
- Firm presets describe firm types, never real companies.
- Every change is measurable: the naive index of the six seed Sources stays as the baseline.
- Terms live in `CONTEXT.md`; hard-to-reverse decisions in `docs/adr/`; the handoff note for the next session in `last_session.md`.

## Step 1: Naive RAG (done 2026-10-21)

Built in three sub-steps with a check-in after each.

### 1a. Sources in (done 2026-10-21: 2,175 Passages from six Sources)

- Backend scaffold: uv project, Python 3.12, package `compliance_advisor` under `backend/src/`, FastAPI, LangChain.
- `config/sources.yaml` with the six seed Sources listed in the README. Fields: `id`, `title`, `short_title`, `regime` (dora, aml, payments), `layer` (eu_level_1, eu_level_2, eu_level_3, national_law, supervisory_practice), `issuer`, `language` (en, de), `format` (html, gii_xml, pdf), `url`, `display_url`, `notes`. Unknown values stop the command with a clear message.
- Added during the build: `display_url`, the page a person opens to read the Source. EU acts are downloaded from the EU Publications Office, because EUR-Lex answers scripts with an empty challenge page; citations still link to EUR-Lex.
- `compliance-advisor-fetch [--source <id>] [--refresh]`: downloads into `data/raw/<id>/`, skips files already there, sends an honest User-Agent, checks robots.txt and stops if a site disallows automated access. Every download is confirmed first.
- Loaders, one function per format: `html` for EU acts as XHTML from the EU Publications Office, `gii_xml` for the gesetze-im-internet zip with one XML file, `pdf` for BaFin documents via pypdf. Each returns plain text plus the Source's metadata.
- Chunker: `RecursiveCharacterTextSplitter`, 1000 characters with 150 overlap, both settings with defaults.
- Embeddings: `openai/text-embedding-3-small` via OpenRouter, using `langchain-openai`'s `OpenAIEmbeddings` with OpenRouter's base URL. 1536 dimensions.
- Store: Postgres with pgvector through LangChain's `PGVector`, one collection named after the embedding model id.
- `compliance-advisor-ingest [--source <id>] [--dry-run] [--rebuild]`: rebuilds a Source's Passages (delete by source id, then insert). Passage ids are content hashes of source id, position and text. `--dry-run` cuts and counts without touching OpenRouter or the database.
- Postgres container via compose: project name `compliance_advisor`, host port 5433, user, password and database `advisor`.
- Backend modules, one per stage: `settings.py`, `registry.py`, `fetch.py`, `loaders.py`, `chunker.py`, `embeddings.py`, `store.py`, `ingest.py`, `retriever.py`, `prompt.py`, `answer.py`, `api.py`, `schemas.py`.

### 1b. Questions answered (done 2026-10-21: three test questions answered, 12 tests pass)

- `POST /api/ask` with `{question, top_k?}`: validate (3 to 2000 characters, otherwise 422), embed the question, top-6 cosine similarity search with scores, build the prompt, call `openai/gpt-6-luna` through `ChatOpenAI` with OpenRouter's base URL, return the agreed response shape (see `last_session.md` until it lives in `schemas.py`).
- `GET /api/health` (alive, database reachable) and `GET /api/sources` (what the Corpus holds).
- Synchronous JSON, single-turn. Streaming and history come with step 2.
- Prompt: the agreed professional prompt in `prompt.py`. No disclaimer inside the answer text; the `disclaimer` field travels with every response.
- Errors: 502 when the Answer Model fails, 503 when the database is unreachable; the page shows the message. One log line per question with duration, Passage ids, model and token counts.
- About ten unit tests without network or database: loaders on fixtures, Passage id determinism, prompt formatting, API validation with model and embeddings mocked.
- Added during the build: each Passage in the response also carries `passage_id` and `issuer`.

### 1c. Page and containers (done 2026-10-21)

- Next.js 16 with TypeScript, App Router, Tailwind and ESLint; `/api/*` forwarded to the backend by a rewrite rule; react-markdown for the answer.
- One page: question box, Ask button, spinner, the answer, the six Passages with the cited ones marked, an error line, the permanent notice below the chat, the list of Sources in the Corpus.
- Backend and frontend Dockerfiles; compose with exactly three containers; host ports 5433 (Postgres), 8010 (backend), 3010 (frontend).
- Development loop: backend and frontend run locally against the Postgres container; `docker compose up --build` for full runs.
- Added during the build: the Next.js proxy timeout is raised to 120 seconds, because answers take up to 30 seconds and the default limit is 30; citations such as "[1, Art. 32 Abs. 1]" are counted as citing Passage 1; the language rule in the prompt names German acts explicitly, because an English question mentioning the GwG got a German answer.

### Settings

`.env`: `OPENROUTER_API_KEY`, `DATABASE_URL`, `EMBEDDING_MODEL`, `TOP_K`, `CHUNK_SIZE`, `CHUNK_OVERLAP` (the Answer Models moved to `config/models.yaml` on day 3).

### Done when (all four met on 2026-10-21)

1. Fetch and ingest run on all six Sources without errors, and `--dry-run` shows sensible Passage counts.
2. Three questions get sensible cited answers: English on DORA incident reporting, German on GwG due diligence, and one outside the Corpus that shows the "not covered" behaviour.
3. The tests pass.
4. `docker compose up --build` brings up all three containers and the page answers.

Delivers: H1 in full (knowledge base, embeddings, chunking, similarity search); H3 partly (domain, focused knowledge base, domain prompt); H4 (LangChain with OpenRouter, error handling, input validation); H5 partly (Next.js, sources shown, progress indicator); A source citations; C multi-language partly (German and English Sources, answer in the question's language).

## The end product (decided 2026-10-22)

Audience: the Compliance Officer researching a question, and the Compliance Function as a team on top. Target firms: large banks and insurers supervised in Germany, with smaller firms still possible (ADR 0001 unchanged). Interface in German, with English available.

Jobs the end product supports: research with Citations; an obligation inventory; horizon scanning; case support through tools. Not supported: gap analysis against a Firm's own documents, because nothing is uploaded (ADR 0004).

Regimes: DORA, anti-money laundering and payments (seed); insurance (Solvency II, VAG, IDD, MaGo); banking (CRR, CRD, KWG, MaRisk); digital (AI Act, GDPR). Sustainability (SFDR, taxonomy, CSRD) comes later.

Trust must-haves: links to the exact provision, legal status and "as of" dates, an audit trail with export, "not covered" visible in the interface.

## Submission plan: five days, due 2026-10-27

### Day 1: Sources and Passages (done 2026-10-22: 18 Sources, 6,415 Passages, 19 tests)

- Passages per article or paragraph with a provision label such as "Art. 17 DORA" or "§ 10 GwG" and a deep link: EU acts via the article anchors (`#art_17`), German acts via per-paragraph pages (`__10.html`), PDFs via `#page=N`. Overlong provisions are split and keep their label.
- The naive fixed-size index of the six seed Sources stays as the baseline collection; new Sources are indexed per article only.
- Registry fields `legal_status` and dated milestones, entered by hand and checked against the official text.
- About twelve new Sources, each URL confirmed before download: Solvency II Directive, Delegated Regulation 2015/35, VAG, IDD, MaGo; CRR, CRD, KWG, MaRisk; AI Act, GDPR; the DORA standard on incident report deadlines. EU texts in their latest consolidated version. Large texts can be trimmed to listed articles or titles if they crowd out other Sources.
- After each Regime's ingest: five probe questions, showing which Sources the Passages came from.
- Added during the build: at most three Passages per Source when others qualify (fills up otherwise); direct lookup of Provisions named in the question; the question's language is detected in code and stated to the model; citations must carry their number next to the Provision; PDF headings follow the table of contents; BaFin web pages are a fourth format (MaGo has no PDF).
- Not trimmed: the probes showed no crowding by the CRR or Delegated Regulation 2015/35.
- Known gaps for later: a German question does not reach the English AI Act text; the DORA classification standard's Art. 8 and the CRD's Art. 74 rank below the top six for general wordings.

### Day 2: Tools and Firm Profile (done 2026-10-22: four Rule Checks, six presets, pre-check, 30 tests)

- Four rule-check tools written in code: applicability check, compliance timeline, DORA incident classifier, AI Act use-case check. Each result names the provision that decides it.
- One tool round: the model may call tools once, then answers (at most two model calls).
- Firm Profile: firm type, size class, activities; kept in the browser; presets by firm type only.
- Question pre-check: removes IBANs, email addresses and phone numbers before anything leaves the app, and says so.
- Delivers H2 in full.
- Added during the build: every rule was read from the Sources' own text first (DORA Art. 2, RTS 2024/1772 Art. 1-9, RTS 2025/301 Art. 5, § 2 GwG, AMLR Art. 2-3, § 1 ZAG, Solvency II Art. 4, MaRisk AT 2.1, AI Act Art. 4, 6, 26, 27, 50, Annex III). Tool results link to the indexed Provision. The bare page got a preset choice, rule-check cards and the pre-check notice, to try the day before the design.
- Seen in live tests: the model passes only stated facts, so an incident question that does not say whether critical services were affected gets "undetermined" and a list of missing facts. Names are not removed by the pre-check (agreed scope: IBAN, email, phone).

### Day 3: Design and frontend (done 2026-10-22: designed interface DE/EN, audit trail, 37 tests)

- The design from `docs/DESIGN-BRIEF.md`; German and English interface.
- Trust elements, tool results, history list, export (JSON, Markdown, PDF via print), cost per answer in money, model choice including an EU-hosted model.
- Audit trail: every answer stored with its Passages and Source versions.
- Delivers H5 in full; A history and export; B token usage and costs; B visualisation of tool results; B multi-model support.
- Added during the build: the layout was built directly from the brief (no separate design tool); signature element is the Regulatory Layer glyph and strip. Real progress steps via server-sent events (`/api/ask/stream`). A closing "Coverage:" line from the model drives the coverage note. `config/models.yaml` lists the models; Mistral is pinned to its EU servers. Number tables are no longer indexed (Delegated Regulation 2015/35 dropped from 1,453 to 634 Passages). `.env.example` was restored; an earlier commit had recorded its deletion.
- Not built: a separate form for the incident classifier (left open). Rule-check details (reasons, deadlines) are generated in English also in the German interface; the labels around them are translated.
- Seen in tests: Mistral answers take about 60 seconds and cost about 2.5 cents; GPT-6 Luna about 15 seconds and 0.15 cent. For broad planning questions the model may call only the applicability check, not the timeline.

### Day 4: Obligations and evaluation (done 2026-10-23: obligations, timeline, Golden Set draft, evaluation log, 42 tests)

- "Extract Obligations" on an answer or provision: addressee, action, deadline, provision with link; each row cites its Passage; CSV export.
- Timeline view from the registry's milestones.
- Golden Set of about 20 questions, written after the interface is settled and reviewed by you; retrieval hit rate and Citation validity; the results log, with the naive baseline as first entry.
- Delivers C evaluation; the basis for C A/B testing.
- Added during the build: five retrieval set-ups are measured separately (naive, provision, lookup, cap, app). Draft results: cutting per Provision raises hit@6 on the seed questions from 0.77 to 1.00; the named lookup adds hits (0.88 to 0.92 on all questions); the per-Source cap costs hits (it pushed Art. 18 DORA out for the major-incident question) and helps only the crowding case's rank. A crowding case was added to the Golden Set so the trade-off stays measured.
- Progress made trustworthy (asked for on 2026-10-23): the steps reached the browser only at the end, because the Next.js server compressed the stream; the stream is now marked `no-transform`. The model's output is streamed, so "writing" is reported when the first words arrive and the answer appears word by word; the search step names what it found. No artificial delay was added. Streamed replies carry no cost from OpenRouter, so cost is computed from OpenRouter's per-token list prices.
- Answer evaluation (draft Golden Set): all answers cite and all citations are valid; answers citing an expected Provision rise from 77 % (naive, 13 questions) to 88 % (app, 25 questions); "full" coverage from 3 of 13 to 15 of 25.
- Resolved since: the cap was switched off on 2026-10-23; the Golden Set stays a draft by decision of 2026-10-28, and the full-set runs are in E1.

### Day 5: Buffer and submission (done 2026-10-23)

- Fixes, README walkthrough, demo script, screenshots.
- Done: per-Source cap switched off (`MAX_PER_SOURCE=0`) after the evaluation; fresh-install test from a clean clone into an empty database following the README only (fetch skipped existing files, ingest 5,596 Passages in 2.5 minutes, first answer stored); README rewritten as one path for reviewers with a requirements table; `docs/DEMO.md`; nine screenshots in `docs/screenshots/`; progress panel polished (formatted live text).
- Still open: your Golden Set review and the final evaluation on the reviewed set; the incident-classifier form; pushing the repository to a host if the submission needs a link.

## Accounts and dashboard (added 2026-10-23, after day 5)

- Optional accounts with email and password (scrypt hashes, hashed session tokens in an httpOnly cookie); answers private to their account; guest mode unchanged (ADR 0005).
- Firm Profile saved to the account; a guest profile is taken over on first login if the account has none.
- Dashboard at `/dashboard`, reworked after feedback (no cost, no first-question date; structure modelled on the OpenRouter dashboard): section menu with overview (key figures, questions per day, most-asked topics, latest questions), questions table with search, all extracted obligations in one table with CSV (a first stored obligation inventory), upcoming dates for the Firm Profile, profile and account; account deletion removes the answers too.
- Not yet: email verification, password reset, login through an identity provider such as Microsoft Entra ID.

## Redesign and dashboard analytics (2026-10-24)

- Interface redesigned in the "petrol, cooler and crisper" palette, chosen from four options: cool blue-grey page, deeper navy text, petrol as the one accent; every text colour passes 4.5:1 (the old grey for dates and counters did not). The layer stack became the logo. Header as one bar (pill switch for Research and Dashboard, Firm Profile chip, theme button); question box as one raised card with the model choice inside; example questions as cards; history grouped by today, yesterday and earlier; the same shapes and buttons on every screen. All ten screenshots retaken.
- Dashboard made analytical: a period switch (7, 30, 90 days or every question), **most-cited provisions** (in how many answers each Provision was cited), **Blind Spots** (Sources that apply to the Firm Profile under the applicability Rule Check but never came up, each with a ready question), and click-through: every day, topic and provision opens the questions behind it, with removable filter chips. Calculations in `backend/src/compliance_advisor/analytics.py`; 57 tests.

## Extensions (planned 2026-10-28)

Nine steps from `soft_requirements.txt`, decided in the design session of 2026-10-28 (terms in `CONTEXT.md`, ADRs 0006 and 0007). One step at a time: finished, tested and committed before the next, with eval figures wherever an eval exists. The Answer Models stay as they are (GPT-6 Luna, Mistral Large 4, Claude Sonnet 5.5).

**OpenRouter budget: about $2.50 for all nine steps, raised to about $3.50 during the day.** All tests and trial questions use GPT-6 Luna. Every eval run has a cost cap and stops when it is reached. Spent on 2026-10-28: about $1.50 (RAGAs calibration $0.67, RAGAs baseline $0.21, Mistral comparison $0.52, everything else under $0.10); about $2.00 left. Per-run costs in `docs/EVALUATION.md`.

### E1. Eval breakdown and hybrid search (done 2026-10-28: vector stays the default, 64 tests) — C: hybrid search

- Eval results split by question `type` and `cross_lingual`; a cost cap per run (`--max-cost`); a fixed split into a tuning and a held-out half (`--halves`); each question is searched once per set-up.
- Search Strategy chosen per question next to the Answer Model and recorded with the answer: vector search, or hybrid search (Postgres keyword search with German and English stemming, merged with vector search by reciprocal rank fusion; nothing re-embedded).
- Result on 214 questions: vector 0.85 hit@6, hybrid 0.79. Keyword search pulls in German texts for German questions about English EU acts, and recitals. Two variants tried, chosen on the tuning half: re-sorting only the vector candidates (0.78) and keyword ranks at half weight (0.82, against 0.88 for vector); on the held-out half half weight still lost (0.81 against 0.83). Hybrid search is offered with half weight; vector search stays the default.
- Found on the way: cross-lingual questions are the weakest kind (0.73 against 0.93). Translating the question into the Source's language would target this; not planned yet.

### E2. RAGAs evaluation (done 2026-10-28: faithfulness 0.96, factual correctness 0.51 on 50 questions) — C: evaluation with RAGAs

- `compliance-advisor-ragas` (dependency group `eval`; `langchain-community` pinned to 0.4.1 because ragas 0.4.3 imports a module that 0.4.2 dropped): faithfulness and factual correctness (against `answer_key`); context recall left out, as recall@6 covers it. A fixed sample of 50 questions, taken in turn from every question type; a cost cap that counts the questions still running.
- Grader: Qwen was blocked by the OpenRouter guardrail, so Gemma 4 31B was calibrated against Gemini 3.8 Flash on 10 answers: faithfulness 0.03 apart, factual correctness 0.22 apart (limit 0.15 missed). Gemini scored lower throughout, gave 0.0 to answers that match the key in the cases checked, was cut off in 4 of 10 gradings and cost 13 times more; Gemma stays the grader and factual correctness is read as a comparison between runs. The first calibration failed on most answers because ragas allows graders 1,024 output tokens; now 4,096.
- Baseline (GPT-6 Luna, vector search): faithfulness 0.96, so the model hardly states anything the Passages do not back; factual correctness 0.51, mostly because the right Provision was not among the six Passages and the answer says so. The weak point is the search, not the Answer Model. Cost $0.21 per run.
- Mistral Large 4 on the same sample, stopped by the $0.60 cap after 20 questions: on those 20, faithfulness 0.90 against 0.96 for Luna, factual correctness 0.30 against 0.50; a Mistral answer cost about $0.02, twenty times Luna's. Luna stays the default.

### E3. Answer Trace (done 2026-10-28) — A: visualisation of the RAG process

- Every answer carries its Answer Trace (`trace` in the response, stored with the answer): what the Pre-Check removed, Provisions looked up directly, the vector and keyword candidates with scores, the merged order, what the per-Source cap held back, how each of the six Passages was found, the Rule Checks, and seconds per step. The interface shows it under the answer as a flow of chips with the numbers; each chip opens its details. Answers stored before have no trace and show nothing.

### E4. Pre-Check and Refusals (done 2026-10-28: 30 of 30 attacks refused, 0 of 244 legitimate questions refused) — B: prompt-injection protection

- After personal data is removed, one model check screens the question (`precheck.screen`): GPT-6 Luna, or the chosen Answer Model itself when it is EU-hosted (ADR 0007). Manipulation attempts and topics outside financial regulation get a Refusal with the reason (`refusal` in the response, kept in the history as "refused"); questions the Corpus does not cover keep the coverage notice. No "answer anyway". If the screening call fails or answers unreadably, the question passes and the event is logged. The screening call's tokens count towards the answer's cost (about $0.00005 with Luna).
- `config/precheck_set.yaml` (18 manipulation attempts, 12 off-topic questions, 30 legitimate questions that mention ignoring, skipping, hidden instructions or system prompts) and `compliance-advisor-precheck-eval --golden`: 30 of 30 attacks refused, all with the expected reason; 0 of 30 suspicious-looking questions and 0 of 214 Golden Set questions wrongly refused; $0.01. README section "How the Compliance Advisor protects its answers" with the figures and the limits; a note on the start screen.

### E5. API keys and rate limiting (done 2026-10-28) — B: rate limiting and API key management

- Review fix 2026-10-28: "Extract Obligations" counts like a question, runs on the Answer Model the answer used (an EU-hosted answer stays in the EU), skips refused answers, and its cost is stored with the answer (`obligations_cost`) and counted in the daily ceiling and the Operator figures. Registrations are limited per address and login attempts per email (`config/limits.yaml`).
- Keys per Account (`apikeys.py`, dashboard section Account): named, shown once, stored as a SHA-256 hash with a prefix, revocable, last use shown. `Authorization: Bearer ca_...` works only on `/api/ask`, `/api/ask/stream` and the MCP server; every account endpoint answers 403 to a key; the public ones (`/api/models`, `/api/sources`, `/api/profiles`, `/api/timeline`) ignore it. Answers asked with a key are stored in the Account's history with the key's name.
- `config/limits.yaml`: guests 10 questions per hour per browser, Accounts 30 per hour and 200 per day (a key shares its Account's budget), and a daily cost ceiling for the whole app from the audit trail. A refusal is a 429 with `Retry-After`; the interface shows "try again from 14:35". Counters per subject live in the backend's memory and restart with it.
- Guests were first limited per address. The review on 2026-10-28 found that the Next.js proxy forwards `x-forwarded-host` but not `x-forwarded-for`, so every browser arrived as 127.0.0.1 and all guests shared one bucket. Now the backend sets a signed random guest id in an httpOnly cookie on the first response (`limits.GuestCookie`, not for `/mcp`), and the limit counts per browser; a forged or missing cookie falls back to one bucket per address, so minting cookies buys nothing. A client-supplied `x-forwarded-for` passes through the proxy, so it is believed only with `TRUST_X_FORWARDED_FOR=true` behind a real reverse proxy (last entry). Idle counters are evicted after a day. The signing key is per process: a restart reissues cookies.

### E6. Logging and monitoring (done 2026-10-28) — B: logging and monitoring

- Review fixes 2026-10-28: a 503 is counted in memory instead of being written to the database that is down (`monitoring.memory_errors`), other failed requests are written off the event loop, and database connects time out after three seconds.

- Logs as one JSON object per line (`LOG_FORMAT=json`, `text` for reading by eye), without question texts. Failed requests (502, 503, 500) are counted in an `events` table; everything else the Operator sees comes from the audit trail. Operators were first the addresses in `OPERATOR_EMAILS`; since the review of 2026-10-28 the role is a flag on the account granted with `compliance-advisor-accounts operator grant <email>`, because open registration would have let anyone become the listed address (ADR 0006, amended). `/api/auth/me` tells the interface.
- `GET /api/operator/overview?days=`: questions, answered and refused, Accounts and guest questions, questions via API key, cost, failed requests, average answer time, average similarity of the best Passage, share of answers with a Citation and with full coverage, questions per day, cost per Answer Model and per Search Strategy, Refusals per reason, errors per status. Shown as the dashboard section "Operations" (ADR 0006: figures, never texts).

### E7. Dashboard (done 2026-10-28) — C: advanced analytics dashboard

- Operator view across all Accounts (see E6) with the Update Runs and Change Records and a "check now" button (see E8).
- For the Compliance Officer: "Your sources have changed" on the overview (`GET /api/me/changes`): Sources their answers relied on whose checksum differs from the current copy, with the Change Record and how many answers used an older version. A reopened answer carries the same notice ("changed since this answer"); the answer itself stays as it was.

### E8. Update Runs (done 2026-10-28) — B: real-time data updates, C: automated knowledge-base updates

- `update.py`: an Update Run downloads every Source again and compares the file's checksum with `meta.json`. A changed file is chunked and its Passage ids compared with the stored ones, because BaFin web pages differ on every download without a word changing (found in the first real run: MaGo "changed" with 0 Provisions changed); only a Source whose text changed is embedded again, with its old Passages replaced in one step, and gets a Change Record counting the Provisions added, removed and changed. The text fingerprint goes into `meta.json` and into each answer's stored Source versions, so "changed since this answer" is text-based too. Runs start nightly inside the backend (`UPDATE_RUNS=true`, `UPDATE_HOUR`, a daemon thread) or from the Operator's "check now"; a process-level lock allows one run at a time (the first version checked the database and let two runs start). Failures of one Source are noted on the run and do not stop it. First real run: 18 Sources checked in 21 seconds, none with changed text. After the review of 2026-10-28 the run stages a changed file under `data/raw/.incoming/`, chunks it there, replaces the Passages in one transaction (`store.replace_source`) and only then moves the file and writes `meta.json`, so a failed reload is retried next time and never leaves the Source out of the index; the run row is always finished, even when the loop itself fails. A fresh download keeps the text fingerprint (`fetch.save_meta`), and the naive baseline's ingest no longer writes one. Changes to the Source Registry stay manual.

### E9. MCP server (done 2026-10-28) — C: tools as MCP servers

- `mcp_server.py` (MCP Python SDK 2.3, streamable HTTP, stateless, JSON responses) mounted at `/mcp` in the same backend: the four Rule Checks with explicit Firm Profile fields, and `search_corpus` (Passages with Provision, Source, link, legal status and similarity; writes no answer, so outside calls cost no Answer Model fees). Every request needs an API key in `Authorization: Bearer ca_...`; the key's Account pays into its own rate limit. Run locally; publishing it is a hosting decision for later. Claude Desktop or Claude Code connect with the URL `http://localhost:8010/mcp/` and the key as a bearer token.

### Review fixes, block B (done 2026-10-28)

- Retriever: Provisions named in the question take at most half the slots, and named hits beyond that now still come through the ranking instead of being dropped. The coverage line is recognised in its usual Markdown form (`**Coverage:** partial`), so it no longer leaks into the answer as "unknown".
- The live progress starts with "Frage prüfen" (the Pre-Check) before "Quellen durchsuchen"; the Rule Check step shows only when one ran; the found line says "6 Passagen aus DORA, GwG" instead of counting passages as sources; the `refused` stream event is typed.
- A stored Firm Profile is kept only if every value still exists (frontend `validProfile`; the backend's dashboard tolerates a stale one), so a renamed firm type or activity cannot wedge every question with a 422.
- A 429 names its limit (`X-Limit: questions | daily-cost`); the daily cost ceiling is shown as such with the date, not as a personal limit with a time. The usual failures (401, 403, 404, 502, 503) are shown in the interface language; a 401 on an account call signs the interface out, so an expired session no longer looks signed in.
- Dashboard: `/dashboard#operator` falls back to the overview for non-operators; errors clear on the next success; deleting the account and revoking a key report failures; "your sources have changed" refreshes with new answers; refused questions are tagged in the questions table and counted next to the questions figure; the Markdown export of a refused answer states the refusal.
- MCP `search_corpus` removes personal data and checks the question length like the question field.

### Review fixes, blocks C and D (done 2026-10-28)

- Update Runs refresh the naive baseline collection too when a Source's text changes, so the evaluation's "naive" rows stay comparable; the eval's `hybrid` set-up now uses the app's keyword weight (`hybrid-full` is the first variant, at full weight).
- Logs carry counts, not passage ids or the screening model's reply; uvicorn's own log lines go through the same JSON handler.
- Documentation brought in line: README API table and status codes, test count, the Golden Set's draft status, screenshot gallery; the superseded plan's steps say what superseded them; `ANSWER_MODEL` removed; `.env.example` lists the settings a deployment needs; VISION.md carries a note that nothing was carried over from the other prototype and that hybrid search was measured.
- Glossary words out of the interface and docs: "Regelwerke/Regimes" instead of "Themen/Topics", Compliance Officers instead of users or compliance teams, Rule Checks instead of tools, "declined" instead of "rejected".
- The obligations table shows the Citation column the design brief promised; a click opens the Passage.
- Code: one database engine (`db.py`), the Rule Check wiring in `rulechecks.py` (the evaluation scripts no longer import the web app), Provision links cached only when found and cleared after an Update Run, the registry and model list parsed once per file version, the dashboard query without Passage texts, a catch-all 500 handler that counts and never leaks the exception, the MCP server telling a database outage from a bad key. Frontend: one CSV helper, the keys and Operator sections in files of their own, dead strings and fields removed, hardcoded texts in `i18n.ts`, empty chart columns no longer keyboard stops.

### Private guest histories (done 2026-10-28)

- Guests no longer share one history: a guest's answers are filed under a hash of the browser's signed guest cookie, so the history, a stored answer and its export are visible only from that browser (ADR 0005, amended). Guest answers stored before have no guest id and are visible to nobody. Found while rehearsing for the review: the shared guest history contradicted the app's own privacy message.
- The dashboard for guests is a page of its own, "Nur mit Konto", with "Konto erstellen" and "Anmelden" buttons (the dialog opens on the matching tab); before, a guest's click on Dashboard bounced straight back to Research because the new session-expiry handler mistook a guest's 401 for an ended session.
- Clean install checked from the pushed commit: `docker compose up --build`, health, one question through the whole stack.

## After the submission

- Obligation tracker: status, owner and due date per obligation, with overdue and due-soon views; then team features (shared lists, assignment, second review).
- Horizon scanning: watching BaFin and EUR-Lex for new documents.
- AML due-diligence level and sanctions screening tools; agentic search and Graph RAG as measured alternatives; connecting tools from an external MCP server.
- Escalation triggers; publishing the app and its MCP server on the internet.
- Sustainability Regime (SFDR, taxonomy, CSRD).

## Earlier plan (2026-10-20), superseded by the submission plan above

### Step 2: Design session, UI layout (superseded)

- Decide the layout, the chat flow, how Passages, Citations and later tool results are shown; streaming answers; conversation history
- Delivers: H5 in full; A conversation history and export; A help feature or guide

### Step 3: Evaluation harness (superseded by day 4 and E2)

- Golden Set draft and review; retrieval metrics (hit@k, recall, MRR); answer metrics (faithfulness, citation validity)
- Delivers: C evaluation of the RAG system; the basis for C A/B testing

### Step 4: Retrieval upgrades (superseded by day 1 and E1)

- Structure-aware chunking (per article or paragraph), hybrid search, reranking, side-by-side strategy comparison measured on the Golden Set
- Delivers: C hybrid search; C A/B testing of RAG strategies; A visualisation of the RAG process

### Step 5: Firm Profile and tools (superseded by day 2)

- Firm Profile (licence type, size class, activities); tools: applicability check, compliance timeline, DORA incident classifier, AML due-diligence level, sanctions screening
- Delivers: H2 (at least three tool calls); H3 domain-specific responses; B visualisation of tool call results; B multi-model support

### Step 6: Safety, currency and updates (superseded by E4 and E8)

- Question pre-check (customer-data stripping, refusals, escalation to the money-laundering officer or counsel); prompt-injection protection; legal status and source currency; update run with change records and change detection per Source
- Delivers: H3 security measures; B prompt injection protection; B real-time knowledge base updates; C automated knowledge base updates

### Step 7: MCP, operations and polish (superseded by E5, E6, E7 and E9)

- MCP server for the tools; rate limiting and API key management; logging and monitoring; token usage and cost display; exports (PDF, CSV, JSON) that carry the notice; analytics dashboard; authentication if time allows
- Delivers: C tools as MCP servers; B rate limiting; B logging; B token usage and costs; B export formats; C analytics dashboard; B authentication
