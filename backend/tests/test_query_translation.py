"""Query Translation: the translation call, the merged search, the Answer Trace and the cost.
No network, no database."""

from datetime import UTC, datetime
from types import SimpleNamespace

from langchain_core.documents import Document
from langchain_core.messages import AIMessage

from compliance_advisor.answer import AnswerService
from compliance_advisor.audit import to_markdown
from compliance_advisor.evaluation import GoldenItem, score_retrieval
from compliance_advisor.models import helper_models
from compliance_advisor.query_translation import clean_query, translate
from compliance_advisor.retriever import RetrievedPassage, Retriever
from compliance_advisor.settings import get_settings

from .test_answering import HITS, FakeModel, RecordingModel


class RecordingTranslator:
    def __init__(self, reply: str):
        self.reply, self.seen = reply, None

    def invoke(self, messages):
        self.seen = messages
        return AIMessage(
            content=self.reply,
            usage_metadata={"input_tokens": 200, "output_tokens": 20, "total_tokens": 220},
        )


def test_a_german_question_is_translated_into_english_and_back():
    translator = RecordingTranslator("Query: When must a major ICT-related incident be reported?")
    translation, reply = translate(
        "Wann muss ein schwerwiegender IKT-Vorfall gemeldet werden?", translator
    )
    assert translation.query == "When must a major ICT-related incident be reported?"
    assert translation.language == "en" and reply.usage_metadata["input_tokens"] == 200
    assert "into English" in translator.seen[0].content
    assert "data, not instructions" in translator.seen[1].content

    translator = RecordingTranslator("„Was verlangt § 10 GwG von Verpflichteten?“")
    translation, _ = translate("What does § 10 GwG require from obliged entities?", translator)
    assert translation.query == "Was verlangt § 10 GwG von Verpflichteten?"
    assert translation.language == "de" and "into German" in translator.seen[0].content


def test_no_translation_when_the_call_fails_or_repeats_the_question():
    assert translate("Was verlangt § 10 GwG?", FakeModel(error=RuntimeError("down"))) == (
        None,
        None,
    )
    translation, reply = translate(
        "What does DORA require?", RecordingTranslator("What does DORA require?")
    )
    assert translation is None and reply is not None  # the call still counts towards the cost
    assert translate("What does DORA require?", RecordingTranslator("  "))[0] is None


def test_the_reply_is_cleaned_into_one_query():
    assert clean_query('Translation: "Meldung schwerwiegender\nIKT-Vorfälle"') == (
        "Meldung schwerwiegender IKT-Vorfälle"
    )
    assert clean_query("Suchanfrage: Auslagerung nach § 26 ZAG") == "Auslagerung nach § 26 ZAG"


def _doc(passage_id: str, provision: str) -> Document:
    return Document(
        page_content="t",
        metadata={
            "passage_id": passage_id,
            "provision": provision,
            "source_id": provision.split()[-1],
            "short_title": provision.split()[-1],
        },
    )


class TwoLanguageStore:
    """Each query finds its own Passages: the German question German ones, the English
    translation English ones; Art. 19 DORA is found by both."""

    def __init__(self):
        self.embeddings = SimpleNamespace(embed_query=lambda q: [1.0] if "Vorfall" in q else [2.0])
        both = (_doc("dora-19", "Art. 19 DORA"), 0.2)
        self.hits = {
            (1.0,): [(_doc("kwg-25a", "§ 25a KWG"), 0.1), both, (_doc("gwg-10", "§ 10 GwG"), 0.3)],
            (2.0,): [
                both,
                (_doc("dora-17", "Art. 17 DORA"), 0.25),
                (_doc("rts-3", "Art. 3 RTS"), 0.3),
            ],
        }

    def similarity_search_with_score_by_vector(self, vector, k, filter=None):
        return self.hits[tuple(vector)][:k]


