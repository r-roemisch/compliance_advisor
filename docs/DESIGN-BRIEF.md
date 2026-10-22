# Design brief

Input for the design session (day 3 of the submission plan in `docs/ROADMAP.md`). It describes what the interface must show; the design decides how. Field names match the API in `backend/src/compliance_advisor/schemas.py`.

## Audience and impression

Compliance Officers and the Compliance Function at large banks and insurers supervised in Germany, such as insurance groups, reinsurers and significant banks. The interface must feel like a tool a German bank's or insurer's compliance team would trust: calm, precise, dense with information, never playful. German is the default language; English is one switch away.

## Style

- Financial-services professional: like a premium bank intranet or a financial terminal, not a consumer app.
- Navy or slate base, warm grey surfaces, one accent color for interaction; red and amber only for status.
- A sober sans-serif for the interface (for example Inter or IBM Plex Sans); provision references such as "Art. 17(1) DORA" or "§ 10 Abs. 1 GwG" get a distinct treatment.
- Light and dark mode; WCAG AA contrast; full keyboard use.
- Avoid: illustrations, emojis, gradients, messenger-style chat bubbles, anything that looks like a compliance verdict such as "compliant" checkmarks, and real company names or logos.

## What the interface shows

1. **Question and answer.** A question field (3 to 2000 characters), the answer in Markdown with Citations [1] to [6].
2. **Passages.** Six per answer, each with number, short title, Provision label, issuer, Regulatory Layer, language, similarity score, cited or not, Legal Status, "as of" date, and a link to the exact Provision in the official text. Clicking a Citation highlights its Passage, and the other way round.
3. **Regulatory Layer badges.** Distinct and consistent: EU Level 1 (regulation or directive), EU Level 2 (technical standard), EU Level 3 (EBA, EIOPA or ESMA guideline), German national law, BaFin supervisory practice. Binding law must look different from supervisory expectation.
4. **"Not covered".** When the Sources do not answer a question or part of it, the interface shows that prominently, as a normal state, not an error.
5. **Tool results.** Four tools, each result naming the Provision that decides it:
   - Applicability check: which Regimes apply to the Firm Profile, and why.
   - Compliance timeline: dated Milestones, past and upcoming.
   - DORA incident classifier: major or not, with the reporting deadlines.
   - AI Act use-case check: risk class of an AI use such as pricing, credit scoring or claims handling, and the resulting duties.
6. **Firm Profile.** A small dialog: firm type, size class, activities. Presets by firm type only, such as "Insurance group, large", "Reinsurer", "Significant bank (ECB-supervised)". The active profile is visible near the question field.
7. **Obligations.** "Extract Obligations" under an answer or Passage opens a table: addressee, action, deadline, Provision with link, Citation. Exportable as CSV.
8. **Timeline view.** Milestones of all Regimes in the Corpus, filterable by the Firm Profile.
9. **History and audit trail.** A list of past questions; each can be reopened and exported as JSON, Markdown or PDF.
10. **Cost and model.** Per answer: model, tokens and cost in money. A model choice that includes an EU-hosted model.
11. **Pre-check notice.** When the app removed personal data (IBAN, email, phone) from a question, it says so above the answer.
12. **Sources.** The indexed Sources with Legal Status, "as of" date and Passage count.
13. **The permanent notice** below the chat: "This is regulatory information generated from the indexed Sources, not legal advice. Verify against the official text before relying on it." In German: "Dies sind regulatorische Informationen aus den indexierten Quellen, keine Rechtsberatung. Prüfen Sie den amtlichen Text, bevor Sie sich darauf stützen."

## States to design

- Empty start: example questions in German and English, the active Firm Profile, the Sources.
- Waiting: answers take 10 to 30 seconds; show steps such as "searching Sources", "checking with tools", "writing the answer".
- Answer, answer with tool results, answer that is partly or fully "not covered".
- Errors: invalid question, answer model unavailable, database unavailable.

## Prompt for the design tool

```text
Design a web app called "Compliance Advisor": a regulatory research tool for compliance
officers at large banks and insurers supervised in Germany (insurance groups, reinsurers,
ECB-supervised banks). Users ask questions in German or English; answers come from EU
regulations, technical standards, German acts and BaFin guidance, with numbered citations.
German UI by default, English one switch away.

Style: financial-services professional, calm, precise and information-dense, like a premium
bank intranet or a financial terminal. Navy/slate base, warm grey surfaces, one accent color;
red and amber only for status. Sans-serif UI (Inter or IBM Plex Sans) with a distinct
treatment for provision references like "Art. 17(1) DORA" or "§ 10 Abs. 1 GwG". Light and
dark mode, WCAG AA, keyboard friendly. No illustrations, emojis, gradients, chat bubbles,
"compliant" checkmarks, or real company names.

Main screen:
- Question field with the active Firm Profile next to it (e.g. "Reinsurer, large").
- Answer in Markdown with citations [1]-[6]; a prominent "not covered" state.
- Six source passages: number, short title, provision label, issuer, regulatory layer badge,
  language, similarity score, cited/not cited, legal status, "as of" date, link to the exact
  provision. Citation and passage highlight each other.
- Layer badges: EU Level 1, EU Level 2, EU Level 3, German law, BaFin practice; binding law
  visibly different from supervisory expectation.
- Tool result cards: applicability check (which regimes apply and why), compliance timeline
  (milestones), DORA incident classifier (major or not, reporting deadlines), AI Act use-case
  check (risk class and duties). Each names its deciding provision.
- "Extract Obligations" action opening a table: addressee, action, deadline, provision, citation;
  CSV export.
- Per answer: model, tokens, cost in euro or dollar; model picker including an EU-hosted model.
- Notice when personal data (IBAN, email, phone) was removed from the question.
- Side areas: history of past questions with export (JSON, Markdown, PDF); timeline view of
  milestones; list of indexed sources with legal status and "as of" date; Firm Profile dialog
  with presets by firm type.
- A small permanent notice below the chat: not legal advice, verify against the official text.

States: empty start with German and English example questions; waiting (10-30 s, steps
"searching sources" -> "checking with tools" -> "writing the answer"); answer; answer with
tool results; partly or fully not covered; errors (invalid input, model unavailable,
database unavailable).
```
