"""Rule-check tools the Answer Model can call.

Each tool is plain code: the rules are written out from the Sources (cited in every result),
so thresholds, dates and classifications never depend on the model. A tool never guesses a
missing fact; it lists what is missing instead.
"""

import json
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from .profile import BANKS, INSURERS, PAYMENT_FIRMS, Activity, FirmProfile, FirmType, SizeClass
from .registry import Source

# --- Provision references --------------------------------------------------------------------


class Ref(BaseModel):
    provision: str  # "Art. 2 DORA", "§ 2 GwG", "AT 2.1 MaRisk"
    link: str = ""


class ProvisionLinks:
    """Finds the link of a Provision label. `lookup` returns the indexed link or None; if the
    label is not indexed, the link falls back to the Source's reading page."""

    def __init__(self, sources: list[Source], lookup: Callable[[str], str | None] | None = None):
        self.sources = sources
        self.lookup = lookup or (lambda label: None)

    def ref(self, label: str) -> Ref:
        link = self.lookup(label)
        if not link:
            source = next((s for s in self.sources if label.endswith(" " + s.short_title)), None)
            link = source.link if source else ""
        return Ref(provision=label, link=link)

    def refs(self, *labels: str) -> list[Ref]:
        return [self.ref(label) for label in labels]


# --- 1. Applicability check ------------------------------------------------------------------

Applies = Literal["yes", "no", "check", "later", "not_in_corpus"]


class RegimeFinding(BaseModel):
    regime: str
    sources: list[str]
    applies: Applies
    reason: str
    provisions: list[Ref]


class ApplicabilityResult(BaseModel):
    firm_profile: str
    findings: list[RegimeFinding]
    missing: list[str]
    note: str = (
        "Rule check against the Sources in the Corpus; it does not cover national exemptions "
        "or individual supervisory decisions."
    )


