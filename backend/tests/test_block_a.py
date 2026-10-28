"""Fixes from the review of 2026-10-28: obligations extraction, fingerprints, 503 handling."""

import json

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from compliance_advisor import api
from compliance_advisor.fetch import save_meta
from compliance_advisor.models import ModelOption
from compliance_advisor.monitoring import memory_errors


class FakeAudit:
    def __init__(self, record):
        self.record = record
        self.saved = None

    def get(self, answer_id):
        return self.record

    def save_obligations(self, answer_id, rows, cost_usd=0.0):
        self.saved = (rows, cost_usd)

    def cost_since(self, since):
        return 0.0


def _record(**response):
    base = {
        "question": "q",
        "passages": [{"n": 1, "provision": "Art. 17 DORA", "text": "t", "source_id": "eu-dora"}],
        "cited": [1],
        "model": "mistralai/mistral-large-4-0",
    }
    return {"id": "a1", "user_id": None, "response": base | response}


def _fail(*args, **kwargs):
    raise AssertionError("must not be called")


def test_refused_answers_are_not_sent_to_a_model(monkeypatch):
    audit = FakeAudit(_record(refusal="off_topic", passages=[], cited=[]))
    api.app.dependency_overrides[api.get_audit] = lambda: audit
    monkeypatch.setattr(api, "chat_model", _fail)
    body = TestClient(api.app).post("/api/history/a1/obligations").json()
    assert body == {"rows": [], "cost_usd": 0.0} and audit.saved is None


def test_extraction_uses_the_answers_own_model_and_keeps_its_cost(monkeypatch):
    audit = FakeAudit(_record())
    api.app.dependency_overrides[api.get_audit] = lambda: audit
    chosen = []
    monkeypatch.setattr(api, "chat_model", lambda option, settings: chosen.append(option.id))
    monkeypatch.setattr(
        api,
        "load_models",
        lambda path: [
            ModelOption(id="openai/gpt-6-luna", label="L"),
            ModelOption(id="mistralai/mistral-large-4-0", label="M", eu_hosted=True),
        ],
    )
    raw = AIMessage(content="", response_metadata={"token_usage": {"cost": 0.0021}})
    monkeypatch.setattr(api, "extract_obligations", lambda model, q, p, c: ([], raw))
    body = TestClient(api.app).post("/api/history/a1/obligations").json()
    assert chosen == ["mistralai/mistral-large-4-0"]  # the answer's model, not the default
    assert body["cost_usd"] == 0.0021 and audit.saved == ([], 0.0021)


def test_extraction_counts_against_the_rate_limit(monkeypatch):
    audit = FakeAudit(_record())
    api.app.dependency_overrides[api.get_audit] = lambda: audit
    monkeypatch.setattr(api, "chat_model", lambda option, settings: "model")
    monkeypatch.setattr(
        api, "extract_obligations", lambda model, q, p, c: ([], AIMessage(content=""))
    )
    client = TestClient(api.app)
    limit = api._limiter().limits.guest_per_hour
    for _ in range(limit + 1):  # the first one counts against the address, then the cookie
        assert client.post("/api/history/a1/obligations").status_code == 200
    assert client.post("/api/history/a1/obligations").status_code == 429


def test_a_fresh_download_keeps_the_text_fingerprint(tmp_path):
    save_meta(tmp_path, {"sha256": "f1"}, text_sha256="t1")
    save_meta(tmp_path, {"sha256": "f2"})  # a new download, text not re-checked yet
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta == {"sha256": "f2", "text_sha256": "t1"}
    save_meta(tmp_path, {"sha256": "f3"}, text_sha256="t2")
    assert json.loads((tmp_path / "meta.json").read_text())["text_sha256"] == "t2"


def test_503s_are_counted_in_memory_not_in_the_down_database(monkeypatch):
    memory_errors.clear()
    monkeypatch.setattr(api, "get_events", _fail)
    api._record_error(503, "/api/ask")
    api._record_error(503, "/api/ask")
    assert memory_errors[503] == 2
    memory_errors.clear()
