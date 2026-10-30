"""Coverage line, cost, audit export, streaming steps and the model list."""

import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk

from compliance_advisor.answer import AnswerService, _usage, split_coverage
from compliance_advisor.api import app, deps
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
    app.dependency_overrides[deps.get_service] = lambda: service
    app.dependency_overrides[deps.get_audit] = lambda: None
    with TestClient(app).stream(
        "POST", "/api/ask/stream", json={"question": "Does DORA apply?"}
    ) as r:
        events = [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
    assert [e["stage"] for e in events] == ["precheck", "search", "found", "model", "done"]
    assert events[2]["count"] == 1 and events[2]["sources"] == ["DORA"]  # the "found" event
    result = AskResponse.model_validate(events[-1]["result"])
    assert result.coverage == "full" and result.cited == [1]


def test_stream_reports_an_unknown_model_as_an_error_event():
    service = AnswerService(OnePassage(), PlainModel(), "m", top_k=6)
    app.dependency_overrides[deps.get_service] = lambda: service
    app.dependency_overrides[deps.get_audit] = lambda: None
    with TestClient(app).stream(
        "POST", "/api/ask/stream", json={"question": "Does DORA apply?", "model": "nope"}
    ) as r:
        events = [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
    assert events[-1]["stage"] == "error" and events[-1]["status"] == 422


def test_model_list_offers_an_eu_hosted_option():
    models = TestClient(app).get("/api/models").json()["models"]
    assert models[0]["id"] == "openai/gpt-6-luna"
    assert any(m["eu_hosted"] for m in models)
    assert all("provider_only" not in m and "system_prompt" not in m for m in models)


class StreamingModel:
    def stream(self, messages):
        for piece in ["DORA ", "applies [1].", "\nCoverage: full"]:
            yield AIMessageChunk(content=piece)


def test_streamed_answer_reports_writing_and_text_as_it_arrives():
    stages = []
    response = AnswerService(OnePassage(), StreamingModel(), "m", top_k=6).ask(
        "Does DORA apply?", on_stage=lambda stage, data: stages.append((stage, data.get("text")))
    )
    names = [s for s, _ in stages]
    assert names[:4] == ["precheck", "search", "found", "model"] and names[4] == "writing"
    assert "".join(t for s, t in stages if s == "delta") == "DORA applies [1].\nCoverage: full"
    assert response.answer == "DORA applies [1]." and response.coverage == "full"


def test_cost_is_computed_from_list_prices_when_not_reported():
    a = AIMessage(
        content="",
        usage_metadata={"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100},
    )
    assert _usage(a, prices=(1e-7, 5e-7)).cost_usd == 0.00015


def test_coverage_line_is_recognised_in_its_bold_label_form():
    assert split_coverage("Answer [1].\n\n**Coverage:** partial") == ("Answer [1].", "partial")
    assert split_coverage("Answer.\n\n**Coverage: full**") == ("Answer.", "full")


def test_refused_record_exports_its_reason_instead_of_an_empty_answer():
    from datetime import UTC, datetime

    from compliance_advisor.audit import to_markdown

    record = {
        "id": "r1",
        "created_at": datetime(2026, 10, 28, tzinfo=UTC),
        "model": "m",
        "profile": None,
        "source_versions": {},
        "response": {
            "question": "Rezept?",
            "answer": "",
            "passages": [],
            "cited": [],
            "tools": [],
            "redactions": [],
            "usage": {"input_tokens": 1, "output_tokens": 1, "cost_usd": 0.0},
            "model": "m",
            "strategy": "vector",
            "disclaimer": "Not legal advice.",
            "refusal": "off_topic",
        },
    }
    text = to_markdown(record)
    assert "## Refused" in text and "off_topic" in text and "## Answer" not in text
