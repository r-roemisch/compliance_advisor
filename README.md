# Compliance Advisor

**A regulatory research assistant for compliance teams at banks and insurers supervised in Germany. It answers from EU law, German acts and BaFin practice, cites the exact provision for every statement, and computes thresholds and deadlines with rule checks written in code.**

> **Not legal advice.** The Compliance Advisor gives general regulatory information only. It does not replace a qualified lawyer or the firm's own compliance assessment.

Built as a Turing College bootcamp project. German interface by default, English one click away.

![An answer with citations next to the original sources](docs/screenshots/answer.png)

## What it does

- **Answers with citations.** Every statement cites a numbered passage; clicking the citation highlights the passage, and each passage links to the exact article or paragraph in the official text (EUR-Lex, gesetze-im-internet.de, BaFin).
- **Shows the layer of each rule.** A small stack glyph marks where a passage sits: EU regulation, EU technical standard, EU guideline, German law or BaFin practice. Binding law is drawn solid, supervisory expectation outlined.
- **Knows what applies when.** Each source carries its legal status, version and dated milestones checked against its own text, so the AMLR is marked as applying only from 10 July 2027 and the AI Act's high-risk rules from 2 December 2027.
- **Rule checks** that the model calls when a question needs an exact result: which regimes apply to a firm, the compliance timeline, whether an ICT incident is major under DORA (with the reporting deadline), and the AI Act risk class of an AI use.
- **Firm Profile** with presets by firm type (insurance group, reinsurer, life insurer, significant bank, less significant bank, payment institution).
- **Extract obligations** from an answer into a table of who must do what by when, with the provision, as CSV for Excel.
- **Timeline** of all dated milestones, or only those that apply to the Firm Profile.
- **Audit trail**: every answer is stored with the exact source versions it used and can be exported as Markdown, JSON or PDF.
- **Honest progress**: the steps appear as they happen, the search step names what it found, and the answer appears while it is written.
- **Accounts and dashboard** (optional): sign up with email and password; your questions, answers and Firm Profile stay private to you. The dashboard has five sections: an overview (questions and extracted obligations, the next date, questions per day, most-asked topics, latest questions), a searchable table of all your questions with their topics and rule checks, all your extracted obligations in one table with CSV export, the upcoming dates for your Firm Profile, and profile and account settings. Deleting the account deletes its answers.
- **Model choice** including an EU-hosted model (Mistral Large 4 on Mistral AI's own servers), with tokens and cost shown for every answer.

| Answer being written | Rule check | Obligations |
|---|---|---|
| ![Progress steps and the answer appearing](docs/screenshots/progress.png) | ![DORA incident classification](docs/screenshots/rule-check.png) | ![Obligations table](docs/screenshots/obligations.png) |

| Timeline for a Firm Profile | Dark mode | Phone |
|---|---|---|
| ![Timeline tab](docs/screenshots/timeline.png) | ![Dark mode](docs/screenshots/answer-dark.png) | ![Phone layout](docs/screenshots/mobile.png) |

## Quick start

Needs Docker and an [OpenRouter](https://openrouter.ai) API key.

```bash
cp .env.example .env                       # add your OPENROUTER_API_KEY
docker compose up -d --build               # postgres, backend, frontend
docker compose run --rm backend compliance-advisor-fetch --all    # download the 18 sources (about 70 MB)
docker compose run --rm backend compliance-advisor-ingest         # index them: about 3 minutes, about 6 cents
```

Then open **http://localhost:3010**. The backend runs on port 8010 and Postgres on 5433. The index lives in a Docker volume, so the last two commands are needed only once. Tested from a clean clone on 2026-10-23.

A five-minute walkthrough for a demo is in [`docs/DEMO.md`](docs/DEMO.md).

## How it works

```
 Browser ──/api/*──▶ Next.js (:3010) ──▶ FastAPI (:8010) ──▶ OpenRouter: embeddings, Answer Model
                     server-sent events      │
                                             └──▶ Postgres + pgvector (:5433): passages, answers
```

**Indexing**, once per source: the fetch command downloads each file from its official publisher (checking robots.txt). A loader per format cuts it into **provisions**: articles, recitals and annexes of EU acts, § of German acts, numbered sections of BaFin circulars. Long provisions are split into parts that keep their label. Each passage is embedded with `text-embedding-3-small` and stored with its provision label, link, legal status, version and download date.

**Answering**, per question:

1. A pre-check removes IBANs, email addresses and phone numbers.
2. The six most similar passages are found by cosine similarity; a provision named in the question ("§ 25a KWG", "Art. 6 AI Act") is looked up directly and comes first.
3. The prompt states the rules (cite every statement, separate binding law from supervisory expectation, say what is not covered) and adds the Firm Profile.
4. The Answer Model may call the rule checks once, then writes the answer, which streams to the page.
5. The answer is stored with its passages and source versions for the audit trail.

| Part | Stack |
|---|---|
| `backend/` | Python 3.12, FastAPI, LangChain (`langchain-openai` against OpenRouter), `langchain-postgres` |
| `frontend/` | Next.js 16, React 19, Tailwind 4, IBM Plex fonts served by the app |
| `config/` | `sources.yaml` (the 18 sources), `models.yaml` (Answer Models), `golden_set.yaml` (test questions) |
| Database | Postgres 17 with pgvector |

## Sources

18 sources across six regimes, 5,596 passages. EU texts are the latest consolidated version in force where one exists in English; German texts are in German, as published.

| Regime | Source | Layer | Version | Passages |
|---|---|---|---|---|
| DORA | Regulation (EU) 2022/2554 (DORA) | EU regulation | OJ L 333, 27.12.2022 | 224 |
| DORA | Delegated Regulation (EU) 2024/1772, classification of ICT incidents | EU technical standard | OJ 25.6.2024 | 32 |
| DORA | Delegated Regulation (EU) 2025/301, content and time limits of incident reports | EU technical standard | OJ 20.2.2025 | 17 |
| AML | Regulation (EU) 2024/1624 (AMLR), applies from 10 July 2027 | EU regulation | OJ 19.6.2024 | 336 |
| AML | Geldwäschegesetz (GwG) | German law | amended 29.6.2026 | 172 |
| AML | BaFin Auslegungs- und Anwendungshinweise zum GwG | BaFin practice | July 2025 | 201 |
| Payments | Zahlungsdiensteaufsichtsgesetz (ZAG) | German law | amended 25.3.2026 | 127 |
| Insurance | Directive 2009/138/EC (Solvency II) | EU directive | consolidated 17.1.2025 | 459 |
| Insurance | Delegated Regulation (EU) 2015/35 (Solvency II) | EU technical standard | consolidated 14.11.2024 | 634 |
| Insurance | Directive (EU) 2016/97 (IDD) | EU directive | consolidated 9.10.2024 | 80 |
| Insurance | Versicherungsaufsichtsgesetz (VAG) | German law | amended 25.9.2026 | 547 |
| Insurance | BaFin Rundschreiben 09/2025 (VA), MaGo | BaFin practice | in force 14.10.2025 | 81 |
| Banking | Regulation (EU) No 575/2013 (CRR) | EU regulation | consolidated 26.6.2026 | 1,273 |
| Banking | Directive 2013/36/EU (CRD) | EU directive | consolidated 11.7.2026 | 339 |
| Banking | Kreditwesengesetz (KWG) | German law | amended 12.5.2026 | 577 |
| Banking | BaFin Rundschreiben 06/2026 (BA), MaRisk; not for ECB-supervised banks (AT 2.1) | BaFin practice | 30.6.2026 | 118 |
| Digital | Regulation (EU) 2024/1689 (AI Act) | EU regulation | consolidated 27.7.2026 | 240 |
| Digital | Regulation (EU) 2016/679 (GDPR) | EU regulation | consolidated 4.5.2016 | 139 |

Adding a source means adding an entry to `config/sources.yaml`, then `compliance-advisor-fetch --source <id>` and `compliance-advisor-ingest --source <id>`. Formats: `html` (EU acts, original or consolidated), `gii_xml` (German acts), `pdf` and `web_html` (BaFin).

## Rule checks

Plain code, not model output: each check applies rules taken from the sources' own text, names and links the provision that decides its result, and lists missing facts instead of assuming them.

| Rule check | Answers | Built on |
|---|---|---|
| `check_applicability` | Which regimes apply to the Firm, and why | DORA Art. 2, § 2 GwG, AMLR Art. 3 and 90, § 1 ZAG, Solvency II Art. 4, MaRisk AT 2.1, AI Act Art. 4 and Annex III |
| `compliance_timeline` | Dated milestones, past and upcoming | the milestones in `config/sources.yaml` |
| `classify_dora_incident` | Whether an ICT incident is major, and the reporting deadlines | Delegated Regulation 2024/1772 Art. 8 and 9; Delegated Regulation 2025/301 Art. 5; DORA Art. 19 |
| `check_ai_act_use_case` | Risk class of an AI use and the resulting duties | AI Act Art. 4, 6, 26, 27, 50, 113 and Annex III |

## Trust and data

- **Public sources only.** No upload, and no internal document of any firm is stored ([ADR 0004](docs/adr/0004-public-sources-only-no-firm-documents.md)).
- **Official publishers**, with the download date and SHA-256 checksum of every file kept next to it.
- **Every statement cited**; citations that point to no passage are not counted, and the evaluation checks that none occur.
- **"Not covered" instead of guessing.** The answer says which part the sources do not cover, and the page shows it above the answer.
- **No compliance verdicts.** The app explains what rules require; it never says whether a specific firm is compliant ([ADR 0003](docs/adr/0003-regulatory-information-not-legal-advice.md)).
- **What leaves the app.** The question, the retrieved passages and the Firm Profile go to the Answer Model through OpenRouter. The pre-check removes IBANs, email addresses and phone numbers first; names are not detected. An EU-hosted model can be chosen. The browser itself contacts no third party.
- **Audit trail** of every answer with its source versions. With an account, answers are private to it; guests share one guest history ([ADR 0005](docs/adr/0005-optional-accounts-private-answers.md)).
- **Accounts store** email address, name, Firm Profile and answers. Passwords are kept only as salted scrypt hashes and sessions as hashes in an httpOnly cookie. There is no email verification or password reset yet.

## Evaluation

`config/golden_set.yaml` holds 25 test questions (half in German), each with the provisions a good search must find. Thirteen can be answered from the first six sources, which is all the naive step 1 index holds, so it can be compared on them. Results on the draft Golden Set (review pending):

| Retrieval set-up | Questions | hit@6 | recall@6 | MRR |
|---|---|---|---|---|
| Naive fixed-size chunks (step 1 baseline) | 13 | 0.77 | 0.77 | 0.67 |
| One passage per provision | 13 | 1.00 | 0.96 | 0.69 |
| Per provision + direct lookup of named provisions (the app) | 25 | 0.92 | 0.86 | 0.72 |
| Per provision + lookup + cap of three passages per source | 25 | 0.88 | 0.81 | 0.72 |

The cap was switched off because of this result. Answers: every answer cites, and no citation points to a missing passage; answers citing an expected provision rise from 77 % (naive, 13 questions) to 88 % (app with rule checks, 25 questions).

```bash
cd backend
uv run compliance-advisor-eval --label "what changed"                  # naive, provision, app
uv run compliance-advisor-eval --label "..." --setups lookup cap       # one change at a time
uv run compliance-advisor-eval --label "..." --answers                 # also generate and score answers
uv run compliance-advisor-ingest --chunker fixed --source eu-dora --source eu-dora-rts-incidents \
    --source eu-amlr --source de-gwg --source de-bafin-aua-gwg --source de-zag   # builds the naive index
```

Every run is appended to `evaluation/results.jsonl` and summarised in [`docs/EVALUATION.md`](docs/EVALUATION.md).

## Development

```bash
docker compose up -d postgres                          # database only
cd backend && uv sync
uv run compliance-advisor-ingest --dry-run             # load and cut only; no key, no database
uv run compliance-advisor-api                          # API on :8010
uv run pytest                                          # 50 tests, no network, no database
cd ../frontend && npm install && npm run dev           # page on :3010, /api forwarded to :8010
```

| Endpoint | Does |
|---|---|
| `POST /api/ask` | Question (3 to 2000 characters, optional `profile`, `model`, `top_k`) in; answer, numbered passages, cited numbers, rule-check results, coverage, pre-check removals, model, tokens, cost and the notice out |
| `POST /api/ask/stream` | The same as server-sent events: one per step, the answer text as it is written, then the result |
| `GET /api/sources` | Sources with legal status, version, milestones, download date and passage count |
| `GET /api/profiles`, `GET /api/models` | Firm Profile presets; Answer Models from `config/models.yaml` |
| `GET /api/history?q=`, `GET /api/history/{id}` | Your stored answers (or the guest answers), with a search |
| `GET /api/history/{id}/export?format=md\|json` | One stored answer as Markdown or JSON, with source versions |
| `POST /api/history/{id}/obligations` | Extracts the obligations behind a stored answer and stores them |
| `POST /api/timeline` | Milestones, optionally only for a Firm Profile and only upcoming ones |
| `POST /api/auth/register`, `/login`, `/logout`; `GET /api/auth/me` | Accounts; the session is an httpOnly cookie |
| `PUT /api/me/profile`, `DELETE /api/me` | Save the Firm Profile; delete the account with its answers |
| `GET /api/me/dashboard`, `/api/me/questions?q=`, `/api/me/obligations` | Dashboard overview; all own questions with topics and rule checks; all own extracted obligations |
| `GET /api/health` | Backend and database status |

Errors come back as `{"detail": "..."}`: 422 for invalid input, 502 when OpenRouter does not respond, 503 when the database is not reachable.

## Bootcamp requirements

| Requirement | Where |
|---|---|
| **1. RAG**: knowledge base, embeddings, chunking, similarity search | 18 sources; per-provision chunking with a naive fixed-size baseline; `text-embedding-3-small`; pgvector cosine search |
| **2. Tool calling**: at least three domain tools | four rule checks the model calls (applicability, timeline, DORA incident, AI Act use case) |
| **3. Domain specialisation** and security | German financial supervision; prompts for compliance professionals; pre-check for personal data; no uploads; passages treated as data, not instructions |
| **4. LangChain with OpenRouter**, error handling, input validation | `langchain-openai` against OpenRouter; 422/502/503 with clear messages; question length and profile validated |
| **5. Next.js interface**: context and sources, tool results, progress | citations linked to passages; rule-check cards; live progress steps and streamed answer |

| Optional | Status |
|---|---|
| Conversation history and export | yes: history, Markdown, JSON, PDF via print; obligations as CSV |
| Source citations | yes |
| Visualisation of the RAG process | partly: live steps with found sources, layer glyph and strip |
| Help feature | partly: start screen with explanation and example questions |
| Multi-model support | yes: GPT-6 Luna, Mistral Large 4 (EU), Claude Sonnet 5.5 |
| Token usage and costs | yes, per answer |
| Visualisation of tool results | yes, one card layout per rule check |
| Prompt-injection protection | partly: passages and question are declared data in the prompt; no separate filter |
| Authentication and personalisation | yes: optional accounts (email and password), Firm Profile saved to the account, dashboard, private searchable archive |
| Logging | partly: one log line per question and the audit trail; no monitoring |
| Multi-language support | yes: German and English interface; answers in the question's language; sources in both languages |
| A/B testing of RAG strategies | yes, offline: five retrieval set-ups compared on the Golden Set |
| Evaluation of the RAG system | yes: own retrieval and answer metrics, logged per run |
| Not done | hybrid search, automated knowledge-base updates, rate limiting, MCP server, analytics dashboard |

## Documentation

| File | Contents |
|---|---|
| [`docs/DEMO.md`](docs/DEMO.md) | A five-minute demo |
| [`docs/EVALUATION.md`](docs/EVALUATION.md) | Every evaluation run |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | The plan, what was built each day, and what comes after the submission |
| [`CONTEXT.md`](CONTEXT.md) | Glossary: Source, Passage, Provision, Regulatory Layer, Firm Profile, Rule Check, Obligation, … |
| [`docs/adr/`](docs/adr/) | Decisions that are hard to reverse |
| [`docs/DESIGN-BRIEF.md`](docs/DESIGN-BRIEF.md) | The brief the interface was built from |

---

<sub>This is general regulatory information, not legal advice. It does not replace a qualified lawyer or the firm's own compliance assessment.</sub>
