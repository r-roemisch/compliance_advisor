# Compliance Advisor

**A RAG assistant that answers regulatory questions for compliance professionals at financial firms supervised in Germany, citing the provisions it relies on.**

> **Not legal advice.** The Compliance Advisor gives general regulatory information only. It does not replace a qualified lawyer or the firm's own compliance assessment.

Built step by step as a Turing College bootcamp project. The plan and the current step are in [`docs/ROADMAP.md`](docs/ROADMAP.md), the project's terms in [`CONTEXT.md`](CONTEXT.md), and the decisions that are hard to reverse in [`docs/adr/`](docs/adr/).

## Status

Step 1, a naive RAG, is being built in three sub-steps. Sub-step 1a, getting the Sources in, has its code in place. The question-and-answer API and the page follow in 1b and 1c.

## Getting the Sources in

Needs Docker, [uv](https://docs.astral.sh/uv/) and an [OpenRouter](https://openrouter.ai) API key.

```bash
cp .env.example .env                                   # add your OPENROUTER_API_KEY
docker compose up -d postgres                          # Postgres with pgvector on port 5433
cd backend
uv run compliance-advisor-fetch --source eu-dora       # download one Source into data/raw/
uv run compliance-advisor-ingest --dry-run             # load and cut only; no key, no database
uv run compliance-advisor-ingest                       # embed and store every downloaded Source
```

`compliance-advisor-fetch --all` downloads every Source. `compliance-advisor-ingest --source <id>` re-indexes one Source: its old Passages are deleted first, so running it again never creates duplicates.

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
