"""Dashboard analytics: periods, most-cited Provisions, Blind Spots and click-through filters.
No database."""

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from compliance_advisor import analytics, api
from compliance_advisor.registry import Source
from compliance_advisor.tools import RegimeFinding

from .test_accounts import FakeAccounts

TODAY = date(2026, 10, 24)


def record(day: int, *, regimes=(), provisions=(), sources=(), tools=(), obligations=()):
    return {
        "id": f"a{day}-{len(provisions)}",
        "created_at": datetime(2026, 10, day, 9, 0, tzinfo=UTC),
        "question": f"Question of {day} October",
        "model": "m",
        "regimes": list(regimes),
        "tools": list(tools),
        "obligations": list(obligations),
        "provisions": [
            {"provision": p, "title": "", "short_title": "", "layer": "", "link": ""}
            for p in provisions
        ],
        "sources": list(sources),
    }


def source(short_title: str, regime: str) -> Source:
    return Source(
        id=short_title.lower().replace(" ", "-"),
        title=short_title,
        short_title=short_title,
        regime=regime,
        layer="national_law",
        issuer="x",
        language="de",
        format="html",
        url=f"https://example.org/{short_title}",
    )


RECORDS = [  # newest first, as AuditStore.records returns them
    record(24, regimes=["dora"], provisions=["Art. 19 DORA", "Art. 19 DORA"], sources=["DORA"]),
    record(20, regimes=["dora"], provisions=["Art. 19 DORA", "Art. 17 DORA"], sources=["DORA"]),
    record(10, regimes=["banking"], provisions=["§ 25a KWG"], sources=["KWG"]),
    record(1, tools=["check_ai_act_use_case"], regimes=["digital"]),
]


def test_period_keeps_only_recent_questions_and_zero_keeps_all():
    assert len(analytics.in_period(RECORDS, 7, TODAY)) == 2
    assert len(analytics.in_period(RECORDS, 30, TODAY)) == 4
    assert len(analytics.in_period(RECORDS, 0, TODAY)) == 4


def test_activity_has_one_entry_per_day_and_every_question_starts_at_the_first():
    week = analytics.activity(RECORDS, 7, TODAY)
    assert [d["date"] for d in week][:1] == ["2026-10-18"] and len(week) == 7
    assert sum(d["count"] for d in week) == 2
    every = analytics.activity(RECORDS, 0, TODAY)
    assert every[0]["date"] == "2026-10-01" and len(every) == 24


def test_most_cited_counts_each_answer_once_per_provision():
    top = analytics.top_provisions(RECORDS)
    assert [(p["provision"], p["count"]) for p in top] == [
        ("Art. 19 DORA", 2),
        ("Art. 17 DORA", 1),
        ("§ 25a KWG", 1),
    ]


def test_blind_spots_list_applicable_sources_never_asked_about_first():
    sources = [
        source("DORA", "dora"),
        source("KWG", "banking"),
        source("MaRisk", "banking"),
        source("AI Act", "digital"),
        source("GwG", "aml"),
    ]
    findings = [
        RegimeFinding(
            regime="DORA", sources=["DORA", "Not indexed"], applies="yes", reason="", provisions=[]
        ),
        RegimeFinding(
            regime="Banking", sources=["KWG", "MaRisk"], applies="yes", reason="", provisions=[]
        ),
        RegimeFinding(regime="AI", sources=["AI Act"], applies="check", reason="", provisions=[]),
        RegimeFinding(regime="AML", sources=["GwG"], applies="no", reason="", provisions=[]),
    ]
    spots = analytics.blind_spots(RECORDS, findings, sources)
    assert [(s["short_title"], s["questions"]) for s in spots] == [
        ("MaRisk", 0),  # applies, never asked: the Blind Spot
        ("DORA", 2),
        ("KWG", 1),
        ("AI Act", 1),  # touched through the AI Act Rule Check
    ]
    assert "GwG" not in {s["short_title"] for s in spots}  # does not apply
    assert spots[0]["url"] == "https://example.org/MaRisk"


def test_filters_narrow_to_what_was_clicked():
    def ids(**kw):
        return [r["created_at"].day for r in analytics.filter_records(RECORDS, today=TODAY, **kw)]

    assert ids(regime="dora") == [24, 20]
    assert ids(provision="§ 25a KWG") == [10]
    assert ids(day=date(2026, 10, 20)) == [20]
    assert ids(days=7, regime="banking") == []


class FakeAudit:
    def __init__(self, records):
        self._records = records

    def records(self, user_id, search=""):
        return [r for r in self._records if search.lower() in r["question"].lower()]


@pytest.fixture
def signed_in(monkeypatch):
    accounts = FakeAccounts()
    monkeypatch.setattr(api, "get_accounts", lambda: accounts)
    api.app.dependency_overrides[api.get_audit] = lambda: FakeAudit(RECORDS)
    http = TestClient(api.app)
    http.post("/api/auth/register", json={"email": "a@b.de", "password": "long enough pw"})
    yield http, accounts
    api.app.dependency_overrides.clear()


def test_dashboard_reports_the_period_and_blind_spots_need_a_profile(signed_in):
    http, accounts = signed_in
    data = http.get("/api/me/dashboard?days=0").json()  # every question, whatever today is
    assert data["days"] == 0 and data["stats"]["questions_total"] == 4
    assert data["blind_spots"] is None
    assert data["provisions"][0]["provision"] == "Art. 19 DORA"
    assert "provisions" not in data["recent"][0] and "obligation_count" in data["recent"][0]
    accounts.users["u1"]["profile"] = {
        "firm_type": "significant_bank",
        "size": "large",
        "customers": "both",
        "activities": [],
    }
    spots = http.get("/api/me/dashboard").json()["blind_spots"]
    assert spots and spots[0]["questions"] == 0
    assert http.get("/api/me/dashboard?days=14").status_code == 422


def test_question_list_filters_by_provision_and_day(signed_in):
    http, _ = signed_in
    by_provision = http.get("/api/me/questions", params={"provision": "Art. 19 DORA"}).json()[
        "items"
    ]
    assert len(by_provision) == 2
    on_day = http.get("/api/me/questions", params={"day": "2026-10-10"}).json()["items"]
    assert [r["question"] for r in on_day] == ["Question of 10 October"]
    assert http.get("/api/me/questions", params={"day": "yesterday"}).status_code == 422
