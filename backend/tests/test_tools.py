"""Rule-check tools, the pre-check and the tool round, without network or database."""

import json
from datetime import date, datetime

from langchain_core.documents import Document
from langchain_core.messages import AIMessage

from compliance_advisor.answer import AnswerService
from compliance_advisor.precheck import redact
from compliance_advisor.profile import PRESETS, FirmProfile
from compliance_advisor.registry import Milestone, Source
from compliance_advisor.retriever import RetrievedPassage
from compliance_advisor.tools import (
    AIUseFacts,
    IncidentFacts,
    ProvisionLinks,
    check_ai_act_use_case,
    check_applicability,
    classify_dora_incident,
    compliance_timeline,
    make_tools,
)

AMLR = Source(
    id="eu-amlr",
    title="AMLR",
    short_title="AMLR",
    regime="aml",
    layer="eu_level_1",
    issuer="EP",
    language="en",
    format="html",
    url="u",
    display_url="https://eur-lex/amlr",
    legal_status="applies_later",
    milestones=[
        Milestone(date=date(2024, 7, 9), what="Entry into force"),
        Milestone(date=date(2027, 7, 10), what="Applies"),
    ],
)
LINKS = ProvisionLinks(
    [AMLR], lambda label: {"§ 2 GwG": "https://gii/gwg_2017/__2.html"}.get(label)
)


def findings(profile: FirmProfile) -> dict[str, str]:
    return {f.regime: f.applies for f in check_applicability(profile, LINKS).findings}


def test_applicability_for_a_significant_bank_excludes_marisk():
    result = findings(FirmProfile(firm_type="significant_bank", activities=["payment_services"]))
    assert result["DORA"] == "yes" and result["AML"] == "yes" and result["Banking"] == "yes"
    assert result["Banking: MaRisk"] == "no" and result["Payments"] == "yes"
    assert result["Insurance"] == "no"


def test_applicability_for_insurers_depends_on_life_business_and_size():
    assert findings(FirmProfile(firm_type="reinsurer"))["AML"] == "no"
    assert (
        findings(FirmProfile(firm_type="primary_insurer", activities=["life_insurance"]))["AML"]
        == "yes"
    )
    assert (
        findings(FirmProfile(firm_type="primary_insurer", activities=["non_life_insurance"]))["AML"]
        == "check"
    )
    small = findings(FirmProfile(firm_type="primary_insurer", size="small"))
    assert small["DORA"] == "check" and small["Insurance"] == "check"


def test_applicability_cites_indexed_links_and_falls_back_to_the_source():
    result = check_applicability(FirmProfile(firm_type="significant_bank"), LINKS)
    aml = next(f for f in result.findings if f.regime == "AML")
    assert aml.provisions[0].link == "https://gii/gwg_2017/__2.html"
    later = next(f for f in result.findings if f.regime.startswith("AML (from"))
    assert later.applies == "later" and later.provisions[0].link == "https://eur-lex/amlr"


def test_every_preset_is_checked_without_errors():
    for preset in PRESETS:
        assert check_applicability(preset.profile, LINKS).findings


def test_timeline_marks_past_and_upcoming_milestones():
    result = compliance_timeline([AMLR], today=date(2026, 10, 22), upcoming_only=False)
    assert [(e.date.year, e.status) for e in result.entries] == [(2024, "past"), (2027, "upcoming")]
    upcoming = compliance_timeline([AMLR], today=date(2026, 10, 22), upcoming_only=True)
    assert len(upcoming.entries) == 1 and upcoming.entries[0].days_from_today == 261


def test_incident_with_two_thresholds_is_major_and_gets_deadlines():
    facts = IncidentFacts(
        critical_services_affected=True,
        malicious_access_possible_data_loss=False,
        downtime_hours=3,
        clients_affected=150_000,
        became_aware_at=datetime(2026, 10, 22, 8, 0),
        classified_major_at=datetime(2026, 10, 22, 10, 0),
    )
    result = classify_dora_incident(facts, LINKS)
    assert result.major == "yes"
    assert result.deadlines[0] == "Initial notification due by 2026-10-22T14:00."


