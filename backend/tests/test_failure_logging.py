"""Every failed prompt leaves one line on the failures logger, with the step it failed in and the
id of its request, and never the question (ADR 0006)."""

import json
import logging
from types import SimpleNamespace

import openai
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from sqlalchemy.exc import OperationalError

from compliance_advisor.answer import AnswerService, UpstreamError, format_problems
from compliance_advisor.api import app, deps
from compliance_advisor.api.routes import history
from compliance_advisor.logs import JsonFormatter, RequestIdFilter, describe
from compliance_advisor.obligations import ExtractedRow, extract_obligations

from .test_answering import FakeModel, FakeRetriever
from .test_block_a import OWNER, FakeAudit, _record
from .test_obligations_timeline import PASSAGES, StructuredModel

QUESTION = "Must Muster Bank report its outage to BaFin?"  # no log line may hold it
ANSWER = AIMessage(content="Yes [1].\nCoverage: full")


class Events:
    def __init__(self):
        self.rows = []

    def record(self, kind, **data):
        self.rows.append((kind, data))


@pytest.fixture
def failures(caplog, monkeypatch):
    """Returns the failed-prompt lines so far, each with the request id the log handler adds,
    after checking that no log line holds the question. Failed requests are counted in `events`
    instead of the database."""
    caplog.handler.addFilter(RequestIdFilter())
    caplog.set_level(logging.INFO)
    events = Events()
    monkeypatch.setattr(deps, "get_events", lambda: events)

    def lines():
        assert not [r for r in caplog.records if "Muster" in r.getMessage()]
        return [r for r in caplog.records if r.name == "compliance_advisor.failures"]

    lines.events = events
    return lines


def _client(service, audit=None) -> TestClient:
    app.dependency_overrides[deps.get_service] = lambda: service
    app.dependency_overrides[deps.get_audit] = lambda: audit
    return TestClient(app, raise_server_exceptions=False)


def test_a_failing_answer_model_is_logged_once_with_its_step_and_request_id(failures):
    model = FakeModel(error=openai.APIConnectionError(request=None))
    service = AnswerService(FakeRetriever(), model, "openai/gpt-6-luna", top_k=6)
    response = _client(service).post("/api/ask", json={"question": QUESTION})
    assert response.status_code == 502
    [line] = failures()
    assert line.levelno == logging.ERROR
    assert line.getMessage().startswith(
        "prompt failed step=answer model=openai/gpt-6-luna strategy=vector seconds="
    )
    assert line.error == "APIConnectionError: Connection error."
    assert line.request_id == response.headers["x-request-id"]
    # the Operator's count of failed requests keeps the id that finds the line
    assert failures.events.rows == [
        ("error", {"status": 502, "where": "/api/ask", "request_id": line.request_id})
    ]


def test_a_database_error_is_logged_at_the_search_step_without_its_parameters(failures):
    class DownRetriever:
        def retrieve(self, question, k, strategy="vector"):
            raise OperationalError("SELECT 1", {"q": question}, ConnectionRefusedError("refused"))

    service = AnswerService(DownRetriever(), FakeModel(ANSWER), "m", top_k=6)
    assert _client(service).post("/api/ask", json={"question": QUESTION}).status_code == 503
    [line] = failures()  # the parameters, holding the question, are not in it
    assert (line.step, line.error) == (
        "search",
        "OperationalError: (builtins.ConnectionRefusedError) refused",
    )


