"""RAGAs grading: the fixed sample and the summary, without network or the ragas package."""

from collections import Counter

from compliance_advisor.evaluation import load_golden
from compliance_advisor.ragas_eval import Meter, sample_items, summarise
from compliance_advisor.settings import get_settings


def test_sample_is_fixed_and_covers_every_question_type():
    items = load_golden(get_settings().config_dir / "golden_set.yaml")
    first, again = sample_items(items, 50), sample_items(list(reversed(items)), 50)
    assert [i.id for i in first] == [i.id for i in again]  # same questions in every run
    assert len(first) == 50 and len({i.id for i in first}) == 50
    types = Counter(i.type for i in first)
    assert set(types) == {i.type for i in items}  # rare types are included too
    assert [i.id for i in sample_items(items, 10)] == [i.id for i in first[:10]]


def test_summary_averages_ignore_failures_and_measure_agreement():
    rows = [
        {
            "grades": {
                "a": {"faithfulness": 1.0, "factual_correctness": 0.5},
                "b": {"faithfulness": 0.8, "factual_correctness": None},
            }
        },
        {
            "grades": {
                "a": {"faithfulness": 0.5, "factual_correctness": 1.0},
                "b": {"faithfulness": 0.5, "factual_correctness": 0.6},
            }
        },
    ]
    summary = summarise(rows, ["a", "b"])
    assert summary["a"] == {
        "faithfulness": 0.75,
        "faithfulness_failed": 0,
        "factual_correctness": 0.75,
        "factual_correctness_failed": 0,
    }
    assert summary["b"]["factual_correctness"] == 0.6
    assert summary["b"]["factual_correctness_failed"] == 1
    assert summary["agreement"]["faithfulness"] == {"pairs": 2, "mean_abs_diff": 0.1}
    assert summary["agreement"]["factual_correctness"] == {"pairs": 1, "mean_abs_diff": 0.4}


def test_cost_cap_counts_the_questions_still_running():
    meter = Meter()
    assert meter.may_start(0.10)  # nothing known yet: the first questions run on trust
    meter.answers, meter.finished = 0.06, 2  # 0.03 $ per question so far
    meter.running = 1
    # 0.06 spent + 0.03 for the running one + 0.03 for a new one = 0.12 > 0.10
    assert not meter.may_start(0.10)
    meter.running = 0
    assert meter.may_start(0.10)  # 0.06 + 0.03 = 0.09