def check_applicability(profile: FirmProfile, links: ProvisionLinks) -> ApplicabilityResult:
    t, size, acts = profile.firm_type, profile.size, set(profile.activities)
    findings: list[RegimeFinding] = []
    missing: list[str] = []

    def add(regime, sources, applies, reason, *labels):
        findings.append(
            RegimeFinding(
                regime=regime,
                sources=sources,
                applies=applies,
                reason=reason,
                provisions=links.refs(*labels),
            )
        )

    # DORA
    dora = ["DORA", "Delegated Regulation (EU) 2024/1772", "Delegated Regulation (EU) 2025/301"]
    dora_point = {
        "significant_bank": "(a) credit institutions",
        "less_significant_bank": "(a) credit institutions",
        "payment_institution": "(b) payment institutions",
        "e_money_institution": "(d) electronic money institutions",
        "crypto_asset_service_provider": "(f) crypto-asset service providers",
        "primary_insurer": "(n) insurance and reinsurance undertakings",
        "insurance_group": "(n) insurance and reinsurance undertakings",
        "reinsurer": "(n) insurance and reinsurance undertakings",
    }[t]
    if t in INSURERS and size == "small":
        add(
            "DORA",
            dora,
            "check",
            "Insurers are in scope (Art. 2(1)(n)), but small undertakings excluded from Solvency II "
            "by Art. 4 Solvency II are also excluded from DORA (Art. 2(3)(b)). Check the Art. 4 thresholds.",
            "Art. 2 DORA",
            "Art. 4 Solvency II",
        )
    else:
        add("DORA", dora, "yes", f"Art. 2(1) DORA lists {dora_point}.", "Art. 2 DORA")

    # Anti-money laundering: GwG now, AMLR from 10 July 2027
    aml_now = ["GwG", "BaFin AuA GwG"]
    if t in BANKS:
        add(
            "AML",
            aml_now,
            "yes",
            "Credit institutions are obliged entities (§ 2 Abs. 1 Nr. 1 GwG).",
            "§ 2 GwG",
        )
    elif t in PAYMENT_FIRMS:
        add(
            "AML",
            aml_now,
            "yes",
            "Payment and e-money institutions are obliged entities (§ 2 Abs. 1 Nr. 3 GwG).",
            "§ 2 GwG",
        )
    elif t == "crypto_asset_service_provider":
        add(
            "AML",
            aml_now,
            "yes",
            "Crypto-asset service providers are obliged entities (§ 2 Abs. 1 Nr. 2 GwG).",
            "§ 2 GwG",
        )
    elif t == "reinsurer":
        add(
            "AML",
            aml_now,
            "no",
            "§ 2 Abs. 1 Nr. 7 GwG covers direct insurance undertakings (Art. 13 Nr. 1 Solvency II) only "
            "insofar as they offer life insurance, accident insurance with premium refund or loans; "
            "reinsurance is not listed.",
            "§ 2 GwG",
        )
    elif "life_insurance" in acts:
        add(
            "AML",
            aml_now,
            "yes",
            "Insurers are obliged entities insofar as they offer life insurance (§ 2 Abs. 1 Nr. 7 Buchst. a GwG).",
            "§ 2 GwG",
        )
    elif acts:
        add(
            "AML",
            aml_now,
            "check",
            "Insurers are obliged entities only for life insurance, accident insurance with premium refund "
            "or loans (§ 2 Abs. 1 Nr. 7 GwG); no life business is stated in the Firm Profile.",
            "§ 2 GwG",
        )
    else:
        add(
            "AML",
            aml_now,
            "check",
            "Depends on whether the insurer offers life insurance (§ 2 Abs. 1 Nr. 7 GwG).",
            "§ 2 GwG",
        )
        missing.append("whether the Firm offers life insurance")
    if not (t == "reinsurer" or (t in INSURERS and "life_insurance" not in acts)):
        add(
            "AML (from 10 July 2027)",
            ["AMLR"],
            "later",
            "The AMLR applies from 10 July 2027 (Art. 90) to credit and financial institutions, including "
            "life insurers (Art. 3, Art. 2 'financial institution').",
            "Art. 3 AMLR",
            "Art. 90 AMLR",
        )

    # Payments
    if t == "payment_institution":
        add(
            "Payments",
            ["ZAG"],
            "yes",
            "Payment institutions are payment service providers (§ 1 Abs. 1 Nr. 1 ZAG).",
            "§ 1 ZAG",
        )
    elif t == "e_money_institution":
        add(
            "Payments",
            ["ZAG"],
            "yes",
            "E-money institutions are payment service providers (§ 1 Abs. 1 Nr. 2 ZAG).",
            "§ 1 ZAG",
        )
    elif t in BANKS:
        applies = "yes" if "payment_services" in acts else "check"
        add(
            "Payments",
            ["ZAG"],
            applies,
            "CRR credit institutions are payment service providers under § 1 Abs. 1 Nr. 3 ZAG when they "
            "provide payment services; rules addressed to all payment service providers apply.",
            "§ 1 ZAG",
        )
    else:
        add(
            "Payments",
            ["ZAG"],
            "no",
            "The Firm type is not a payment service provider under § 1 Abs. 1 ZAG.",
            "§ 1 ZAG",
        )

    # Insurance supervision
    insurance = ["Solvency II", "Delegated Regulation (EU) 2015/35", "VAG", "MaGo", "IDD"]
    if t in INSURERS:
        if size == "small":
            add(
                "Insurance",
                insurance,
                "check",
                "Small undertakings below all thresholds of Art. 4 Solvency II are outside Solvency II and "
                "fall under the rules for small insurers (§ 211 VAG); MaGo addresses Solvency II undertakings.",
                "Art. 4 Solvency II",
                "§ 211 VAG",
            )
        else:
            add(
                "Insurance",
                insurance,
                "yes",
                "Solvency II, its Delegated Regulation, the VAG and MaGo govern insurance and reinsurance "
                "undertakings; the IDD covers insurance and reinsurance distribution (Art. 1 IDD).",
                "Art. 2 Solvency II",
                "Art. 1 IDD",
                "§ 1 VAG",
            )
    else:
        add(
            "Insurance",
            insurance,
            "no",
            "The Firm is not an insurance or reinsurance undertaking.",
            "Art. 2 Solvency II",
        )

    # Banking supervision
    banking = ["CRR", "CRD", "KWG"]
    if t == "significant_bank":
        add(
            "Banking",
            banking,
            "yes",
            "Prudential rules for credit institutions apply (CRR, CRD, KWG).",
            "Art. 1 CRR",
            "§ 1 KWG",
        )
        add(
            "Banking: MaRisk",
            ["MaRisk"],
            "no",
            "MaRisk does not apply to significant institutions under direct ECB supervision (AT 2.1 MaRisk); "
            "ECB guides apply instead, which are not in the Corpus.",
            "AT 2.1 MaRisk",
        )
    elif t == "less_significant_bank":
        add(
            "Banking",
            banking + ["MaRisk"],
            "yes",
            "Prudential rules for credit institutions apply; MaRisk applies to institutions not under "
            "direct ECB supervision (AT 2.1 MaRisk).",
            "Art. 1 CRR",
            "§ 1 KWG",
            "AT 2.1 MaRisk",
        )
    else:
        add(
            "Banking",
            banking + ["MaRisk"],
            "no",
            "The Firm is not a credit institution.",
            "Art. 1 CRR",
        )

    # Digital
    add(
        "Data protection",
        ["GDPR"],
        "yes",
        "The GDPR applies to the processing of personal data of customers, employees and contacts (Art. 2 GDPR).",
        "Art. 2 GDPR",
    )
    ai_uses = sorted(a for a in acts if a.startswith("ai_"))
    if ai_uses:
        high = [a for a in ai_uses if a in ("ai_credit_scoring", "ai_insurance_pricing")]
        reason = (
            "Using AI systems makes the Firm a deployer: AI literacy duties apply (Art. 4 AI Act)."
        )
        if high:
            reason += (
                " Credit scoring and life or health insurance pricing are high-risk uses (Annex III "
                "point 5(b) and (c)); use the AI Act use-case check for the duties."
            )
        add("AI", ["AI Act"], "yes", reason, "Art. 4 AI Act", "Art. 6 AI Act", "Annex III AI Act")
    else:
        add(
            "AI",
            ["AI Act"],
            "check",
            "Depends on whether the Firm uses AI systems (Art. 2 AI Act).",
            "Art. 2 AI Act",
        )

    if t == "crypto_asset_service_provider":
        add(
            "Crypto-assets",
            ["MiCA"],
            "not_in_corpus",
            "MiCA governs crypto-asset service providers but is not in the Corpus yet.",
        )

    return ApplicabilityResult(firm_profile=profile.describe(), findings=findings, missing=missing)