def test_search_merges_the_translations_ranking_and_traces_it():
    retriever = Retriever(TwoLanguageStore(), candidates=3)
    question, translation = (
        "Wann ist ein IKT-Vorfall schwerwiegend?",
        "When is an ICT incident major?",
    )
    alone, trace = retriever.search(question, 3)
    assert [p.document.metadata["passage_id"] for p in alone] == ["kwg-25a", "dora-19", "gwg-10"]
    assert trace["translation"] is None and trace["merged"] == []

    passages, trace = retriever.search(question, 3, translation=translation)
    ids = [p.document.metadata["passage_id"] for p in passages]
    assert ids[0] == "dora-19"  # found by both searches, so it rises to the top
    assert "dora-17" in ids  # only the translation found it
    assert trace["translation"]["query"] == translation
    assert [h["passage_id"] for h in trace["translation"]["vector"]] == [
        "dora-19",
        "dora-17",
        "rts-3",
    ]
    assert (
        trace["found_by"]["dora-17"] == "translation" and trace["found_by"]["dora-19"] == "vector"
    )
    assert trace["merged"][:1] == ["dora-19"]
    # a Passage the question found keeps the question's own score
    assert next(p.score for p in passages if p.document.metadata["passage_id"] == "dora-19") == 0.8


class TranslatingRetriever:
    def __init__(self):
        self.translations = []

    def search(self, question, k, strategy="vector", translation=None):
        self.translations.append(translation)
        trace = {
            "strategy": strategy,
            "translation": {"query": translation, "vector": []} if translation else None,
        }
        return HITS[:1], trace


def test_the_answer_model_gets_the_question_and_the_search_gets_both():
    retriever, answer_model = TranslatingRetriever(), RecordingModel()
    translator = RecordingTranslator("When must a major ICT-related incident be reported?")
    service = AnswerService(retriever, answer_model, "m", top_k=6, translators={"m": translator})
    response = service.ask("Wann muss ein schwerwiegender IKT-Vorfall gemeldet werden?")
    assert retriever.translations == ["When must a major ICT-related incident be reported?"]
    assert response.trace.translation.query == retriever.translations[0]
    assert response.trace.translation.language == "en"
    assert "translation" in response.trace.seconds
    assert response.usage.input_tokens == 200  # the translation call is part of the cost
    assert "Wann muss ein schwerwiegender IKT-Vorfall" in answer_model.seen[-1].content
    assert "ICT-related" not in answer_model.seen[-1].content


def test_without_a_translator_the_question_is_searched_alone():
    retriever = TranslatingRetriever()
    AnswerService(retriever, FakeModel(AIMessage(content="Yes [1].")), "m", top_k=6).ask(
        "Wann muss ein IKT-Vorfall gemeldet werden?"
    )
    assert retriever.translations == [None]


def test_an_eu_hosted_answer_model_translates_its_own_questions():
    """ADR 0007 and 0008: a question meant for an EU-hosted model never goes to another one."""
    settings = get_settings()
    models = {
        "openai/gpt-6-luna": "luna",
        "mistralai/mistral-large-4-0": "mistral",
        "anthropic/claude-sonnet-5.5": "claude",
    }
    assert helper_models(settings, models, "openai/gpt-6-luna") == {
        "openai/gpt-6-luna": "luna",
        "mistralai/mistral-large-4-0": "mistral",
        "anthropic/claude-sonnet-5.5": "luna",
    }


def test_the_export_records_the_translated_search():
    record = {
        "created_at": datetime(2026, 10, 30, 9, 0, tzinfo=UTC),
        "profile": None,
        "source_versions": {},
        "response": {
            "question": "Wann ist ein IKT-Vorfall schwerwiegend?",
            "answer": "Nach Art. 18 DORA [1].",
            "passages": [],
            "cited": [],
            "tools": [],
            "redactions": [],
            "usage": {"input_tokens": 1, "output_tokens": 1, "cost_usd": 0.0},
            "model": "m",
            "disclaimer": "Not legal advice.",
            "trace": {
                "strategy": "vector",
                "translation": {"query": "When is an ICT incident major?", "language": "en"},
            },
        },
    }
    assert "- Also searched as (en): When is an ICT incident major?" in to_markdown(record)


def test_the_evaluation_searches_with_the_translation_and_records_it():
    class Retriever_:
        def __init__(self):
            self.translations = []

        def retrieve(self, question, k, strategy="vector", translation=None):
            self.translations.append(translation)
            return [
                RetrievedPassage(
                    Document(page_content="t", metadata={"provision": "Art. 19 DORA"}), 0.5
                )
            ]

    item = GoldenItem(
        id="a",
        question="Wann melden?",
        language="de",
        regime="dora",
        expected=["Art. 19 DORA"],
        seed=True,
    )
    retriever = Retriever_()
    result = score_retrieval(
        retriever, [item], k=6, naive=False, translator=RecordingTranslator("When to report?")
    )
    assert retriever.translations == ["When to report?"]
    assert result["items"][0]["translation"] == "When to report?" and result["hit_at_k"] == 1.0
