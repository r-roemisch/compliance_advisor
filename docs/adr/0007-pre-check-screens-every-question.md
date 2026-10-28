# The Pre-Check screens every question with one model check

Every question passes the Pre-Check before the search: personal data is removed locally first, then one short model check screens the question for attempts to manipulate the Compliance Advisor and for topics outside financial regulation. A question that does not pass gets a Refusal with its reason and can be rephrased; there is no "answer anyway", because anyone could press it. A question on financial regulation that the Corpus does not cover is not refused but gets the existing coverage notice, so a Compliance Officer learns that the Corpus has a gap rather than that they asked something forbidden. With an Account, a Refusal is kept in that Account's history, marked as refused; the Operator sees only counts per reason (ADR 0006). The screening runs on GPT-6 Luna, the cheapest Answer Model, because running cost matters for this demo; when the Compliance Officer has chosen Mistral Large 4, Mistral screens instead, so a question meant for an EU-hosted provider never reaches a US one. Decided in the design session of 2026-10-28.

## Considered Options

- **Fixed text patterns only**: free and instant, but miss any rephrased attack.
- **Patterns first, model check only on suspicion**: cheaper per question, but two layers are harder to explain to a bank's reviewer than one.
- **Always screen with EU-pinned Mistral**: keeps every question in the EU, rejected on cost.
- **Always screen with GPT-6 Luna**: cheapest, but would quietly break the promise behind choosing Mistral.

## Consequences

The protection is measured, not asserted: a test set of about 30 manipulation attempts and about 30 legitimate questions that look suspicious ("Can we ignore § 25a KWG if…?") gives two figures, attacks caught and legitimate questions wrongly refused, published in the README together with what the Pre-Check does not protect against, such as kinds of attack the test set does not contain. It is one layer among others already in place: Passages are declared data, not instructions, in the prompt, and every Citation is checked to point at a Passage that exists.
