# Compliance Advisor

**A RAG assistant that answers regulatory questions for compliance professionals at financial firms supervised in Germany, citing the provisions it relies on.**

> **Not legal advice.** The Compliance Advisor gives general regulatory information only. It does not replace a qualified lawyer or the firm's own compliance assessment.

Built step by step as a Turing College bootcamp project. The plan and the current step are in [`docs/ROADMAP.md`](docs/ROADMAP.md), the project's terms in [`CONTEXT.md`](CONTEXT.md), and the decisions that are hard to reverse in [`docs/adr/`](docs/adr/).

## Status

Step 1, a naive RAG, is done. Day 1 of the five-day submission plan in [`docs/ROADMAP.md`](docs/ROADMAP.md) is done too: 18 Sources cut into Provisions, each with a link to the exact article or paragraph, its Legal Status and dated Milestones. Day 2 added four Rule Checks the model can call, the Firm Profile with presets, and a pre-check that removes personal data. The designed interface follows on day 3.

## Quick start

Needs Docker and an [OpenRouter](https://openrouter.ai) API key.

```bash
cp .env.example .env               # add your OPENROUTER_API_KEY
docker compose up --build          # postgres, backend, frontend
```

Then open **http://localhost:3010**. The backend API runs on port 8010 and Postgres on port 5433. The Corpus must be filled once, as described in the next section; it is kept in a Docker volume.

## Trust and data

A compliance team can only use an answer it can check. These are the Compliance Advisor's rules for that.

**Built**

- **Public Sources only.** The Corpus holds published regulatory texts: EU acts, German acts and BaFin guidance. There is no upload, and no internal document of any Firm is stored.
- **Official publishers.** Every Source is downloaded from its official publisher: the EU Publications Office, gesetze-im-internet.de or BaFin. The download date and a checksum of each file are kept next to it.
- **Numbered Citations.** Every statement in an answer cites a numbered Passage. Each Passage shows its Source, issuer, Regulatory Layer and language.
- **A link to the exact Provision** in the official text next to every Passage, such as Article 17 DORA or § 10 GwG.
- **Legal Status and "as of" dates.** Each Source carries its Legal Status, version and dated Milestones, checked against its own text, and the date the app's copy was downloaded. Rules that apply only later, such as the AMLR, are marked so.
- **"Not covered" instead of guessing.** When the Passages do not answer a question, the answer says which part is not covered instead of filling the gap from memory.
- **No compliance verdicts.** The app explains what the rules require; it never says whether a specific Firm is compliant. A permanent notice below the chat says that the answers are not legal advice.

**Planned**

- **Audit trail.** Every question and answer is stored with the exact Source versions used, and can be exported.
- **"Not covered" made visible** in the interface, not only in the answer text.

**What leaves the app.** The question, together with the retrieved Passages and the Firm Profile, is sent to the Answer Model through OpenRouter, an external service. A pre-check removes IBANs, email addresses and phone numbers first; names and other details are not detected. Do not enter confidential Firm data or Customer data in a question.

## Getting the Sources in

For local development, run the database in Docker and the commands with [uv](https://docs.astral.sh/uv/). Inside Docker the same commands work as `docker compose run --rm backend compliance-advisor-ingest`.

```bash
cp .env.example .env                                   # add your OPENROUTER_API_KEY
docker compose up -d postgres                          # Postgres with pgvector on port 5433
cd backend
uv run compliance-advisor-fetch --source eu-dora       # download one Source into data/raw/
uv run compliance-advisor-ingest --dry-run             # load and cut only; no key, no database
uv run compliance-advisor-ingest                       # embed and store every downloaded Source
```

`compliance-advisor-fetch --all` downloads every Source. `compliance-advisor-ingest --source <id>` re-indexes one Source: its old Passages are deleted first, so running it again never creates duplicates.

## Asking questions without the page

```bash
cd backend
uv run compliance-advisor-api                          # API on http://localhost:8010
curl -s -X POST localhost:8010/api/ask -H 'content-type: application/json' \
     -d '{"question": "When is an ICT-related incident major under DORA?"}'
uv run pytest                                          # unit tests, no network, no database
```

The page in development: `cd frontend && npm install && npm run dev`, then http://localhost:3010. It forwards `/api/*` to the backend on port 8010.

| Endpoint | Does |
|---|---|
| `POST /api/ask` | Question in (3 to 2000 characters, optional `top_k` and `profile`); answer with numbered Passages, cited numbers, Rule Check results, what the pre-check removed, model, token usage and the notice out |
| `GET /api/health` | Says whether the backend runs and the database is reachable |
| `GET /api/sources` | Lists the Sources with Legal Status, version, Milestones, "as of" date and Passage count |
| `GET /api/profiles` | Lists the Firm Profile presets |

Errors come back as `{"detail": "..."}`: 422 for invalid input, 502 when OpenRouter does not respond, 503 when the database is not reachable. The interactive API documentation is at http://localhost:8010/docs.

## Rule checks and the Firm Profile

The Answer Model may call four Rule Checks once before it answers. Each is plain code that applies rules taken from the Sources, names the Provision that decides its result, and lists missing facts instead of assuming them.

| Rule check | Answers | Built on |
|---|---|---|
| `check_applicability` | Which Regimes apply to the Firm, and why | DORA Art. 2, § 2 GwG, AMLR Art. 3 and 90, § 1 ZAG, Solvency II Art. 4, MaRisk AT 2.1, AI Act Art. 4 and Annex III |
| `compliance_timeline` | Dated Milestones, past and upcoming | the Milestones in `config/sources.yaml` |
| `classify_dora_incident` | Whether an ICT incident is major, and the reporting deadlines | Delegated Regulation 2024/1772 Art. 8 and 9; Delegated Regulation 2025/301 Art. 5; DORA Art. 19 |
| `check_ai_act_use_case` | Risk class of an AI use and the resulting duties | AI Act Art. 4, 6, 26, 27, 50, 113 and Annex III |

The **Firm Profile** (firm type, size class, customers, activities) travels with each question and shapes the Rule Checks. `GET /api/profiles` lists presets that describe firm types, never real companies: insurance group, reinsurer, life insurer, significant bank, less significant bank, payment institution.

The **pre-check** removes IBANs, email addresses and phone numbers from a question before anything leaves the app, and the response says what was removed. Names are not detected; do not enter them.

## Sources

18 Sources across six Regimes, 6,415 Passages. Each Passage is one Provision (an article, recital, annex, § or numbered guideline section), or part of a long one, and links to exactly that Provision in the official text. EU texts are the latest consolidated version in force where one exists in English.

| Regime | Source | Regulatory Layer | Version | Passages |
|---|---|---|---|---|
| DORA | Regulation (EU) 2022/2554 (DORA) | EU Level 1 | OJ L 333, 27.12.2022 | 224 |
| DORA | Delegated Regulation (EU) 2024/1772, classification of ICT incidents | EU Level 2 | OJ 25.6.2024 | 32 |
| DORA | Delegated Regulation (EU) 2025/301, content and time limits of incident reports | EU Level 2 | OJ 20.2.2025 | 17 |
| AML | Regulation (EU) 2024/1624 (AMLR), applies from 10 July 2027 | EU Level 1 | OJ 19.6.2024 | 336 |
| AML | Geldwäschegesetz (GwG) | National Law | amended 29.6.2026 | 172 |
| AML | BaFin Auslegungs- und Anwendungshinweise zum GwG | Supervisory Practice | July 2025 | 201 |
| Payments | Zahlungsdiensteaufsichtsgesetz (ZAG) | National Law | amended 25.3.2026 | 127 |
| Insurance | Directive 2009/138/EC (Solvency II) | EU Level 1 | consolidated 17.1.2025 | 459 |
| Insurance | Delegated Regulation (EU) 2015/35 (Solvency II) | EU Level 2 | consolidated 14.11.2024 | 1,453 |
| Insurance | Directive (EU) 2016/97 (IDD) | EU Level 1 | consolidated 9.10.2024 | 80 |
| Insurance | Versicherungsaufsichtsgesetz (VAG) | National Law | amended 25.9.2026 | 547 |
| Insurance | BaFin Rundschreiben 09/2025 (VA), MaGo | Supervisory Practice | in force 14.10.2025 | 81 |
| Banking | Regulation (EU) No 575/2013 (CRR) | EU Level 1 | consolidated 26.6.2026 | 1,273 |
| Banking | Directive 2013/36/EU (CRD) | EU Level 1 | consolidated 11.7.2026 | 339 |
| Banking | Kreditwesengesetz (KWG) | National Law | amended 12.5.2026 | 577 |
| Banking | BaFin Rundschreiben 06/2026 (BA), MaRisk; not for ECB-supervised banks (AT 2.1) | Supervisory Practice | 30.6.2026 | 118 |
| Digital | Regulation (EU) 2024/1689 (AI Act) | EU Level 1 | consolidated 27.7.2026 | 240 |
| Digital | Regulation (EU) 2016/679 (GDPR) | EU Level 1 | consolidated 4.5.2016 | 139 |

**How links reach a Provision.** EU acts: the article anchor on EUR-Lex (`#art_17`). German acts: the paragraph's own page on gesetze-im-internet.de (`__10.html`). BaFin PDFs: the page where the section starts (`#page=67`). BaFin web pages: a text fragment that scrolls to the section heading (`#:~:text=9.1.1 Allgemeines`).

**How search works.** The six most similar Passages by cosine similarity, with at most three from one Source when others qualify, so one closely related act cannot fill every slot. A Provision named in the question, such as "§ 25a KWG" or "Art. 6 AI Act", is looked up directly and comes first. The naive fixed-size index of the first six Sources is kept as the baseline for the evaluation.

Adding a Source means adding an entry to `config/sources.yaml`. Formats: `html` (EU acts, original or consolidated), `gii_xml` (German acts), `pdf` and `web_html` (BaFin).

---

<sub>This is general regulatory information, not legal advice. It does not replace a qualified lawyer or the firm's own compliance assessment.</sub>
