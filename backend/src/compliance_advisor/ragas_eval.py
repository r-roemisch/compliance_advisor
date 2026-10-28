"""compliance-advisor-ragas: grades answers with RAGAs on a fixed sample of the Golden Set.

Two metrics (docs/ROADMAP.md, step E2):
  faithfulness         is every statement in the answer backed by what the Answer Model was given
                       (the Passages and the Rule Check results)?
  factual correctness  does the answer agree with the Golden Set's `answer_key`?

A second language model grades them, from another model family than the Answer Model, so it does
not favour its own family's answers. Grading costs money: a run starts no new question once answers
and grading, plus what the questions still running are expected to cost, would exceed --max-cost.

Needs the eval dependency group:
  uv run --group eval compliance-advisor-ragas --label "baseline"
Every run is appended to evaluation/results.jsonl and shown in docs/EVALUATION.md.
"""

import argparse
import asyncio
import hashlib
import json
import re
import statistics
from datetime import UTC, datetime

from .evaluation import RESULTS, GoldenItem, load_golden, make_retriever, write_report
from .models import chat_models, list_price, load_models
from .settings import OPENROUTER_BASE_URL, PROJECT_ROOT, get_settings

METRICS = ("faithfulness", "factual_correctness")
DEFAULT_GRADER = "google/gemma-4-31b-it"  # passes the OpenRouter guardrail, no forced reasoning


def _hash(item_id: str) -> str:
    return hashlib.sha256(item_id.encode()).hexdigest()


def sample_items(items: list[GoldenItem], n: int) -> list[GoldenItem]:
    """A fixed sample: questions in a stable pseudo-random order, taken in turn from each
    question type, so even rare types appear and every run grades the same questions."""
    by_type: dict[str, list[GoldenItem]] = {}
    for item in sorted(items, key=lambda i: _hash(i.id)):
        by_type.setdefault(item.type or "untyped", []).append(item)
    queues = [by_type[t] for t in sorted(by_type)]
    chosen: list[GoldenItem] = []
    while len(chosen) < n and any(queues):
        for queue in queues:
            if queue and len(chosen) < n:
                chosen.append(queue.pop(0))
    return chosen


def summarise(rows: list[dict], graders: list[str]) -> dict:
    """Mean score per grader and metric, ignoring gradings that failed; with two graders also
    how far apart they are on the same answers."""
    result: dict = {}
    for grader in graders:
        result[grader] = {}
        for metric in METRICS:
            values = [r["grades"][grader][metric] for r in rows]
            done = [v for v in values if v is not None]
            result[grader][metric] = round(statistics.mean(done), 3) if done else None
            result[grader][f"{metric}_failed"] = len(values) - len(done)
    if len(graders) == 2:
        a, b = graders
        result["agreement"] = {}
        for metric in METRICS:
            pairs = [
                (r["grades"][a][metric], r["grades"][b][metric])
                for r in rows
                if r["grades"][a][metric] is not None and r["grades"][b][metric] is not None
            ]
            result["agreement"][metric] = {
                "pairs": len(pairs),
                "mean_abs_diff": (
                    round(statistics.mean(abs(x - y) for x, y in pairs), 3) if pairs else None
                ),
            }
    return result


class Meter:
    """Adds up what answers and grading cost, from the cost OpenRouter reports for each call."""

    def __init__(self) -> None:
        self.answers = 0.0
        self.grading: dict[str, float] = {}
        self.finished = 0
        self.running = 0

    @property
    def total(self) -> float:
        return self.answers + sum(self.grading.values())

    def may_start(self, cap: float) -> bool:
        """Whether one more question fits under the cap, counting what the questions still
        running will cost at the average so far. The first questions run on trust; with a
        reasoning grader they can still cost more than the average suggests."""
        average = self.total / self.finished if self.finished else 0.0
        return self.total + average * (self.running + 1) <= cap

    def hook_for(self, grader: str):
        self.grading.setdefault(grader, 0.0)

        async def on_response(response) -> None:
            await response.aread()
            try:
                usage = response.json().get("usage") or {}
            except ValueError:
                return
            cost = usage.get("cost")
            if cost is None:  # fall back to list prices
                prices = list_price(grader) or (0.0, 0.0)
                cost = (usage.get("prompt_tokens") or 0) * prices[0] + (
                    usage.get("completion_tokens") or 0
                ) * prices[1]
            self.grading[grader] += cost

        return on_response


def _grader(model_id: str, api_key: str, meter: Meter):
    import httpx
    import openai
    from ragas.llms import llm_factory

    client = openai.AsyncOpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        max_retries=1,
        http_client=httpx.AsyncClient(
            timeout=120, event_hooks={"response": [meter.hook_for(model_id)]}
        ),
    )
    # ragas allows 1024 output tokens by default; the statement lists of a full answer need more,
    # and a reasoning model's thinking counts against the same limit.
    return llm_factory(model_id, client=client, max_tokens=4096)


def contexts_of(response) -> list[str]:
    """What the Answer Model was given: the Passages, and the Rule Check results it asked for."""
    contexts = [f"{p.provision}: {p.text}" for p in response.passages]
    contexts += [
        f"Rule Check {t.name}: {json.dumps(t.result, ensure_ascii=False)}" for t in response.tools
    ]
    return contexts


