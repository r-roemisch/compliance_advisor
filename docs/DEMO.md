# Demo: five minutes

> **Not legal advice.** The Compliance Advisor gives general regulatory information only.

For a compliance audience at a bank or insurer. Every question below was tried with GPT-6 Luna; answers take 10 to 30 seconds and cost well under one cent each. Start with the app running at http://localhost:3010 in German, light theme, no Firm Profile.

## Before you start

- Open the page once and ask any question, so the first answer is not slowed down by start-up.
- Keep these questions in a text file to paste; typing costs time.
- Do not use Mistral Large 4 live unless asked: it takes about a minute per answer. Mention it instead (step 6).

## 1. The problem (30 seconds)

"A compliance function in Germany answers to three layers at once: EU regulations and their technical standards, German acts, and BaFin's interpretation. Finding the decisive provision, and knowing whether it already applies, takes hours. This tool answers from 18 official sources and shows exactly where each statement comes from."

Point at the start screen: the notice at the bottom, the example questions, the **Quellen** tab with legal status and download date of each source.

## 2. A DORA incident, with a deadline (90 seconds)

Set the Firm Profile: **Firmenprofil → Bedeutendes Institut (EZB-Aufsicht) → Profil übernehmen**. Ask:

```
Unser Online-Banking war heute 3 Stunden ausgefallen, rund 150.000 Kunden waren betroffen, kritische Dienste waren betroffen. Bemerkt um 08:00, als schwerwiegend eingestuft um 10:00. Ist das ein schwerwiegender Vorfall nach DORA und bis wann müssen wir melden?
```

Point out while it runs: the steps appear live, the search step names the sources it found, the answer is written in front of you.

Then:
- The **rule check card**: "major: yes", the two thresholds met (more than 100,000 clients, more than 2 hours downtime), the initial notification due by 14:00. "This is computed in code from Art. 8 and 9 of the classification standard and Art. 5 of the reporting standard, not guessed by the model."
- Click a **citation chip**: the passage on the right lights up. Click **Quelle öffnen**: EUR-Lex opens at Article 19.
- The **layer glyph** next to each passage: binding EU law solid, BaFin practice outlined.

## 3. Obligations for the project plan (45 seconds)

Under the answer, click **Pflichten extrahieren**. A table appears: addressee, obligation, deadline, provision with link. Click **Als CSV herunterladen** and open it in Excel. "This is the start of a Pflichtenkataster, built from the cited provisions only."

## 4. AI in insurance pricing (60 seconds)

Set the Firm Profile to **Lebensversicherer, mittelgroß**. Ask:

```
Wir wollen ein KI-Modell für die Tarifierung in der Lebensversicherung einsetzen. Ist das Hochrisiko-KI und welche Pflichten haben wir?
```

Point out: the AI Act rule check classifies it as high-risk (Annex III point 5(c)), lists the duties including the fundamental rights impact assessment (Art. 27), says from when they apply (2 December 2027, as amended in 2026), and names the facts it still needs, such as whether the model profiles natural persons. "It does not invent missing facts; it asks for them."

## 5. What applies to us, and what is coming (45 seconds)

Switch the language to **EN**, keep the profile, and ask:

```
Which regimes apply to us?
```

The applicability card lists each regime with applies / does not apply / check, the reason, and the deciding provision. For a reinsurer (switch the preset) the anti-money-laundering rules drop out, because § 2 GwG covers insurers only for life business.

Open the **Timeline** tab: the dated milestones for this profile, such as the AMLR from 10 July 2027.

## 6. Trust (45 seconds)

- **Verlauf / History**: every answer is stored with the exact source versions it used. Open one and export it as **Markdown** or **JSON**, or print it as PDF.
- Paste an IBAN into a question: the answer starts with "Removed before sending: IBAN".
- The **model** menu: Mistral Large 4 runs on Mistral AI's servers in the EU, for firms that require it.
- The partial-coverage note: when the sources do not answer everything, the page says so above the answer.

## 7. How good is it? (30 seconds)

Open `docs/EVALUATION.md`: 25 test questions, retrieval measured for five set-ups. Cutting the sources per provision raised the share of questions where the right provision is among the six passages from 77 % to 100 % on the first six sources; a feature that did not help (a cap per source) was measured and switched off.

## If something goes wrong

| Symptom | Do |
|---|---|
| "Das Backend ist nicht erreichbar" | `docker compose up -d` in the project folder, wait 20 seconds |
| An answer takes over a minute | Check the model menu is on GPT-6 Luna |
| The incident check says "offen" | The question did not say whether critical services were affected; use the question above verbatim |
| An answer misses an obvious provision | Name it in the question, for example "§ 25a KWG": named provisions are looked up directly |