def test_incident_classified_late_gets_four_hours_from_classification():
    facts = IncidentFacts(
        critical_services_affected=True,
        malicious_access_possible_data_loss=True,
        became_aware_at=datetime(2026, 10, 20, 8, 0),
        classified_major_at=datetime(2026, 10, 22, 9, 30),
    )
    result = classify_dora_incident(facts, LINKS)
    assert result.major == "yes" and result.deadlines[0].endswith("2026-10-22T13:30.")


def test_incident_without_enough_facts_is_undetermined_and_lists_them():
    result = classify_dora_incident(
        IncidentFacts(critical_services_affected=True, downtime_hours=3), LINKS
    )
    assert result.major == "undetermined"
    assert any("economic impact" in m for m in result.missing)
    assert (
        classify_dora_incident(IncidentFacts(critical_services_affected=False), LINKS).major == "no"
    )


def test_ai_act_check_classifies_financial_use_cases():
    pricing = check_ai_act_use_case(
        AIUseFacts(use_case="life_health_insurance_pricing", profiles_natural_persons=True), LINKS
    )
    assert pricing.risk_class == "high_risk"
    assert any("Art. 27" in d.provision.provision for d in pricing.duties)  # impact assessment
    assert "2 December 2027" in pricing.applies_from[0]
    assert (
        check_ai_act_use_case(AIUseFacts(use_case="fraud_detection"), LINKS).risk_class == "minimal"
    )
    assert (
        check_ai_act_use_case(AIUseFacts(use_case="customer_chatbot"), LINKS).risk_class
        == "transparency"
    )
    unknown = check_ai_act_use_case(AIUseFacts(use_case="credit_scoring"), LINKS)
    assert unknown.risk_class == "high_risk" and unknown.missing


def test_precheck_removes_personal_data_but_keeps_amounts_and_provisions():
    question, removed = redact(
        "IBAN DE89 3704 0044 0532 0130 00, max@example.com, +49 89 1234 5678; costs 120 000 EUR, Art. 19 DORA"
    )
    assert removed == ["IBAN", "email address", "phone number"]
    assert "DE89" not in question and "example.com" not in question and "1234" not in question
    assert "120 000 EUR" in question and "Art. 19 DORA" in question


class ScriptedModel:
    """Answers the first call with a tool call and the second with text."""

    def __init__(self):
        self.calls = []

    def bind_tools(self, tools, **kwargs):
        self.calls.append(kwargs)
        return self

    def invoke(self, messages):
        if len(self.calls) == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "classify_dora_incident",
                        "id": "c1",
                        "args": {"critical_services_affected": False},
                    }
                ],
                usage_metadata={"input_tokens": 100, "output_tokens": 10, "total_tokens": 110},
            )
        assert messages[-1].type == "tool"
        return AIMessage(
            content="Not major [1] (rule check: classify_dora_incident).",
            usage_metadata={"input_tokens": 200, "output_tokens": 20, "total_tokens": 220},
        )


class OnePassage:
    def retrieve(self, question, k):
        meta = {
            "passage_id": "p1",
            "source_id": "eu-dora",
            "source_title": "DORA",
            "short_title": "DORA",
            "regime": "dora",
            "layer": "eu_level_1",
            "issuer": "EP",
            "language": "en",
            "url": "u",
        }
        return [RetrievedPassage(Document(page_content="Art. 19 text", metadata=meta), 0.8)]


def test_tool_round_runs_the_tool_once_and_answers_with_its_result():
    model = ScriptedModel()
    service = AnswerService(
        OnePassage(),
        model,
        "m",
        top_k=6,
        tools=lambda profile, today: make_tools(profile, [AMLR], LINKS, today),
    )
    response = service.ask("Is it major? Contact max@example.com")
    assert model.calls[1] == {"tool_choice": "none"}  # the second call may not call tools again
    assert response.tools[0].name == "classify_dora_incident"
    assert response.tools[0].result["major"] == "no"
    assert response.redactions == ["email address"] and "example.com" not in response.question
    assert response.usage.input_tokens == 300 and response.cited == [1]
    assert json.loads(response.model_dump_json())["tools"][0]["arguments"] == {
        "critical_services_affected": False
    }
