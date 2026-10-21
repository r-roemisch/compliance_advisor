# Roadmap

The Compliance Advisor is built step by step, one or more sessions per step, and every step leaves a working app. Status values: `todo`, `in progress`, `done`.

`hard_requirements.txt` (H1 to H5) and `soft_requirements.txt` (A easy, B medium, C hard) are the bootcamp's requirements. Each step lists what it delivers against them, so nothing is forgotten.

## Working agreements

- Build only the current step. Later ideas go into this file, not into the code.
- Ask before downloading any Source; the registry entry is agreed first.
- Say explicitly when a config file such as `.env.example` or `.env` is created, so it can be filled in.
- No code, docs or wording are reused from other projects. This project stands on its own.
- Terms live in `CONTEXT.md`; hard-to-reverse decisions in `docs/adr/`; the handoff note for the next session in `last_session.md`.

## Step 1: Naive RAG (in progress, designed 2026-10-20/21)

Built in three sub-steps with a check-in after each.

### 1a. Sources in

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

### 1b. Questions answered

- `POST /api/ask` with `{question, top_k?}`: validate (3 to 2000 characters, otherwise 422), embed the question, top-6 cosine similarity search with scores, build the prompt, call `openai/gpt-6-luna` through `ChatOpenAI` with OpenRouter's base URL, return the agreed response shape (see `last_session.md` until it lives in `schemas.py`).
- `GET /api/health` (alive, database reachable) and `GET /api/sources` (what the Corpus holds).
- Synchronous JSON, single-turn. Streaming and history come with step 2.
- Prompt: the agreed professional prompt in `prompt.py`. No disclaimer inside the answer text; the `disclaimer` field travels with every response.
- Errors: 502 when the Answer Model fails, 503 when the database is unreachable; the page shows the message. One log line per question with duration, Passage ids, model and token counts.
- About ten unit tests without network or database: loaders on fixtures, Passage id determinism, prompt formatting, API validation with model and embeddings mocked.

### 1c. Page and containers

- Next.js 16 with TypeScript, App Router, Tailwind and ESLint; `/api/*` forwarded to the backend by a rewrite rule; react-markdown for the answer.
- One page: question box, Ask button, spinner, the answer, the six Passages with the cited ones marked, an error line, the permanent notice below the chat, the list of Sources in the Corpus.
- Backend and frontend Dockerfiles; compose with exactly three containers; host ports 5433 (Postgres), 8010 (backend), 3010 (frontend).
- Development loop: backend and frontend run locally against the Postgres container; `docker compose up --build` for full runs.

### Settings

`.env`: `OPENROUTER_API_KEY`, `DATABASE_URL`, `EMBEDDING_MODEL`, `ANSWER_MODEL`, `TOP_K`, `CHUNK_SIZE`, `CHUNK_OVERLAP`.

### Done when

1. Fetch and ingest run on all six Sources without errors, and `--dry-run` shows sensible Passage counts.
2. Three questions get sensible cited answers: English on DORA incident reporting, German on GwG due diligence, and one outside the Corpus that shows the "not covered" behaviour.
3. The tests pass.
4. `docker compose up --build` brings up all three containers and the page answers.

Delivers: H1 in full (knowledge base, embeddings, chunking, similarity search); H3 partly (domain, focused knowledge base, domain prompt); H4 (LangChain with OpenRouter, error handling, input validation); H5 partly (Next.js, sources shown, progress indicator); A source citations; C multi-language partly (German and English Sources, answer in the question's language).

## Step 2: Design session, UI layout (todo)

- Decide the layout, the chat flow, how Passages, Citations and later tool results are shown; streaming answers; conversation history
- Delivers: H5 in full; A conversation history and export; A help feature or guide

## Step 3: Evaluation harness (todo)

- Golden Set draft and review; retrieval metrics (hit@k, recall, MRR); answer metrics (faithfulness, citation validity)
- Delivers: C evaluation of the RAG system; the basis for C A/B testing

## Step 4: Retrieval upgrades (todo)

- Structure-aware chunking (per article or paragraph), hybrid search, reranking, side-by-side strategy comparison measured on the Golden Set
- Delivers: C hybrid search; C A/B testing of RAG strategies; A visualisation of the RAG process

## Step 5: Firm Profile and tools (todo)

- Firm Profile (licence type, size class, activities); tools: applicability check, compliance timeline, DORA incident classifier, AML due-diligence level, sanctions screening
- Delivers: H2 (at least three tool calls); H3 domain-specific responses; B visualisation of tool call results; B multi-model support

## Step 6: Safety, currency and updates (todo)

- Question pre-check (customer-data stripping, refusals, escalation to the money-laundering officer or counsel); prompt-injection protection; legal status and source currency; update run with change records and change detection per Source
- Delivers: H3 security measures; B prompt injection protection; B real-time knowledge base updates; C automated knowledge base updates

## Step 7: MCP, operations and polish (todo)

- MCP server for the tools; rate limiting and API key management; logging and monitoring; token usage and cost display; exports (PDF, CSV, JSON) that carry the notice; analytics dashboard; authentication if time allows
- Delivers: C tools as MCP servers; B rate limiting; B logging; B token usage and costs; B export formats; C analytics dashboard; B authentication
