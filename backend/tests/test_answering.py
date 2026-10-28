"""Prompt, citations and the API, with the retriever and the Answer Model replaced by fakes."""

from types import SimpleNamespace

import openai
from fastapi.testclient import TestClient
from langchain_core.documents import Document
from langchain_core.messages import AIMessage

from compliance_advisor import api
from compliance_advisor.answer import AnswerService, DatabaseError, cited_numbers
from compliance_advisor.prompt import build_messages, format_passages, question_language
from compliance_advisor.retriever import (
    RetrievedPassage,
    Retriever,
    cap_per_source,
    merge_ranked,
    named_provisions,
)

METADATA = {
    "passage_id": "eu-dora:0:abc",
    "source_id": "eu-dora",
    "source_title": "Regulation (EU) 2022/2554 (DORA)",
    "short_title": "DORA",
    "regime": "dora",
    "layer": "eu_level_1",
    "issuer": "European Parliament and Council",
    "language": "en",
    "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32022R2554",
    "provision": "Art. 17 DORA",
    "link": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32022R2554#art_17",
    "legal_status": "in_force",
    "as_of": "2026-10-21",
    "position": 0,
}
HITS = [
    RetrievedPassage(Document(page_content="Article 17 text", metadata=METADATA), 0.81),
    RetrievedPassage(Document(page_content="Article 19 text", metadata=METADATA), 0.74),
]


class FakeRetriever:
    def __init__(self):
        self.strategies = []

    def retrieve(self, question, k, strategy="vector"):
        self.strategies.append(strategy)
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
    api.app.dependency_overrides[api.get_audit] = lambda: None
    return TestClient(api.app)


def test_prompt_numbers_passages_and_names_their_layer():
    text = format_passages(HITS)
    assert '<passage n="1" provision="Art. 17 DORA"' in text and '<passage n="2"' in text
    assert 'status="in force"' in text
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
    assert set(body) == {
        "id",
        "created_at",
        "question",
        "redactions",
        "answer",
        "passages",
        "cited",
        "tools",
        "coverage",
        "model",
        "strategy",
        "usage",
        "disclaimer",
        "trace",
        "refusal",
    }
    assert body["tools"] == [] and body["redactions"] == []
    assert body["cited"] == [1]
    assert body["passages"][0]["n"] == 1 and body["passages"][0]["score"] == 0.81
    assert body["passages"][0]["provision"] == "Art. 17 DORA"
    assert body["passages"][0]["link"].endswith("#art_17")
    assert body["usage"] == {"input_tokens": 900, "output_tokens": 40, "cost_usd": 0.0}
    assert "not legal advice" in body["disclaimer"]
    assert body["strategy"] == "vector"  # the default Search Strategy


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


def test_cap_per_source_keeps_other_sources_in_the_top_k():
    def hit(source, score):
        return RetrievedPassage(Document(page_content="t", metadata={"source_id": source}), score)

    ranked = [
        hit("de-kwg", 0.9),
        hit("de-kwg", 0.89),
        hit("de-kwg", 0.88),
        hit("de-kwg", 0.87),
        hit("de-gwg", 0.86),
        hit("de-kwg", 0.85),
        hit("de-bafin", 0.84),
    ]
    chosen = cap_per_source(ranked, k=5, max_per_source=3)
    assert [h.document.metadata["source_id"] for h in chosen] == [
        "de-kwg",
        "de-kwg",
        "de-kwg",
        "de-gwg",
        "de-bafin",
    ]
    assert cap_per_source(ranked, k=3, max_per_source=0) == ranked[:3]


def test_cap_per_source_fills_up_when_one_source_dominates():
    def hit(source, score):
        return RetrievedPassage(Document(page_content="t", metadata={"source_id": source}), score)

    ranked = [hit("eu-ai-act", 0.9 - i / 100) for i in range(8)]
    chosen = cap_per_source(ranked, k=6, max_per_source=3)
    assert len(chosen) == 6 and chosen == ranked[:6]


def test_question_language_is_detected():
    assert question_language("Welche Aufgaben hat die Compliance-Funktion?") == "German"
    assert question_language("Gilt die MaRisk für bedeutende Institute?") == "German"
    assert question_language("What does § 10 GwG require for identification?") == "English"
    assert question_language("When is an ICT incident major under DORA?") == "English"


def test_named_provisions_are_recognised_in_the_index_form():
    titles = ["KWG", "AI Act", "DORA", "GwG", "Solvency II"]
    assert named_provisions("What does § 25a KWG require?", titles) == ["§ 25a KWG"]
    assert named_provisions("Art. 6(2) AI Act and Article 17 of DORA", titles) == [
        "Art. 6 AI Act",
        "Art. 17 DORA",
    ]
    assert named_provisions("Was verlangt § 10 Abs. 1 GwG?", titles) == ["§ 10 GwG"]
    assert named_provisions("Artikel 41 der Solvency II", titles) == ["Art. 41 Solvency II"]
    assert named_provisions("What does DORA require?", titles) == []


