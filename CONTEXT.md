# Compliance Advisor

A regulatory information assistant for compliance professionals at financial firms supervised in Germany: banks, insurers, payment and e-money institutions, crypto-asset service providers and fintechs. EU financial regulation applies to these firms directly, so EU texts, German acts and BaFin's supervisory practice sit side by side in one Corpus.

> **Not legal advice.** The Compliance Advisor gives general regulatory information only. It does not replace a qualified lawyer or the Firm's own compliance assessment.

## Language

### People and firms

**Compliance Officer**:
The person asking a question, whatever their job title: compliance, risk, legal, product or management.
_Avoid_: User, client, customer, end user

**Firm**:
The regulated financial entity a question is about, supervised in Germany.
_Avoid_: Company, institution, bank, entity

**Customer**:
A customer of the Firm, for example the subject of a know-your-customer check. Never the person using the app.
_Avoid_: Client, end user

### Sources

**Source**:
One regulatory document the Corpus holds: an EU regulation, a technical standard, a German act or a BaFin circular. Each Source has exactly one Regime, one Regulatory Layer and one official language.
_Avoid_: Document, dataset, file, law (when the document is meant)

**Source Registry**:
The editable list of every Source the Corpus should hold, with where each one comes from.
_Avoid_: Source list, config, dataset

**Corpus**:
The ingested, searchable content of every Source in the Source Registry at a given moment.
_Avoid_: Knowledge base, database, index (in domain talk)

**Passage**:
One indexed piece of a Source: the unit that is retrieved and cited.
_Avoid_: Chunk (in domain talk), document, snippet

**Regime**:
A body of rules referred to as one unit, such as DORA, anti-money laundering or payment services. A Regime spans several Regulatory Layers.
_Avoid_: Law, framework, topic, area

**Regulatory Layer**:
Where a Source sits in the stack of rules that bind a Firm: EU Level 1 (regulations and directives), EU Level 2 (delegated and implementing acts, technical standards), EU Level 3 (guidelines and Q&As of EBA, EIOPA and ESMA), National Law (German acts) or Supervisory Practice (BaFin circulars, FAQs and interpretive notes).
_Avoid_: Tier, hierarchy, level (on its own), jurisdiction

### Answers

**Guidance**:
What a provision requires, whom it applies to, what the supervisor expects and the steps Firms typically take, stated from the Sources. It is never a judgement on a specific Firm's case.
_Avoid_: Legal advice, opinion, recommendation

**Citation**:
A reference from an answer to one Passage, shown as [n].
_Avoid_: Reference, footnote, link

**Answer Model**:
The language model that writes the answer the Compliance Officer reads.
_Avoid_: LLM, the model, chat model
