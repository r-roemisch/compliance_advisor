"""Prompt, citations and the API, with the retriever and the Answer Model replaced by fakes."""

import openai
from fastapi.testclient import TestClient
from langchain_core.documents import Document
from langchain_core.messages import AIMessage

from compliance_advisor import api
from compliance_advisor.answer import AnswerService, DatabaseError, cited_numbers
from compliance_advisor.prompt import build_messages, format_passages
from compliance_advisor.retriever import RetrievedPassage

METADATA = {
    "passage_id": "eu-dora:0:abc",
    "source_id": "eu-dora",
    "source_title": "Regulation (EU) 2022/2554 (DORA)",
    "short_title": "DORA",
    "regime": "dora",
    "layer": "eu_level_1",
    "issuer": "European Parliament and Council",
    "language": "en",
    "url": "https://eur-lex.europa.eu/eli/reg/2022/2554/oj/eng",
    "position": 0,
}
HITS = [
    RetrievedPassage(Document(page_content="Article 17 text", metadata=METADATA), 0.81),
    RetrievedPassage(Document(page_content="Article 19 text", metadata=METADATA), 0.74),
]


class FakeRetriever:
    def retrieve(self, question, k):
        return HITS[:k]


class FakeModel:
    def __init__(self, reply=None, error=None):
        self.reply, self.error = reply, error

    def invoke(self, messages):
        if self.error:
            raise self.error
        return self.reply


def client_with(model) -> TestClient:
    service = AnswerService(FakeRetriever(), model, "openai/gpt-6-luna", top_k=6)
    api.app.dependency_overrides[api.get_service] = lambda: service
    return TestClient(api.app)


def test_prompt_numbers_passages_and_names_their_layer():
    text = format_passages(HITS)
    assert '<passage n="1"' in text and '<passage n="2"' in text
    assert "EU Level 1" in text and 'issuer="European Parliament and Council"' in text
    messages = build_messages("When is an incident major?", HITS)
    assert "Do not add disclaimers" in messages[0].content
    assert "<question>\nWhen is an incident major?\n</question>" in messages[1].content


def test_cited_numbers_ignore_numbers_that_were_not_given():
    assert cited_numbers("See [2] and [1, 2]; also [7].", available=2) == [2, 1]


def test_cited_numbers_accept_provisions_inside_the_bracket():
    text = "Guidelines [1, Art. 32 Abs. 1-2]; reporting [DORA Art. 19(1) [3]]; [4; 2]."
    assert cited_numbers(text, available=6) == [1, 3, 4, 2]


def test_ask_returns_the_agreed_shape():
    reply = AIMessage(
        content="Major incidents are reported [1].",
        usage_metadata={"input_tokens": 900, "output_tokens": 40, "total_tokens": 940},
    )
    response = client_with(FakeModel(reply)).post("/api/ask", json={"question": "Major?"})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"question", "answer", "passages", "cited", "model", "usage", "disclaimer"}
    assert body["cited"] == [1]
    assert body["passages"][0]["n"] == 1 and body["passages"][0]["score"] == 0.81
    assert body["usage"] == {"input_tokens": 900, "output_tokens": 40}
    assert "not legal advice" in body["disclaimer"]


def test_ask_rejects_too_short_and_too_long_questions():
    client = client_with(FakeModel(AIMessage(content="x")))
    assert client.post("/api/ask", json={"question": "  a "}).status_code == 422
    too_long = client.post("/api/ask", json={"question": "x" * 2001})
    assert too_long.status_code == 422
    assert "question" in too_long.json()["detail"]


def test_ask_reports_a_failing_answer_model_as_502():
    error = openai.APIConnectionError(request=None)
    response = client_with(FakeModel(error=error)).post("/api/ask", json={"question": "Major?"})
    assert response.status_code == 502
    assert "answer model did not respond" in response.json()["detail"]


def test_ask_reports_an_unreachable_database_as_503():
    def down():
        raise DatabaseError("the database is not reachable")

    api.app.dependency_overrides[api.get_service] = down
    response = TestClient(api.app).post("/api/ask", json={"question": "Major?"})
    assert response.status_code == 503
    assert response.json()["detail"] == "The database is not reachable"
