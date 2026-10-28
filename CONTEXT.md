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

**Compliance Function**:
The organisational unit a Firm must maintain to identify and manage its compliance risk, as required for banks by MaRisk and for insurers by Solvency II.
_Avoid_: Compliance department, compliance team

**Firm Profile**:
The stated facts about a Firm that decide which rules apply to it: its type (for example significant bank, primary insurer, reinsurer), its size class and its activities.
_Avoid_: Settings, company profile, persona

**Account**:
A Compliance Officer's login, holding their Firm Profile and their own answers. Optional: without one, the Compliance Officer works as a guest.
_Avoid_: User (in domain talk), profile (when the Firm Profile is meant)

**Operator**:
The person who runs the Compliance Advisor: watches how it performs and starts Update Runs. Sees figures and technical data across all Accounts, never question texts or answers.
_Avoid_: Admin, administrator, superuser

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

**Update Run**:
One check of every Source in the Source Registry for a new version, loading again only the Sources whose text changed. Runs on a schedule or when an Operator starts it.
_Avoid_: Sync, refresh, crawl, re-ingest (in domain talk)

**Change Record**:
The record of one Source changing in an Update Run: its old and new version and how many Provisions were added, changed or removed.
_Avoid_: Changelog, diff, update log

**Passage**:
One indexed piece of a Source: the unit that is retrieved and cited.
_Avoid_: Chunk (in domain talk), document, snippet

**Obligation**:
A duty a provision imposes on a Firm, with its addressee, the action required, a deadline where one applies, and the provision it comes from.
_Avoid_: Requirement, rule, duty (when this is meant)

**Provision**:
The smallest citable unit of a Source: an article, a paragraph (§) or a numbered section of a guideline.
_Avoid_: Clause, rule, section (when a law is meant)

**Legal Status**:
Where a Source stands: in force, applicable from a later date, or a pending proposal that is not yet law.
_Avoid_: Validity, version

**Milestone**:
A dated event in a Regime's life that matters to a Firm, such as the date from which a regulation applies.
_Avoid_: Deadline (unless an Obligation's own due date is meant), event

**Regime**:
A body of rules referred to as one unit, such as DORA, anti-money laundering, Solvency II or the AI Act. A Regime spans several Regulatory Layers.
_Avoid_: Law, framework, topic, area

**Regulatory Layer**:
Where a Source sits in the stack of rules that bind a Firm: EU Level 1 (regulations and directives), EU Level 2 (delegated and implementing acts, technical standards), EU Level 3 (guidelines and Q&As of EBA, EIOPA and ESMA), National Law (German acts) or Supervisory Practice (BaFin circulars, FAQs and interpretive notes).
_Avoid_: Tier, hierarchy, level (on its own), jurisdiction

### Answers

**Pre-Check**:
Everything that happens to a question before the search: personal data is removed, then the question is screened for attempts to manipulate the Compliance Advisor and for topics outside financial regulation.
_Avoid_: Firewall, guardrail, filter

**Refusal**:
The Compliance Advisor declining a question the Pre-Check did not let through, with the reason: a manipulation attempt or a topic outside financial regulation. A question on financial regulation that the Corpus does not cover is not refused; it gets a coverage notice instead.
_Avoid_: Block, rejection, error

**Rule Check**:
A check written in code that applies rules taken from the Sources to facts the Compliance Officer stated, and names the Provision that decides its result. It never fills in a missing fact; it reports it as missing.
_Avoid_: AI check, calculator, tool (in domain talk)

**Guidance**:
What a provision requires, whom it applies to, what the supervisor expects and the steps Firms typically take, stated from the Sources. It is never a judgement on a specific Firm's case.
_Avoid_: Legal advice, opinion, recommendation

**Citation**:
A reference from an answer to one Passage, shown as [n].
_Avoid_: Reference, footnote, link

**Search Strategy**:
How Passages are found for a question: by meaning alone (vector search) or by meaning and exact words together (hybrid search). Chosen per question and recorded with the answer.
_Avoid_: Retriever, search mode, RAG strategy

**Answer Trace**:
The saved record of every step from question to answer: what the pre-check removed, which Passages each search found and with what score, which were kept, which Rule Checks ran, and which Answer Model wrote the answer at what cost.
_Avoid_: Debug info, log, pipeline view

**Answer Model**:
The language model that writes the answer the Compliance Officer reads.
_Avoid_: LLM, the model, chat model

**Blind Spot**:
A Source that applies to the Firm Profile, according to the applicability Rule Check, but that none of the Account's answers drew on.
_Avoid_: Gap, coverage gap, missing topic