def test_ask_uses_the_chosen_search_strategy_and_records_it():
    retriever = FakeRetriever()
    service = AnswerService(retriever, FakeModel(AIMessage(content="Yes [1].")), "m", top_k=6)
    api.app.dependency_overrides[api.get_service] = lambda: service
    api.app.dependency_overrides[api.get_audit] = lambda: None
    client = TestClient(api.app)
    body = client.post("/api/ask", json={"question": "Major?", "strategy": "hybrid"}).json()
    assert body["strategy"] == "hybrid" and retriever.strategies == ["hybrid"]
    assert (
        client.post("/api/ask", json={"question": "Major?", "strategy": "magic"}).status_code == 422
    )


def test_merge_ranks_passages_found_by_both_searches_first():
    def hit(passage_id, score):
        return RetrievedPassage(
            Document(page_content="t", metadata={"passage_id": passage_id}), score
        )

    vector = [hit("a", 0.8), hit("b", 0.7), hit("c", 0.6)]
    keyword = [hit("c", 0.6), hit("a", 0.8), hit("d", 0.3)]
    merged = merge_ranked(vector, keyword)
    # a: 1/61 + 1/62, c: 1/63 + 1/61, b: 1/62, d: 1/63 (reciprocal rank fusion)
    assert [h.document.metadata["passage_id"] for h in merged] == ["a", "c", "b", "d"]
    assert merged[1].score == 0.6  # the shown score stays the cosine similarity


def test_cap_per_source_keeps_the_merged_order():
    def hit(source, score):
        return RetrievedPassage(Document(page_content="t", metadata={"source_id": source}), score)

    # A keyword hit can rank above a Passage with a higher cosine similarity.
    ranked = [hit("x", 0.5), hit("x", 0.9), hit("x", 0.8), hit("y", 0.7)]
    chosen = cap_per_source(ranked, k=3, max_per_source=1)
    # x 0.5 and y 0.7 pass the cap, x 0.9 fills the last slot; all keep their merged rank.
    assert [h.score for h in chosen] == [0.5, 0.9, 0.7]


def test_merge_weights_the_keyword_ranks():
    def hit(passage_id):
        return RetrievedPassage(
            Document(page_content="t", metadata={"passage_id": passage_id}), 0.5
        )

    vector = [hit("a"), hit("b")]
    keyword = [hit("b"), hit("c")]
    # At half weight, a keyword-only first rank (0.5/61) counts less than a vector second rank (1/62).
    merged = merge_ranked(vector, [hit("c")], weights=(1.0, 0.5))
    assert [h.document.metadata["passage_id"] for h in merged] == ["a", "b", "c"]
    assert merge_ranked(vector, keyword)[0].document.metadata["passage_id"] == "b"  # in both


class FakeStore:
    """Enough of PGVector for the Retriever: an embedding and a ranked list per call."""

    def __init__(self, hits):
        self.hits = hits
        self.embeddings = SimpleNamespace(embed_query=lambda q: [0.1, 0.2])

    def similarity_search_with_score_by_vector(self, vector, k, filter=None):
        if filter:
            label = filter["provision"]["$eq"]
            return [(d, 1 - s) for d, s in self.hits if d.metadata["provision"] == label][:k]
        return [(d, 1 - s) for d, s in self.hits][:k]


def test_search_returns_the_answer_trace():
    def doc(passage_id, provision, source):
        return Document(
            page_content="t",
            metadata={
                "passage_id": passage_id,
                "provision": provision,
                "source_id": source,
                "short_title": source,
            },
        )

    store = FakeStore(
        [
            (doc("a", "Art. 17 DORA", "DORA"), 0.9),
            (doc("b", "Art. 19 DORA", "DORA"), 0.8),
            (doc("c", "§ 10 GwG", "GwG"), 0.7),
        ]
    )
    retriever = Retriever(store, short_titles=["DORA", "GwG"])
    passages, trace = retriever.search("Was sagt § 10 GwG?", 2)
    assert [p.document.metadata["passage_id"] for p in passages] == ["c", "a"]
    assert trace["named"] == ["§ 10 GwG"] and trace["named_hits"][0]["passage_id"] == "c"
    assert [h["passage_id"] for h in trace["vector"]] == ["a", "b"] and trace["vector"][0][
        "score"
    ] == 0.9
    assert trace["found_by"] == {"c": "named", "a": "vector"}
    assert trace["keyword"] == [] and trace["merged"] == []


def test_named_hits_beyond_half_the_slots_still_come_through_the_ranking():
    def doc(passage_id, provision):
        return Document(
            page_content="t",
            metadata={
                "passage_id": passage_id,
                "provision": provision,
                "source_id": "KWG",
                "short_title": "KWG",
            },
        )

    # two named Provisions in two parts each: four named hits, only two may take named slots
    hits = [
        (doc("a1", "§ 25a KWG"), 0.9),
        (doc("a2", "§ 25a KWG"), 0.85),
        (doc("b1", "§ 25b KWG"), 0.8),
        (doc("b2", "§ 25b KWG"), 0.95),
    ]
    retriever = Retriever(FakeStore(hits), short_titles=["KWG"])
    passages, trace = retriever.search("Was verlangen § 25a KWG und § 25b KWG?", 4)
    ids = [p.document.metadata["passage_id"] for p in passages]
    assert ids[:2] == ["a1", "a2"]  # the named slots
    assert "b2" in ids and "b1" in ids  # the rest fill up from the ranking, not dropped
    assert trace["found_by"]["b2"] == "vector"
