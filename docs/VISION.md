# Compliance Advisor for Financial Services: the target picture

> **Not legal advice.** This project gives general regulatory information only. It does not replace consultation with a qualified lawyer or the firm's own compliance function.

Snapshot of the first planning summary, written 2026-10-20 before the grilling session and kept for re-reading. It is not a spec: the grilling decided otherwise in places, for example no code is reused from other projects, Firms are always supervised in Germany, and the default model is cheaper. Current decisions live in `CONTEXT.md`, `docs/ROADMAP.md` and `docs/adr/`.

## The pitch

A regulatory compliance assistant for compliance officers and product owners at banks, insurers, payment and e-money institutions, crypto-asset service providers and fintechs in the EU and Germany. It answers "what applies to us, what exactly must we do, by when, and where does it say so". Every answer cites the regulation, the delegated technical standard, the supervisory guideline and the BaFin circular in their proper order. BaFin is the German financial supervisor. Same "not legal advice" pattern everywhere as in the Founder Legal Guide.

## What makes it different from the Founder Legal Guide

- **Professional users.** They ask by article number and want obligation-level precision. Exact terminology matters, so hybrid search will probably beat vector-only here, the opposite of the founder result. The A/B setup can prove it.
- **Regulatory layering is the hard problem.** One question stacks Level 1, Level 2 and Level 3 texts plus national law and supervisory practice. Level 1 is the regulation or directive, Level 2 the delegated technical standards, Level 3 the EBA, EIOPA and ESMA guidelines. Then come German acts like KWG and GwG, then BaFin circulars. Source Tier becomes a "Regulatory Layer" field, and answers show the stack.
- **Proportionality.** Obligations scale with entity type and size, so a Firm Profile replaces the Founder Profile: licence type, home state, size class, activities such as payments, lending, crypto, AI credit scoring and cloud outsourcing, and retail versus corporate customers.
- **Deadlines dominate.** Most questions are "when does this apply to us", so Legal Status and the timeline tool move from extras to the centre.
- **Audit trail.** Every answer is stored with the exact Source versions it cited, so an officer can later show what the tool said and on which text. Fingerprinting in the update pipeline makes that cheap.

## Corpus, cut for two weeks

| Regime | Covers | German layer | Status |
|---|---|---|---|
| DORA with its technical standards | ICT risk, incident reporting, third-party register | BaFin DORA FAQs | applies since 17 Jan 2025 |
| AML package: AMLD, new AMLR and AMLA | KYC, due diligence levels, reporting | GwG, BaFin interpretive notes | AMLR applies 10 Jul 2027 |
| PSD2, with PSD3 and PSR coming | payment services, strong customer authentication | ZAG | PSD3 pending |
| MiCA | crypto-asset services, stablecoins | KMAG | applies since 30 Dec 2024 |
| Solvency II and IDD | insurer governance, distribution, product oversight | VAG | amendments apply 30 Jan 2027 |
| CRR and CRD | capital, governance, outsourcing | KWG, MaRisk | CRR3 applies since 1 Jan 2025 |
| Cross-cutting: GDPR, AI Act, Consumer Credit Directive 2, EU sanctions | automated decisions, credit scoring, consumer credit, screening | BDSG | CCD2 applies 20 Nov 2026, AI Act high-risk date under revision |

Tier 2 holds EBA, EIOPA and ESMA guidelines, FATF, ECB guides and BaFin circulars. The EUR-Lex and gesetze-im-internet adapters carry over from the Founder Legal Guide. BaFin, the supervisory authorities and FATF publish PDFs and HTML, which a pinned-web adapter handles.

## Tools (the three-tool requirement)

1. **Applicability check.** Firm Profile in, list of applicable regimes with proportionality notes out.
2. **Compliance timeline.** Dated milestones per regime, filtered for the firm.
3. **DORA incident classifier.** Incident facts in. Major or not major per the classification standard, plus the reporting clock with its initial, intermediate and final deadlines. The best candidate for visualising tool results.
4. **AML due-diligence level.** Customer type, country risk, politically exposed person status and product in. Simplified, standard or enhanced due diligence plus GwG thresholds out.
5. **Sanctions screening** against the EU consolidated list and the OFAC list, via the OpenSanctions API or downloaded lists. The real API integration.
6. **Source currency check**, ported from the Founder Legal Guide.

All of them are also exposed through an MCP server.

## Domain-specific safety

- **Escalation Triggers.** Suspicion of money laundering goes to the money-laundering officer and the Financial Intelligence Unit. Major incidents go to the incident process. Enforcement or investigations go to counsel.
- **Refusals.** Structuring below thresholds, circumventing sanctions, or tipping off a customer about a report.
- **Customer data.** A pre-check strips names, IBANs and account numbers before the model sees the question.
- Prompt-injection screening of ingested pages, audit log, rate limit and admin token.

## UI and evaluation

On top of the chat: the Firm Profile questionnaire, obligation cards stating who, what, by when and what evidence, a regulatory calendar fed by the timeline tool, an incident-report helper page, and audit log export. The Golden Set spans a Coverage Map of Regime by Entity type, with retrieval and answer metrics, plus a check that answers order the layers correctly.

## Effort split and reuse

Backend skeleton, retrieval strategies, index backends, update pipeline, admin, MCP server and the frontend shell can carry over from the Founder Legal Guide. New work is the source registry, glossary and scope docs, the tools, the profile and obligation-card rendering. Most of the effort goes into corpus curation and the Golden Set, not code.

---

_This is general regulatory information, not legal advice. It does not replace consultation with a qualified lawyer._
