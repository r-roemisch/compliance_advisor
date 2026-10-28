"""The Operator's figures and who may see them."""

import json
import logging
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from compliance_advisor import api
from compliance_advisor.monitoring import JsonFormatter, overview


def _row(day: int, **extra) -> dict:
    row = {
        "created_at": datetime(2026, 10, day, 10, tzinfo=UTC),
        "model": "openai/gpt-6-luna",
        "user_id": "u1",
        "api_key": None,
        "strategy": "vector",
        "refusal": None,
        "cost": 0.001,
        "seconds": 8.0,
        "top_score": 0.6,
        "coverage": "full",
        "cited": 2,
    }
    return row | extra


def test_overview_counts_volume_cost_quality_and_refusals():
    rows = [
        _row(27),
        _row(28, model="mistralai/mistral-large-4-0", strategy="hybrid", cost=0.012, user_id=None),
        _row(28, refusal="off_topic", cost=0.0001, seconds=None, top_score=None, cited=0),
        _row(28, api_key="ci", coverage="partial", cited=0),
    ]
    errors = [{"at": None, "kind": "error", "data": {"status": 502}}] * 2
    o = overview(rows, errors, days=7, today=date(2026, 10, 28))
    s = o["stats"]
    assert s["questions"] == 4 and s["answered"] == 3 and s["refused"] == 1
    assert s["accounts"] == 1 and s["guest_questions"] == 1 and s["via_api_key"] == 1
    assert s["cost_usd"] == 0.0141 and s["errors"] == 2
    assert s["avg_seconds"] == 8.0 and s["avg_top_score"] == 0.6
    assert s["cited_share"] == 0.667 and s["coverage_full_share"] == 0.667
    assert len(o["activity"]) == 7 and o["activity"][-1] == {"date": "2026-10-28", "count": 3}
    assert o["models"][0] == {"id": "openai/gpt-6-luna", "questions": 3, "cost_usd": 0.0021}
    assert o["strategies"][1] == {"id": "hybrid", "questions": 1, "cost_usd": 0.012}
    assert o["refusals"] == [{"reason": "off_topic", "count": 1}]
    assert o["errors"] == [{"status": "502", "count": 2}]


def test_json_log_lines_carry_no_free_text_structure_problems():
    record = logging.LogRecord(
        "x", logging.INFO, "f", 1, "ask refused reason=%s", ("off_topic",), None
    )
    line = json.loads(JsonFormatter().format(record))
    assert line["message"] == "ask refused reason=off_topic" and line["level"] == "INFO"


def test_only_operators_see_the_overview(monkeypatch):
    user = {"id": "u1", "email": "ops@example.org", "name": "", "profile": None}
    api.app.dependency_overrides[api.current_user] = lambda: user
    client = TestClient(api.app)
    assert client.get("/api/operator/overview").status_code == 403
    user["operator"] = True  # granted with `compliance-advisor-accounts operator grant`

    class FakeEvents:
        def answer_rows(self, start):
            return []

        def since(self, start, kind=None):
            return []

    api.app.dependency_overrides[api.get_events] = lambda: FakeEvents()
    monkeypatch.setattr(api, "get_events", lambda: FakeEvents())
    response = client.get("/api/operator/overview?days=7")
    assert response.status_code == 200 and response.json()["stats"]["questions"] == 0
    assert client.get("/api/auth/me").json()["user"]["operator"] is True