def test_the_stream_logs_its_failure_with_the_requests_id(failures):
    model = FakeModel(error=openai.APIConnectionError(request=None))
    service = AnswerService(FakeRetriever(), model, "m", top_k=6)
    with _client(service).stream("POST", "/api/ask/stream", json={"question": QUESTION}) as r:
        events = [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
        sent_id = r.headers["x-request-id"]
    assert events[-1]["stage"] == "error" and events[-1]["status"] == 502
    [line] = failures()  # logged in the stream's worker thread
    assert line.step == "answer" and line.request_id == sent_id


def test_an_unexpected_error_is_logged_and_its_500_carries_the_request_id(failures):
    service = AnswerService(FakeRetriever(), FakeModel(error=KeyError("tool")), "m", top_k=6)
    response = _client(service).post("/api/ask", json={"question": QUESTION})
    assert response.status_code == 500 and response.json() == {"detail": "Unexpected error"}
    [line] = failures()
    assert (line.step, line.error) == ("answer", "KeyError: 'tool'")
    assert response.headers["x-request-id"] == line.request_id


def test_failed_screening_and_translation_are_warnings_and_the_question_is_answered(failures):
    down = FakeModel(error=RuntimeError("provider down"))
    service = AnswerService(
        FakeRetriever(),
        FakeModel(ANSWER),
        "m",
        top_k=6,
        screeners={"m": down},
        translators={"m": down},
    )
    body = _client(service).post("/api/ask", json={"question": QUESTION}).json()
    assert body["cited"] == [1]
    assert [(line.levelno, line.step, line.error) for line in failures()] == [
        (logging.WARNING, "screening", "RuntimeError: provider down"),
        (logging.WARNING, "translation", "RuntimeError: provider down"),
    ]


def test_an_answer_that_breaks_the_format_is_a_warning(failures):
    reply = AIMessage(content="It depends.", response_metadata={"finish_reason": "length"})
    service = AnswerService(FakeRetriever(), FakeModel(reply), "m", top_k=6)
    assert _client(service).post("/api/ask", json={"question": QUESTION}).status_code == 200
    [line] = failures()
    assert (line.levelno, line.step) == (logging.WARNING, "answer")
    assert line.error == "cut off at the output limit; no Coverage line; no citation"


def test_format_problems_spare_an_answer_with_nothing_to_cite():
    assert format_problems("Yes [1].", "full", 1, 2, "stop") == []
    assert format_problems("The passages do not cover it.", "none", 0, 2, "stop") == []
    assert format_problems("Yes.", "partial", 0, 2, None) == ["no citation"]
    assert format_problems("", "unknown", 0, 2, "content_filter") == [
        "stopped by the provider's content filter",
        "empty answer",
    ]


def test_an_answer_that_could_not_be_stored_is_a_warning_and_still_returned(failures):
    class BrokenAudit:
        def cost_since(self, since):
            return 0.0

        def save(self, response, *args):
            raise OperationalError("INSERT", {"question": QUESTION}, ConnectionRefusedError("x"))

    service = AnswerService(FakeRetriever(), FakeModel(ANSWER), "m", top_k=6)
    response = _client(service, BrokenAudit()).post("/api/ask", json={"question": QUESTION})
    assert response.status_code == 200 and response.json()["cited"] == [1]
    [line] = failures()
    assert (line.levelno, line.step, line.model) == (logging.WARNING, "storage", "m")


def test_an_answer_service_that_cannot_start_is_logged(failures, monkeypatch):
    def no_key():
        raise SystemExit("OPENROUTER_API_KEY is not set")

    monkeypatch.setattr(deps, "_service", no_key)
    with pytest.raises(UpstreamError):
        deps.get_service()
    [line] = failures()
    assert (line.step, line.error) == ("start", "SystemExit: OPENROUTER_API_KEY is not set")


def test_a_failed_extraction_of_obligations_is_logged(failures, monkeypatch):
    def timeout(model, question, passages, cited):
        raise openai.APITimeoutError(request=None)

    app.dependency_overrides[deps.get_audit] = lambda: FakeAudit(_record())
    app.dependency_overrides[deps.current_user] = lambda: OWNER
    monkeypatch.setattr(history, "chat_model", lambda option, settings: "model")
    monkeypatch.setattr(history, "extract_obligations", timeout)
    assert TestClient(app).post("/api/history/a1/obligations").status_code == 502
    [line] = failures()
    assert (line.step, line.model, line.error) == (
        "obligations",
        "mistralai/mistral-large-4-0",  # the answer's own model
        "APITimeoutError: Request timed out.",
    )


def test_unreadable_and_invented_obligations_are_logged(failures):
    class Unreadable(StructuredModel):
        def invoke(self, messages):
            return {"parsed": None, "parsing_error": ValueError(QUESTION), "raw": AIMessage("")}

    rows, _ = extract_obligations(Unreadable([]), QUESTION, PASSAGES, cited=[1])
    invented = StructuredModel([ExtractedRow(addressee="bank", action="Invented", passage=7)])
    extract_obligations(invented, QUESTION, PASSAGES, cited=[1])
    assert rows == []
    assert [line.error for line in failures()] == [
        "reply not readable (ValueError)",  # the parsing error's text can quote the reply
        "rows citing a passage not given: 1 of 1",
    ]


def test_openrouter_metadata_which_can_quote_the_question_is_left_out():
    flagged = openai.PermissionDeniedError(
        f"Error code: 403 - {{'metadata': {{'flagged_input': '{QUESTION}'}}}}",
        response=SimpleNamespace(request=None, status_code=403, headers={}),
        body={"message": "Input was flagged", "code": 403, "metadata": {"flagged_input": QUESTION}},
    )
    error = UpstreamError(f"the answer model did not respond: {flagged}")
    error.__cause__ = flagged
    assert describe(error) == "PermissionDeniedError: 403 Input was flagged"


def test_json_lines_carry_the_fields_of_a_failed_prompt_and_the_request_id():
    record = logging.makeLogRecord(
        {
            "name": "compliance_advisor.failures",
            "msg": "prompt failed step=search error=x",
            "step": "search",
            "error": "x",
            "request_id": "3f2a9c1e0b7d",
            "color_message": "\x1b[1mprompt failed\x1b[0m",  # uvicorn's coloured copy
        }
    )
    line = json.loads(JsonFormatter().format(record))
    assert (line["step"], line["error"], line["request_id"]) == ("search", "x", "3f2a9c1e0b7d")
    assert "color_message" not in line


def test_every_response_carries_its_own_request_id():
    client = TestClient(app)
    first, second = (client.get("/api/profiles").headers["x-request-id"] for _ in range(2))
    assert len(first) == 12 and first != second
