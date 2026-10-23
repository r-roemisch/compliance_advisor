"""Golden Set loading and retrieval scoring with a fake retriever."""

from langchain_core.documents import Document

from compliance_advisor.evaluation import GoldenItem, load_golden, score_retrieval
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

    def retrieve(self, question, k):
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