# --- 2. Compliance timeline --------------------------------------------------------------------


class TimelineEntry(BaseModel):
    date: date
    status: Literal["past", "upcoming"]
    days_from_today: int
    source: str
    regime: str
    what: str
    link: str


class TimelineResult(BaseModel):
    today: date
    entries: list[TimelineEntry]
    regimes: list[str]


def compliance_timeline(
    sources: list[Source],
    today: date,
    regimes: list[str] | None = None,
    upcoming_only: bool = False,
) -> TimelineResult:
    chosen = {r.lower() for r in regimes or []}
    entries = [
        TimelineEntry(
            date=m.date,
            status="past" if m.date < today else "upcoming",
            days_from_today=(m.date - today).days,
            source=s.short_title,
            regime=s.regime,
            what=m.what,
            link=s.link,
        )
        for s in sources
        if not chosen or s.regime in chosen
        for m in s.milestones
        if not upcoming_only or m.date >= today
    ]
    return TimelineResult(
        today=today, entries=sorted(entries, key=lambda e: e.date), regimes=sorted(chosen)
    )


# --- 3. DORA incident classifier ---------------------------------------------------------------


class IncidentFacts(BaseModel):
    critical_services_affected: bool | None = Field(
        None,
        description="Affects ICT supporting critical or important functions, authorised financial services, or is a successful malicious unauthorised access (Art. 6 RTS 2024/1772)",
    )
    malicious_access_possible_data_loss: bool | None = Field(
        None,
        description="Successful, malicious and unauthorised access to network and information systems that may result in data losses",
    )
    clients_affected: int | None = Field(None, description="Number of clients affected")
    clients_affected_percent: float | None = Field(
        None, description="Affected clients as % of all clients using the affected service"
    )
    counterparts_affected_percent: float | None = None
    transactions_affected_percent: float | None = Field(
        None, description="Affected transactions as % of the daily average number"
    )
    transaction_value_affected_percent: float | None = None
    relevant_clients_affected: bool | None = None
    reputational_impact: bool | None = Field(
        None,
        description="Media coverage, repeated complaints, regulatory breach likely, or material client loss likely",
    )
    duration_hours: float | None = Field(None, description="Hours from occurrence to resolution")
    downtime_hours: float | None = Field(
        None,
        description="Hours the service supporting critical or important functions was unavailable",
    )
    member_states_affected: int | None = Field(
        None, description="Number of EU Member States with impact"
    )
    data_impact_on_business: bool | None = Field(
        None,
        description="Impact on availability, authenticity, integrity or confidentiality of data adversely affects business objectives or regulatory compliance",
    )
    costs_eur: float | None = Field(
        None, description="Direct and indirect costs and losses in euro"
    )
    became_aware_at: datetime | None = Field(
        None, description="When the Firm became aware of the incident (ISO 8601)"
    )
    classified_major_at: datetime | None = Field(
        None, description="When the incident was classified as major (ISO 8601)"
    )
    is_credit_institution: bool | None = None


