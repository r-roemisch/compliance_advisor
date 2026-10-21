# Compliance Advisor

**A RAG assistant that answers regulatory questions for compliance professionals at financial firms supervised in Germany, citing the provisions it relies on.**

> **Not legal advice.** The Compliance Advisor gives general regulatory information only. It does not replace a qualified lawyer or the firm's own compliance assessment.

Built step by step as a Turing College bootcamp project. The plan and the current step are in [`docs/ROADMAP.md`](docs/ROADMAP.md), the project's terms in [`CONTEXT.md`](CONTEXT.md), and the decisions that are hard to reverse in [`docs/adr/`](docs/adr/).

## Status

Step 1, a naive RAG, is done: six Sources, an index pipeline, a question-and-answer API and a bare page, running as three containers. Step 2 decides the layout and design.

## Quick start

Needs Docker and an [OpenRouter](https://openrouter.ai) API key.

```bash
cp .env.example .env               # add your OPENROUTER_API_KEY
docker compose up --build          # postgres, backend, frontend
```

Then open **http://localhost:3010**. The backend API runs on port 8010 and Postgres on port 5433. The Corpus must be filled once, as described in the next section; it is kept in a Docker volume.

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
| `POST /api/ask` | Question in (3 to 2000 characters, optional `top_k`); answer with numbered Passages, the cited numbers, model, token usage and the notice out |
| `GET /api/health` | Says whether the backend runs and the database is reachable |
| `GET /api/sources` | Lists the Sources and how many Passages each has in the Corpus |

Errors come back as `{"detail": "..."}`: 422 for invalid input, 502 when OpenRouter does not respond, 503 when the database is not reachable. The interactive API documentation is at http://localhost:8010/docs.

## Seed Sources

Step 1 indexes six Sources. They were chosen to cover three Regimes, four of the five Regulatory Layers, three file formats and both languages, so that every loader is exercised and later steps can measure how well answers stack the layers.

| Id | Source | Regulatory Layer | Format | Language | Why |
|---|---|---|---|---|---|
| `eu-dora` | Regulation (EU) 2022/2554, Digital Operational Resilience Act (DORA) | EU Level 1 | EUR-Lex HTML | EN | Applies to nearly every type of firm; most questions touch it |
| `eu-dora-rts-incidents` | Delegated Regulation (EU) 2024/1772, classification of ICT-related incidents | EU Level 2 | EUR-Lex HTML | EN | Hangs off DORA Article 18; a "major incident" question needs both texts |
| `eu-amlr` | Regulation (EU) 2024/1624, Anti-Money Laundering Regulation (AMLR) | EU Level 1 | EUR-Lex HTML | EN | The coming EU rulebook, applies from 10 July 2027; future law that must not be presented as current |
| `de-gwg` | Geldwäschegesetz (GwG), German Money Laundering Act | National Law | gesetze-im-internet XML | DE | The AML act German firms live by today |
| `de-bafin-aua-gwg` | BaFin, Auslegungs- und Anwendungshinweise zum GwG | Supervisory Practice | PDF | DE | BaFin's reading of the GwG; pairs with `de-gwg` |
| `de-zag` | Zahlungsdiensteaufsichtsgesetz (ZAG), German Payment Services Supervision Act | National Law | gesetze-im-internet XML | DE | A second Regime, payments, and a second XML sample |

Adding a Source means adding an entry to `config/sources.yaml`. A new file format means one new loader function. EU Level 3 Sources, such as EBA guidelines, come with the corpus step of the roadmap.

---

<sub>This is general regulatory information, not legal advice. It does not replace a qualified lawyer or the firm's own compliance assessment.</sub>