async def _grade(metrics: dict, item: GoldenItem, answer: str, contexts: list[str]) -> dict:
    async def safe(coroutine):
        try:
            return round(float((await coroutine).value), 3)
        # ragas and the structured-output layer raise many kinds of errors; a grader that
        # returns malformed output should fail only this one score, not the whole run.
        except Exception as e:  # noqa: BLE001
            return {"error": f"{type(e).__name__}: {e}"[:300]}

    faithfulness, correctness = await asyncio.gather(
        safe(
            metrics["faithfulness"].ascore(
                user_input=item.question, response=answer, retrieved_contexts=contexts
            )
        ),
        safe(metrics["factual_correctness"].ascore(response=answer, reference=item.answer_key)),
    )
    grades, errors = {}, {}
    for name, value in (("faithfulness", faithfulness), ("factual_correctness", correctness)):
        grades[name] = value if isinstance(value, float) else None
        if isinstance(value, dict):
            errors[name] = value["error"]
    return {**grades, "errors": errors} if errors else grades


async def run(args) -> dict:
    from ragas.metrics.collections import FactualCorrectness, Faithfulness

    from .answer import AnswerService
    from .embeddings import get_embeddings
    from .rulechecks import tool_factory

    settings = get_settings()
    items = [i for i in load_golden(settings.config_dir / "golden_set.yaml") if i.answer_key]
    chosen = sample_items(items, args.n)
    models = chat_models(settings)
    model_id = args.model or load_models(settings.models_file)[0].id
    retriever, _ = make_retriever("app", settings, get_embeddings(settings))
    service = AnswerService(
        retriever, models, model_id, args.k, tool_factory, list_price, strategy=args.strategy
    )
    meter = Meter()
    metrics = {}
    for grader in args.graders:
        llm = _grader(grader, settings.require_api_key(), meter)
        metrics[grader] = {
            "faithfulness": Faithfulness(llm=llm),
            "factual_correctness": FactualCorrectness(llm=llm),
        }

    gate = asyncio.Semaphore(args.concurrency)
    rows: list[dict] = []

    async def one(item: GoldenItem) -> None:
        async with gate:
            if not meter.may_start(args.max_cost):
                return
            meter.running += 1
            try:
                await answer_and_grade(item)
            finally:
                meter.running -= 1
                meter.finished += 1

    async def answer_and_grade(item: GoldenItem) -> None:
        response = await asyncio.to_thread(service.ask, item.question)
        meter.answers += response.usage.cost_usd
        answer = re.sub(r"\s+", " ", response.answer).strip()
        contexts = contexts_of(response)
        grades = await asyncio.gather(
            *(_grade(metrics[g], item, answer, contexts) for g in args.graders)
        )
        rows.append(
            {
                "id": item.id,
                "type": item.type,
                "language": item.language,
                "answer": answer,
                "answer_key": item.answer_key,
                "grades": dict(zip(args.graders, grades, strict=True)),
            }
        )
        print(
            f"{len(rows):3}/{len(chosen)} {item.id:40} "
            + "  ".join(
                f"{g.split('/')[-1]}: F {gr['faithfulness']} C {gr['factual_correctness']}"
                for g, gr in zip(args.graders, grades, strict=True)
            )
            + f"  (spent {meter.total:.3f} $)",
            flush=True,
        )

    await asyncio.gather(*(one(item) for item in chosen))
    order = {item.id: n for n, item in enumerate(chosen)}
    rows.sort(key=lambda r: order[r["id"]])
    return {
        "answer_model": model_id,
        "strategy": args.strategy,
        "n": len(rows),
        "planned": len(chosen),
        "graders": summarise(rows, args.graders),
        "cost_usd": {
            "answers": round(meter.answers, 4),
            **{g: round(c, 4) for g, c in meter.grading.items()},
        },
        "items": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Grade answers on a Golden Set sample with RAGAs.")
    parser.add_argument("--label", required=True, help="what changed, e.g. 'baseline'")
    parser.add_argument("--n", type=int, default=50, help="questions in the sample (default 50)")
    parser.add_argument("--model", help="Answer Model id (default: the first in models.yaml)")
    parser.add_argument("--strategy", choices=["vector", "hybrid"], default="vector")
    parser.add_argument(
        "--graders", nargs="+", default=[DEFAULT_GRADER], help="one grader, or two to compare"
    )
    parser.add_argument(
        "--max-cost",
        type=float,
        default=0.25,
        metavar="USD",
        help="no new question is started once answers and grading cost this much (default 0.25)",
    )
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--k", type=int, default=6)
    args = parser.parse_args()

    settings = get_settings()
    result = asyncio.run(run(args))
    items = result.pop("items")
    run_record = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "label": args.label,
        "golden_status": "draft",
        "golden_items": result["planned"],
        "k": args.k,
        "retrieval": {},
        "answers": {},
        "ragas": result,
    }
    with RESULTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(run_record, ensure_ascii=False) + "\n")
    detail_dir = settings.data_dir / "eval"
    detail_dir.mkdir(parents=True, exist_ok=True)
    detail_file = detail_dir / (
        f"{run_record['run_at'][:19].replace(':', '')}-ragas-"
        f"{re.sub(r'[^a-z0-9]+', '-', args.label.lower())}.json"
    )
    detail_file.write_text(
        json.dumps({**run_record, "items": items}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_report()
    print(json.dumps(result, indent=2))
    if result["n"] < result["planned"]:
        print(f"Stopped by the cost cap after {result['n']} of {result['planned']} questions.")
    print(f"Details in {detail_file.relative_to(PROJECT_ROOT)}; report docs/EVALUATION.md")
