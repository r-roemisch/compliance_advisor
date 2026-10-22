"""Coverage line, cost, audit export, streaming steps and the model list."""

import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from compliance_advisor import api
from compliance_advisor.answer import AnswerService, _usage, split_coverage
from compliance_advisor.audit import to_markdown
from compliance_advisor.schemas import AskResponse
from tests.test_tools import OnePassage


def test_coverage_line_is_removed_and_returned():
    assert split_coverage("Answer text [1].\n\nCoverage: partial") == (
        "Answer text [1].",
        "partial",
    )
    assert split_coverage("Nicht abgedeckt.\nCoverage: none.") == ("Nicht abgedeckt.", "none")
    assert split_coverage("No marker here.") == ("No marker here.", "unknown")
    assert split_coverage("Text.\n\n**Coverage: partial**") == ("Text.", "partial")


def test_cost_is_summed_from_what_openrouter_reports():
    a = AIMessage(
        content="",
        usage_metadata={"input_tokens": 10, "output_tokens": 1, "total_tokens": 11},
        response_metadata={"token_usage": {"cost": 0.0012}},
    )
    b = AIMessage(
        content="",
        usage_metadata={"input_tokens": 20, "output_tokens": 2, "total_tokens": 22},
        response_metadata={"token_usage": {"cost": 0.0003}},
    )
    usage = _usage(a, b)
    assert (usage.input_tokens, usage.output_tokens, usage.cost_usd) == (30, 3, 0.0015)


class PlainModel:
    def invoke(self, messages):
        return AIMessage(
            content="DORA applies [1].\nCoverage: full",
            usage_metadata={"input_tokens": 5, "output_tokens": 5, "total_tokens": 10},
        )


def test_markdown_export_lists_question_passages_and_source_versions():
    response = AnswerService(OnePassage(), PlainModel(), "m", top_k=6).ask("Does DORA apply?")
    record = {
        "created_at": datetime(2026, 10, 22, 12, 0, tzinfo=UTC),
        "profile": {"firm_type": "reinsurer", "size": "large", "activities": []},
        "response": json.loads(response.model_dump_json()),
        "source_versions": {
            "eu-dora": {"fetched_at": "2026-10-21T12:05:31+00:00", "sha256": "abc"}
        },
    }
    text = to_markdown(record)
    assert "## Question\n\nDoes DORA apply?" in text and "DORA applies [1]." in text
    assert "Coverage" not in text.split("## Answer")[1].split("## Passages")[0]
    assert "eu-dora: downloaded 2026-10-21T12:05:31+00:00, sha256 abc" in text
    assert "Firm Profile: reinsurer" in text


def test_stream_reports_each_step_then_the_result():
    service = AnswerService(OnePassage(), PlainModel(), "m", top_k=6)
    api.app.dependency_overrides[api.get_service] = lambda: service
    api.app.dependency_overrides[api.get_audit] = lambda: None
    with TestClient(api.app).stream(
        "POST", "/api/ask/stream", json={"question": "Does DORA apply?"}
    ) as r:
        events = [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
    assert [e["stage"] for e in events] == ["search", "model", "done"]
    result = AskResponse.model_validate(events[-1]["result"])
    assert result.coverage == "full" and result.cited == [1]


def test_stream_reports_an_unknown_model_as_an_error_event():
    service = AnswerService(OnePassage(), PlainModel(), "m", top_k=6)
    api.app.dependency_overrides[api.get_service] = lambda: service
    api.app.dependency_overrides[api.get_audit] = lambda: None
    with TestClient(api.app).stream(
        "POST", "/api/ask/stream", json={"question": "Does DORA apply?", "model": "nope"}
    ) as r:
        events = [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
    assert events[-1]["stage"] == "error" and events[-1]["status"] == 422


def test_model_list_offers_an_eu_hosted_option():
    models = TestClient(api.app).get("/api/models").json()["models"]
    assert models[0]["id"] == "openai/gpt-6-luna"
    assert any(m["eu_hosted"] for m in models)
    assert all("provider_only" not in m for m in models)
