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

`.env`: `OPENROUTER_API_KEY`, `DATABASE_URL`, `EMBEDDING_MODEL`, `ANSWER_MODEL`, `TOP_K`, `CHUNK_SIZE`, `CHUNK_OVERLAP`.

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
- Open: your review of the Golden Set, then the decision whether to switch the cap off (`MAX_PER_SOURCE=0`) and a final run on the reviewed set.

### Day 5: Buffer and submission (done 2026-10-23)

- Fixes, README walkthrough, demo script, screenshots.
- Done: per-Source cap switched off (`MAX_PER_SOURCE=0`) after the evaluation; fresh-install test from a clean clone into an empty database following the README only (fetch skipped existing files, ingest 5,596 Passages in 2.5 minutes, first answer stored); README rewritten as one path for reviewers with a requirements table; `docs/DEMO.md`; nine screenshots in `docs/screenshots/`; progress panel polished (formatted live text).
- Still open: your Golden Set review and the final evaluation on the reviewed set; the incident-classifier form; pushing the repository to a host if the submission needs a link.

## After the submission

- Stored obligation list across sessions, then team features (shared lists, assignment, second review).
- Automatic update runs with change records; full horizon scanning.
- AML due-diligence level and sanctions screening tools; agentic search as a measured alternative.
- Prompt-injection protection, refusals and escalation triggers; MCP server; rate limiting; analytics dashboard; user accounts.
- Sustainability Regime (SFDR, taxonomy, CSRD).

## Earlier plan (2026-10-20), superseded by the submission plan above

### Step 2: Design session, UI layout (superseded)

- Decide the layout, the chat flow, how Passages, Citations and later tool results are shown; streaming answers; conversation history
- Delivers: H5 in full; A conversation history and export; A help feature or guide

### Step 3: Evaluation harness (todo)

- Golden Set draft and review; retrieval metrics (hit@k, recall, MRR); answer metrics (faithfulness, citation validity)
- Delivers: C evaluation of the RAG system; the basis for C A/B testing

### Step 4: Retrieval upgrades (todo)

- Structure-aware chunking (per article or paragraph), hybrid search, reranking, side-by-side strategy comparison measured on the Golden Set
- Delivers: C hybrid search; C A/B testing of RAG strategies; A visualisation of the RAG process

### Step 5: Firm Profile and tools (todo)

- Firm Profile (licence type, size class, activities); tools: applicability check, compliance timeline, DORA incident classifier, AML due-diligence level, sanctions screening
- Delivers: H2 (at least three tool calls); H3 domain-specific responses; B visualisation of tool call results; B multi-model support

### Step 6: Safety, currency and updates (todo)

- Question pre-check (customer-data stripping, refusals, escalation to the money-laundering officer or counsel); prompt-injection protection; legal status and source currency; update run with change records and change detection per Source
- Delivers: H3 security measures; B prompt injection protection; B real-time knowledge base updates; C automated knowledge base updates

### Step 7: MCP, operations and polish (todo)

- MCP server for the tools; rate limiting and API key management; logging and monitoring; token usage and cost display; exports (PDF, CSV, JSON) that carry the notice; analytics dashboard; authentication if time allows
- Delivers: C tools as MCP servers; B rate limiting; B logging; B token usage and costs; B export formats; C analytics dashboard; B authentication
