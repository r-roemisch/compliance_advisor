"""Golden Set loading and retrieval scoring with a fake retriever."""

from types import SimpleNamespace

from langchain_core.documents import Document

from compliance_advisor.evaluation import (
    GoldenItem,
    half_of,
    load_golden,
    score_answers,
    score_retrieval,
)
from compliance_advisor.retriever import RetrievedPassage
from compliance_advisor.settings import get_settings


def test_golden_set_loads_and_marks_seed_items():
    items = load_golden(get_settings().config_dir / "golden_set.yaml")
    assert len(items) >= 20
    assert any(i.seed for i in items) and any(not i.seed for i in items)
    assert all(i.expected for i in items)


class FakeRetriever:
    def __init__(self, labels):
        self.labels = labels

    def retrieve(self, question, k, strategy="vector"):
        return [
            RetrievedPassage(Document(page_content="t", metadata={"provision": label}), 0.5)
            for label in self.labels[:k]
        ]


def test_scores_count_hits_ranks_and_recall():
    items = [
        GoldenItem(
            id="a",
            question="q",
            language="en",
            regime="dora",
            expected=["Art. 8 X", "Art. 18 DORA"],
            seed=True,
        ),
        GoldenItem(
            id="b", question="q", language="en", regime="dora", expected=["§ 10 GwG"], seed=True
        ),
    ]
    result = score_retrieval(
        FakeRetriever(["Art. 17 DORA", "Art. 18 DORA", "Art. 19 DORA"]), items, k=6, naive=False
    )
    assert result["hit_at_k"] == 0.5  # item a found at rank 2, item b not found
    assert result["mrr"] == 0.25  # (1/2 + 0) / 2
    assert result["recall_at_k"] == 0.25  # a: 1 of 2, b: 0 of 1


def test_scores_are_split_by_question_type_and_cross_lingual():
    def item(id, type, cross_lingual, expected):
        return GoldenItem(
            id=id,
            question="q",
            language="de",
            regime="dora",
            expected=[expected],
            seed=True,
            type=type,
            cross_lingual=cross_lingual,
        )

    items = [
        item("a", "lookup", False, "Art. 17 DORA"),
        item("b", "lookup", True, "§ 10 GwG"),
        item("c", "threshold", True, "Art. 18 DORA"),
    ]
    slices = score_retrieval(
        FakeRetriever(["Art. 17 DORA", "Art. 18 DORA"]), items, k=6, naive=False
    )["slices"]
    assert slices["lookup"] == {"n": 2, "hit_at_k": 0.5, "recall_at_k": 0.5, "mrr": 0.5}
    assert slices["threshold"]["hit_at_k"] == 1.0
    assert slices["cross-lingual"]["n"] == 2 and slices["cross-lingual"]["hit_at_k"] == 0.5
    assert slices["same language"] == {"n": 1, "hit_at_k": 1.0, "recall_at_k": 1.0, "mrr": 1.0}


class FakeService:
    """Answers every question for a fixed cost, citing one Passage."""

    def __init__(self, cost):
        self.cost = cost
        self.asked = 0

    def ask(self, question):
        self.asked += 1
        passage = SimpleNamespace(n=1, provision="Art. 17 DORA", source_id="eu-dora", text="t")
        return SimpleNamespace(
            answer="See [1].",
            cited=[1],
            passages=[passage],
            coverage="good",
            tools=[],
            usage=SimpleNamespace(cost_usd=self.cost),
        )


def test_answer_scoring_stops_at_the_cost_cap():
    items = [
        GoldenItem(
            id=str(n),
            question="q",
            language="en",
            regime="dora",
            expected=["Art. 17 DORA"],
            seed=True,
        )
        for n in range(10)
    ]
    service = FakeService(cost=0.04)
    result = score_answers(service, items, naive=False, max_cost=0.10)
    # Stops before the question that would start once $0.10 is reached: 0.04, 0.08, 0.12.
    assert service.asked == 3
    assert result["n"] == 3 and result["planned"] == 10
    assert result["cost_usd"] == 0.12
    assert result["cites_expected"] == 1.0


def test_golden_set_splits_into_two_fixed_halves():
    items = load_golden(get_settings().config_dir / "golden_set.yaml")
    tune = [i for i in items if half_of(i.id) == "tune"]
    assert 0.4 < len(tune) / len(items) < 0.6
    assert [half_of(i.id) for i in items] == [half_of(i.id) for i in items]  # stable