class Criterion(BaseModel):
    criterion: str
    met: bool | None
    detail: str
    provision: Ref


class IncidentResult(BaseModel):
    major: Literal["yes", "no", "undetermined"]
    reason: str
    criteria: list[Criterion]
    missing: list[str]
    deadlines: list[str]
    provisions: list[Ref]


def _any_true(*values: bool | None) -> bool | None:
    if any(v is True for v in values):
        return True
    return None if any(v is None for v in values) else False


def classify_dora_incident(f: IncidentFacts, links: ProvisionLinks) -> IncidentResult:
    rts = "Delegated Regulation (EU) 2024/1772"
    art9 = links.ref(f"Art. 9 {rts}")

    def over(value, limit):
        return None if value is None else value > limit

    criteria = [
        Criterion(
            criterion="clients, financial counterparts and transactions",
            provision=art9,
            met=_any_true(
                over(f.clients_affected_percent, 10),
                over(f.clients_affected, 100_000),
                over(f.counterparts_affected_percent, 30),
                over(f.transactions_affected_percent, 10),
                over(f.transaction_value_affected_percent, 10),
                f.relevant_clients_affected,
            ),
            detail="> 10 % of clients of the service, > 100 000 clients, > 30 % of counterparts, > 10 % of transactions by number or value, or relevant clients (Art. 9(1))",
        ),
        Criterion(
            criterion="reputational impact",
            provision=art9,
            met=f.reputational_impact,
            detail="media, repeated complaints, regulatory breach or material client loss (Art. 9(2), Art. 2)",
        ),
        Criterion(
            criterion="duration and service downtime",
            provision=art9,
            met=_any_true(over(f.duration_hours, 24), over(f.downtime_hours, 2)),
            detail="duration > 24 hours, or downtime > 2 hours for services supporting critical or important functions (Art. 9(3))",
        ),
        Criterion(
            criterion="geographical spread",
            provision=art9,
            met=None if f.member_states_affected is None else f.member_states_affected >= 2,
            detail="impact in two or more Member States (Art. 9(4))",
        ),
        Criterion(
            criterion="data losses",
            provision=art9,
            met=f.data_impact_on_business,
            detail="adverse impact on business objectives or regulatory compliance through data impact (Art. 9(5)(a))",
        ),
        Criterion(
            criterion="economic impact",
            provision=art9,
            met=over(f.costs_eur, 100_000),
            detail="costs and losses > 100 000 euro (Art. 9(6))",
        ),
    ]
    met = [c.criterion for c in criteria if c.met]
    unknown = [c.criterion for c in criteria if c.met is None]
    missing: list[str] = []

    if f.critical_services_affected is False:
        major, reason = (
            "no",
            "Critical services were not affected; a major incident requires this (Art. 8(1)).",
        )
    elif f.malicious_access_possible_data_loss and f.critical_services_affected:
        major, reason = (
            "yes",
            "Critical services affected and malicious unauthorised access that may cause data losses (Art. 8(1)(a), Art. 9(5)(b)).",
        )
    elif f.critical_services_affected and len(met) >= 2:
        major, reason = (
            "yes",
            f"Critical services affected and two or more thresholds met: {', '.join(met)} (Art. 8(1)(b)).",
        )
    elif f.critical_services_affected is None:
        major, reason = (
            "undetermined",
            "Whether critical services were affected is not known (Art. 6, Art. 8(1)).",
        )
        missing.append("whether critical services were affected (Art. 6)")
    elif len(met) + len(unknown) < 2 and f.malicious_access_possible_data_loss is False:
        major, reason = (
            "no",
            f"Fewer than two thresholds can be met (met: {', '.join(met) or 'none'}) (Art. 8(1)(b)).",
        )
    else:
        major, reason = (
            "undetermined",
            f"Met so far: {', '.join(met) or 'none'}; two are needed (Art. 8(1)(b)).",
        )
    if major == "undetermined":
        missing += [f"facts for: {c}" for c in unknown]
        if f.malicious_access_possible_data_loss is None:
            missing.append(
                "whether there was malicious unauthorised access that may cause data losses"
            )

    deadlines: list[str] = []
    if major == "yes":
        deadlines = [
            "Initial notification: as early as possible, within 4 hours of classification as major and no later than 24 hours after becoming aware (Art. 5(1)(a) RTS 2025/301); if classified later than 24 hours after awareness, within 4 hours of classification (Art. 5(2)).",
            "Intermediate report: within 72 hours of the initial notification; updated when regular activities are recovered (Art. 5(1)(b)).",
            "Final report: within one month of the latest intermediate report (Art. 5(1)(c)).",
        ]
        if f.became_aware_at and f.classified_major_at:
            limit = f.classified_major_at + timedelta(hours=4)
            if f.classified_major_at <= f.became_aware_at + timedelta(hours=24):
                limit = min(limit, f.became_aware_at + timedelta(hours=24))
            deadlines.insert(
                0, f"Initial notification due by {limit.isoformat(timespec='minutes')}."
            )
        if f.is_credit_institution:
            deadlines.append(
                "Credit institutions cannot move an initial notification or intermediate report due on a weekend or bank holiday to the next working day (Art. 5(5))."
            )
        else:
            deadlines.append(
                "Deadlines on a weekend or bank holiday may move to noon of the next working day, except for credit institutions and other entities named in Art. 5(5) (Art. 5(4))."
            )
        deadlines.append(
            "Report to the competent authority; significant credit institutions report to the national authority, which forwards to the ECB (Art. 19(1) DORA)."
        )

    return IncidentResult(
        major=major,
        reason=reason,
        criteria=criteria,
        missing=missing,
        deadlines=deadlines,
        provisions=links.refs(
            f"Art. 8 {rts}",
            f"Art. 9 {rts}",
            "Art. 5 Delegated Regulation (EU) 2025/301",
            "Art. 19 DORA",
        ),
    )


# --- 4. AI Act use-case check ------------------------------------------------------------------

UseCase = Literal[
    "credit_scoring",
    "life_health_insurance_pricing",
    "fraud_detection",
    "claims_handling",
    "customer_chatbot",
    "recruitment",
    "employee_management",
    "other",
]


class AIUseFacts(BaseModel):
    use_case: UseCase = Field(description="What the AI system is used for")
    role: Literal["provider", "deployer", "both"] = Field(
        "deployer",
        description="provider = develops or has it developed and places it on the market under its own name; deployer = uses it",
    )
    profiles_natural_persons: bool | None = Field(
        None, description="Whether the system profiles natural persons"
    )
    narrow_or_preparatory_task: bool | None = Field(
        None,
        description="Only a narrow procedural, preparatory or human-result-improving task without materially influencing decisions (Art. 6(3))",
    )


class Duty(BaseModel):
    duty: str
    provision: Ref


class AIUseResult(BaseModel):
    risk_class: Literal["high_risk", "possibly_not_high_risk", "transparency", "minimal"]
    reason: str
    duties: list[Duty]
    applies_from: list[str]
    missing: list[str]
    provisions: list[Ref]


def check_ai_act_use_case(f: AIUseFacts, links: ProvisionLinks) -> AIUseResult:
    annex = {
        "credit_scoring": "Annex III point 5(b): creditworthiness evaluation and credit scoring of natural persons",
        "life_health_insurance_pricing": "Annex III point 5(c): risk assessment and pricing for natural persons in life and health insurance",
        "recruitment": "Annex III point 4(a): recruitment and selection",
        "employee_management": "Annex III point 4(b): decisions on work relationships, task allocation, monitoring",
    }.get(f.use_case)
    duties = [
        Duty(
            duty="AI literacy of staff using AI systems, since 2 February 2025",
            provision=links.ref("Art. 4 AI Act"),
        )
    ]
    missing: list[str] = []
    provider = f.role in ("provider", "both")
    deployer = f.role in ("deployer", "both")

    if annex:
        if f.profiles_natural_persons is True or f.narrow_or_preparatory_task is False:
            risk, reason = (
                "high_risk",
                f"Listed in {annex}"
                + (
                    "; it profiles natural persons, so it is always high-risk (Art. 6(3) last subparagraph)."
                    if f.profiles_natural_persons
                    else "; the Art. 6(3) derogation does not apply because it materially influences decisions."
                ),
            )
        elif f.narrow_or_preparatory_task is True and f.profiles_natural_persons is False:
            risk, reason = (
                "possibly_not_high_risk",
                f"Listed in {annex}, but Art. 6(3) may exclude it: a narrow or preparatory task without profiling. The provider must document this assessment and register the system (Art. 6(4), Art. 49(2)).",
            )
        else:
            risk, reason = (
                "high_risk",
                f"Listed in {annex}; treated as high-risk unless the Art. 6(3) derogation is shown.",
            )
            if f.profiles_natural_persons is None:
                missing.append(
                    "whether the system profiles natural persons (decisive under Art. 6(3))"
                )
            if f.narrow_or_preparatory_task is None:
                missing.append("whether it only performs a narrow or preparatory task (Art. 6(3))")
        if risk == "high_risk":
            if deployer:
                duties += [
                    Duty(
                        duty="Use according to the instructions; human oversight by competent persons; relevant input data; monitoring; log retention; inform affected persons (deployer duties)",
                        provision=links.ref("Art. 26 AI Act"),
                    ),
                ]
                if f.use_case in ("credit_scoring", "life_health_insurance_pricing"):
                    duties.append(
                        Duty(
                            duty="Fundamental rights impact assessment before first use (deployers of Annex III point 5(b) and (c) systems)",
                            provision=links.ref("Art. 27 AI Act"),
                        )
                    )
            if provider:
                duties += [
                    Duty(
                        duty="Provider duties: risk management, data governance, technical documentation, conformity assessment, registration",
                        provision=links.ref("Art. 16 AI Act"),
                    ),
                    Duty(
                        duty="Risk management system across the life cycle",
                        provision=links.ref("Art. 9 AI Act"),
                    ),
                ]
        applies = [
            "High-risk rules for Annex III systems apply from 2 December 2027 (Art. 113(c)(i), as amended in 2026)."
        ]
    elif f.use_case == "fraud_detection":
        risk, reason = (
            "minimal",
            "Fraud detection is expressly excluded from the credit-scoring use case (Annex III point 5(b)); no other high-risk category is indicated.",
        )
        applies = ["General application from 2 August 2026 (Art. 113)."]
    elif f.use_case == "customer_chatbot":
        risk, reason = (
            "transparency",
            "A system interacting directly with natural persons must make clear that they are interacting with AI (Art. 50(1), a provider duty).",
        )
        duties.append(
            Duty(
                duty="Inform people that they are interacting with an AI system, unless obvious",
                provision=links.ref("Art. 50 AI Act"),
            )
        )
        applies = [
            "Transparency obligations apply from 2 August 2026 (general application, Art. 113)."
        ]
    else:
        risk, reason = (
            "minimal",
            "The use case is not listed in Annex III; no high-risk classification follows from the Corpus. If it decides on natural persons, check GDPR Art. 22 on automated decisions.",
        )
        applies = ["General application from 2 August 2026 (Art. 113)."]
        if f.use_case == "claims_handling":
            reason += " Claims handling is not an Annex III use; pricing and risk assessment in life and health insurance would be."

    return AIUseResult(
        risk_class=risk,
        reason=reason,
        duties=duties,
        applies_from=applies,
        missing=missing,
        provisions=links.refs("Art. 6 AI Act", "Annex III AI Act", "Art. 113 AI Act"),
    )


# --- LangChain tools for one request --------------------------------------------------------


class ApplicabilityArgs(BaseModel):
    firm_type: FirmType | None = Field(
        None, description="Only if the question names a different firm type than the Firm Profile"
    )
    size: SizeClass | None = None
    activities: list[Activity] | None = None


class TimelineArgs(BaseModel):
    regimes: list[Literal["dora", "aml", "payments", "insurance", "banking", "digital"]] | None = (
        Field(None, description="Regimes to include; omit for all")
    )
    upcoming_only: bool = False


def make_tools(
    profile: FirmProfile | None, sources: list[Source], links: ProvisionLinks, today: date
) -> list[StructuredTool]:
    def applicability(firm_type=None, size=None, activities=None) -> str:
        base = profile.model_dump() if profile else {}
        updates = {
            k: v
            for k, v in {"firm_type": firm_type, "size": size, "activities": activities}.items()
            if v is not None
        }
        if "firm_type" not in {**base, **updates}:
            return json.dumps({"missing": ["firm type: set a Firm Profile or name the firm type"]})
        return check_applicability(FirmProfile(**{**base, **updates}), links).model_dump_json()

    def timeline(regimes=None, upcoming_only=False) -> str:
        return compliance_timeline(sources, today, regimes, upcoming_only).model_dump_json()

    def incident(**facts) -> str:
        return classify_dora_incident(IncidentFacts(**facts), links).model_dump_json()

    def ai_use(**facts) -> str:
        return check_ai_act_use_case(AIUseFacts(**facts), links).model_dump_json()

    return [
        StructuredTool.from_function(
            applicability,
            name="check_applicability",
            args_schema=ApplicabilityArgs,
            description="Which Regimes in the Corpus apply to the Firm (from the Firm Profile), with the deciding provisions. Use for 'does X apply to us' questions.",
        ),
        StructuredTool.from_function(
            timeline,
            name="compliance_timeline",
            args_schema=TimelineArgs,
            description="Dated milestones (entry into force, application dates, versions) of the Sources, past and upcoming. Use for 'when', 'from when', 'deadline' questions.",
        ),
        StructuredTool.from_function(
            incident,
            name="classify_dora_incident",
            args_schema=IncidentFacts,
            description="Classifies an ICT-related incident as major or not under DORA and the RTS 2024/1772 thresholds, and gives the reporting deadlines of RTS 2025/301. Pass only facts stated by the user.",
        ),
        StructuredTool.from_function(
            ai_use,
            name="check_ai_act_use_case",
            args_schema=AIUseFacts,
            description="Risk class of an AI use case under the AI Act (Annex III, Art. 6(3), Art. 50) and the resulting duties and application dates.",
        ),
    ]
