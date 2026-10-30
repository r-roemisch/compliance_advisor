"""compliance-advisor-eval: scores retrieval (and optionally answers) against the Golden Set.

Retrieval set-ups, so each change is measured on its own:
  naive        fixed-size Passages of the first six Sources, plain top-k   (the step 1 baseline)
  provision    one Passage per Provision, plain top-k
  lookup       one Passage per Provision, direct lookup of named Provisions, no cap
  cap          one Passage per Provision, per-Source cap, no lookup
  app          what the app does: per Provision, direct lookup of named Provisions, and the
               per-Source cap when MAX_PER_SOURCE is set (it is off since 2026-10-23)
  translated   as app, with Query Translation: the question is also searched in the Corpus's
               other language, merged by RRF (one short TRANSLATION_MODEL call per question)
  hybrid       the app's hybrid search: keyword ranks at KEYWORD_WEIGHT (0.5), merged by RRF
  hybrid-full  as hybrid, with keyword ranks at full weight (the first variant measured)
  hybrid-rerank    as hybrid-full, but keyword search only re-sorts the vector candidates

--halves adds a fixed split of the Golden Set: choose between variants on the tuning half, then
report the held-out half, so a variant is not picked for fitting these very questions.

Every run is appended to evaluation/results.jsonl and summarised in docs/EVALUATION.md, split
by question type and by cross-lingual questions as well. Answer generation costs money, so it
stops at a cost cap (--max-cost, default 0.25 $).
"""

import argparse
import hashlib
import json
import re
import statistics
import time
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

from .answer import AnswerService
from .embeddings import get_embeddings
from .loaders import load
from .models import ModelOption, chat_model, chat_models, helper_models, load_models, system_prompts
from .query_translation import translate
from .registry import load_sources
from .retriever import Retriever
from .settings import PROJECT_ROOT, Settings, get_settings
from .store import get_store

RESULTS = PROJECT_ROOT / "evaluation" / "results.jsonl"
REPORT = PROJECT_ROOT / "docs" / "EVALUATION.md"


class GoldenItem(BaseModel, extra="forbid"):
    id: str
    question: str
    language: str
    regime: str
    expected: list[str]
    seed: bool
    status: str = "draft"
    notes: str = ""
    # For slicing results and reviewing; not used by the retrieval metric.
    type: str = ""
    cross_lingual: bool = False
    origin: str = "drafted"
    source_url: str | None = None
    answer_key: str = ""


def half_of(item_id: str) -> str:
    """A fixed split by id: "tune" or "test", about half each, the same in every run."""
    return "tune" if hashlib.sha256(item_id.encode()).digest()[0] % 2 == 0 else "test"


def load_golden(path: Path) -> list[GoldenItem]:
    items = [
        GoldenItem.model_validate(i)
        for i in yaml.safe_load(path.read_text(encoding="utf-8"))["items"]
    ]
    return [i for i in items if i.status != "rejected"]


# --- Mapping naive Passages to Provisions ------------------------------------------------------


def _norm(text: str) -> str:
    return re.sub(r"[^0-9a-zäöüß]", "", text.lower())


@lru_cache(maxsize=32)
def _provision_texts(source_id: str) -> list[tuple[str, str]]:
    settings = get_settings()
    source = next(s for s in load_sources(settings.sources_file) if s.id == source_id)
    loaded = load(source, settings.raw_dir)
    return [(f"{s.label} {source.short_title}", _norm(s.text)) for s in loaded.sections]


def provisions_of_chunk(source_id: str, text: str) -> list[str]:
    """The Provisions a naive fixed-size Passage overlaps, found by locating probes of its text."""
    norm = _norm(text)
    if len(norm) < 40:
        return []
    probes = {
        norm[i : i + 40]
        for i in (0, len(norm) // 4, len(norm) // 2, 3 * len(norm) // 4, len(norm) - 40)
    }
    found = []
    for label, section in _provision_texts(source_id):
        if any(p in section for p in probes) and label not in found:
            found.append(label)
    return found


# --- Retrieval scoring -------------------------------------------------------------------------


def labels_of(hit, naive: bool) -> list[str]:
    meta = hit.document.metadata
    if naive:
        return provisions_of_chunk(meta["source_id"], hit.document.page_content)
    return [meta.get("provision", "")]


def score_retrieval(
    retriever: Retriever,
    items: list[GoldenItem],
    k: int,
    naive: bool,
    strategy: str = "vector",
    translator=None,
) -> dict:
    """With a `translator` model, every question is translated first and both are searched, as
    the app does with Query Translation; each row then records the translation."""
    rows = []
    for item in items:
        translation = translate(item.question, translator)[0] if translator else None
        translated = {"translation": translation.query} if translation else {}
        hits = retriever.retrieve(item.question, k, strategy, **translated)
        ranked = [labels_of(h, naive) for h in hits]
        first = next(
            (
                rank
                for rank, labels in enumerate(ranked, start=1)
                if set(labels) & set(item.expected)
            ),
            None,
        )
        found = {e for e in item.expected if any(e in labels for labels in ranked)}
        rows.append(
            {
                "id": item.id,
                "hit": first is not None,
                "rank": first,
                "recall": len(found) / len(item.expected),
                "retrieved": [", ".join(labels) or "?" for labels in ranked],
                "type": item.type or "untyped",
                "cross_lingual": item.cross_lingual,
                **(
                    {"translation": translation.query if translation else None}
                    if translator
                    else {}
                ),
            }
        )
    return {**_summarise(rows), "slices": slices_of(rows), "items": rows}


def _summarise(rows: list[dict]) -> dict:
    return {
        "n": len(rows),
        "hit_at_k": round(sum(r["hit"] for r in rows) / len(rows), 3),
        "recall_at_k": round(statistics.mean(r["recall"] for r in rows), 3),
        "mrr": round(statistics.mean(1 / r["rank"] if r["rank"] else 0 for r in rows), 3),
    }


def slices_of(rows: list[dict]) -> dict:
    """The same metrics per question type, and for cross-lingual against same-language questions,
    so a change that helps one kind of question cannot hide a loss on another."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["type"], []).append(r)
        groups.setdefault("cross-lingual" if r["cross_lingual"] else "same language", []).append(r)
    return {name: _summarise(group) for name, group in groups.items()}


# --- Answer scoring ----------------------------------------------------------------------------

_NUMBERS = re.compile(r"\[(\d+)\]")


def score_answers(
    service: AnswerService, items: list[GoldenItem], naive: bool, max_cost: float | None = None
) -> dict:
    """Answers and scores each question. With `max_cost`, no new question is started once the
    answers so far cost that much, so a run can overshoot the cap by one answer at most."""
    rows = []
    for item in items:
        if max_cost is not None and sum(r["cost_usd"] for r in rows) >= max_cost:
            break
        started = time.monotonic()
        r = service.ask(item.question)
        raw = [int(n) for n in _NUMBERS.findall(r.answer)]
        cited_labels = {
            label
            for p in r.passages
            if p.n in r.cited
            for label in (provisions_of_chunk(p.source_id, p.text) if naive else [p.provision])
        }
        rows.append(
            {
                "id": item.id,
                "has_citation": bool(r.cited),
                "invalid_numbers": sorted({n for n in raw if n < 1 or n > len(r.passages)}),
                "cites_expected": bool(cited_labels & set(item.expected)),
                "coverage": r.coverage,
                "tools": [t.name for t in r.tools],
                "seconds": round(time.monotonic() - started, 1),
                "cost_usd": r.usage.cost_usd,
            }
        )
    n = len(rows)
    return {
        "n": n,
        "planned": len(items),
        "answers_with_citations": round(sum(r["has_citation"] for r in rows) / n, 3),
        "citations_valid": round(sum(not r["invalid_numbers"] for r in rows) / n, 3),
        "cites_expected": round(sum(r["cites_expected"] for r in rows) / n, 3),
        "avg_seconds": round(statistics.mean(r["seconds"] for r in rows), 1),
        "cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
        "items": rows,
    }


# --- Set-ups -----------------------------------------------------------------------------------


def strategy_of(setup: str) -> str:
    return "hybrid" if setup.startswith("hybrid") else "vector"


def make_retriever(name: str, settings: Settings, embeddings) -> tuple[Retriever, bool]:
    if name == "naive":
        store = get_store(settings.model_copy(update={"chunker": "fixed"}), embeddings)
        return Retriever(store), True
    store = get_store(settings.model_copy(update={"chunker": "provision"}), embeddings)
    if name == "provision":
        return Retriever(store), False
    titles = [s.short_title for s in load_sources(settings.sources_file)]
    if name == "lookup":
        return Retriever(store, 0, settings.candidates, titles), False
    if name == "cap":
        return Retriever(store, settings.max_per_source, settings.candidates), False
    variant = {
        "hybrid": {"keyword_weight": settings.keyword_weight},
        "hybrid-full": {"keyword_weight": 1.0},
        "hybrid-rerank": {"keyword_scope": "candidates", "keyword_weight": 1.0},
    }.get(name, {})
    return Retriever(store, settings.max_per_source, settings.candidates, titles, **variant), False


SLICE_ORDER = [
    "lookup",
    "threshold",
    "definition",
    "applicability",
    "scenario",
    "cross_regime",
    "crowding",
    "temporal",
    "cross-lingual",
    "same language",
]


def _ragas_cell(scores: dict, metric: str) -> str:
    value, failed = scores[metric], scores[f"{metric}_failed"]
    text = "?" if value is None else f"{value:.2f}"
    return f"{text} ({failed} failed)" if failed else text


def write_report() -> None:
    runs = [json.loads(line) for line in RESULTS.read_text().splitlines() if line.strip()]
    lines = [
        "# Evaluation log",
        "",
        "Each run of `compliance-advisor-eval` appends one line to `evaluation/results.jsonl`; this page is",
        "regenerated from it. The Golden Set is `config/golden_set.yaml`.",
        "",
        "**Metrics.** *hit@6*: share of questions where at least one expected Provision is among the six",
        "Passages. *recall@6*: share of the expected Provisions found, averaged. *MRR*: mean of 1/rank of",
        "the first expected Provision (1.0 = always first). For answers: *citations valid*: no citation",
        "points to a Passage that does not exist; *cites expected*: the answer cites an expected Provision.",
        "",
        "**Subsets.** *seed*: questions the naive baseline index can answer; *all*: the whole Golden Set;",
        "*tune* and *test*: a fixed split into halves. A variant is chosen on *tune* and reported on *test*,",
        "so it is not picked for fitting these very questions.",
        "",
        "**Hybrid search (2026-10-28).** Keyword search merged with vector search lost to vector search on",
        "both halves. It pulls in Passages that share words with the question but not its meaning: German",
        "texts for German questions about English EU acts, and recitals that repeat an act's name. Half",
        "weight for the keyword ranks was the best variant on *tune* (0.82 against 0.88 for vector) and",
        "stayed behind on *test* (0.81 against 0.83). Vector search stays the default; hybrid search can be",
        "chosen per question, with half weight.",
        "",
        "## Retrieval",
        "",
        "| Run | Label | Golden Set | Set-up | Questions | hit@6 | recall@6 | MRR |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for run in runs:
        for setup, subsets in run["retrieval"].items():
            for subset, m in subsets.items():
                lines.append(
                    f"| {run['run_at'][:16]} | {run['label']} | {run['golden_status']} | {setup} ({subset}) | "
                    f"{m['n']} | {m['hit_at_k']:.2f} | {m['recall_at_k']:.2f} | {m['mrr']:.2f} |"
                )
    sliced = [
        run
        for run in runs
        if any("slices" in m for s in run["retrieval"].values() for m in s.values())
    ]
    if sliced:
        lines += [
            "",
            "## Retrieval by kind of question",
            "",
            "hit@6 per question type, and for cross-lingual questions (asked in another language than an",
            "expected Source) against same-language ones. Number of questions in brackets.",
        ]
    for run in sliced:
        present = {
            name
            for s in run["retrieval"].values()
            for m in s.values()
            for name in m.get("slices", {})
        }
        columns = [c for c in SLICE_ORDER if c in present] + sorted(present - set(SLICE_ORDER))
        lines += [
            "",
            f"**{run['run_at'][:16]}, {run['label']}**",
            "",
            "| Set-up | " + " | ".join(columns) + " |",
            "|---|" + "---|" * len(columns),
        ]
        for setup, subsets in run["retrieval"].items():
            for subset, m in subsets.items():
                cells = [
                    f"{m['slices'][c]['hit_at_k']:.2f} ({m['slices'][c]['n']})"
                    if c in m.get("slices", {})
                    else ""
                    for c in columns
                ]
                lines.append(f"| {setup} ({subset}) | " + " | ".join(cells) + " |")
    if any(run.get("answers") for run in runs):
        lines += [
            "",
            "## Answers",
            "",
            "| Run | Label | Set-up | Questions | with citations | citations valid | cites expected | avg s | cost $ |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for run in runs:
            for setup, m in (run.get("answers") or {}).items():
                planned = m.get("planned", m["n"])
                questions = m["n"] if m["n"] == planned else f"{m['n']} of {planned} (cost cap)"
                lines.append(
                    f"| {run['run_at'][:16]} | {run['label']} | {setup} | {questions} | {m['answers_with_citations']:.2f} | "
                    f"{m['citations_valid']:.2f} | {m['cites_expected']:.2f} | {m['avg_seconds']} | {m['cost_usd']} |"
                )
    graded = [run for run in runs if run.get("ragas")]
    if graded:
        lines += [
            "",
            "## Answers graded with RAGAs",
            "",
            "On a fixed sample of the Golden Set (`compliance-advisor-ragas`). *Faithfulness*: share of the",
            "answer's statements backed by the Passages and Rule Check results the Answer Model was given.",
            "*Factual correctness*: agreement with the `answer_key` (F1 of matching claims). Small samples:",
            "differences of a few points can be chance. With two graders, *apart* is the mean absolute",
            "difference of their scores on the same answers.",
            "",
            "**Grader.** Gemma 4 31B (Google, through OpenRouter), chosen on 2026-10-28 by grading the same",
            "ten answers with Gemini 3.8 Flash as well. On faithfulness the two agreed (0.03 apart). On factual",
            "correctness they were 0.22 apart, more than the 0.15 set beforehand as the limit: Gemini scored",
            "lower throughout and gave 0.0 to answers that do match the `answer_key` in the cases checked, four",
            "of its ten faithfulness gradings were cut off even at 4,096 output tokens, and it cost 13 times",
            "more. So factual correctness is read as a comparison between runs with the same grader, not as an",
            "absolute score. The first calibration run failed on most answers because ragas allows graders",
            "1,024 output tokens by default; the limit is now 4,096.",
            "",
            "| Run | Label | Answer Model | Strategy | Questions | Grader | Faithfulness | Factual correctness | apart (F / C) | Cost $ |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
    for run in graded:
        r = run["ragas"]
        questions = r["n"] if r["n"] == r["planned"] else f"{r['n']} of {r['planned']} (cost cap)"
        agreement = r["graders"].get("agreement")
        apart = (
            " / ".join(
                f"{agreement[m]['mean_abs_diff']:.2f}"
                if agreement[m]["mean_abs_diff"] is not None
                else "?"
                for m in ("faithfulness", "factual_correctness")
            )
            if agreement
            else ""
        )
        for grader, scores in r["graders"].items():
            if grader == "agreement":
                continue

            lines.append(
                f"| {run['run_at'][:16]} | {run['label']} | {r['answer_model']} | "
                f"{r['strategy']}{' + translation' if r.get('query_translation') else ''} | "
                f"{questions} | {grader} | {_ragas_cell(scores, 'faithfulness')} | {_ragas_cell(scores, 'factual_correctness')} | "
                f"{apart} | {sum(r['cost_usd'].values()):.3f} |"
            )
    screened = [run for run in runs if run.get("precheck")]
    if screened:
        lines += [
            "",
            "## Pre-Check screening",
            "",
            "`config/precheck_set.yaml` holds attacks (manipulation attempts and off-topic questions) that",
            "must be refused, and legitimate questions that look suspicious and must pass. *Refused* counts",
            "a refusal in either category; *right category* how often the reason was the expected one.",
            "*Wrongly refused* is the share of legitimate questions the screening refused. With `--golden`,",
            "every Golden Set question is screened as well; none of them should be refused.",
            "",
            "| Run | Label | Screening model | Attacks refused | right category | Legitimate wrongly refused | Golden Set wrongly refused | Cost $ |",
            "|---|---|---|---|---|---|---|---|",
        ]
    for run in screened:
        r, s = run["precheck"], run["precheck"]["set"]
        golden = run["precheck"].get("golden")
        golden_cell = f"{golden['wrongly_refused']} of {golden['legitimate']}" if golden else ""
        lines.append(
            f"| {run['run_at'][:16]} | {run['label']} | {r['model']} | "
            f"{s['attacks_refused']} of {s['attacks']} | {s['attacks_right_category']} of {s['attacks']} | "
            f"{s['wrongly_refused']} of {s['legitimate']} | {golden_cell} | {r['cost_usd']:.3f} |"
        )
    lines += ["", "_Regulatory information, not legal advice._", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score retrieval (and answers) against the Golden Set."
    )
    parser.add_argument(
        "--label", required=True, help="what changed, e.g. 'baseline' or 'hybrid search'"
    )
    parser.add_argument(
        "--setups",
        nargs="+",
        default=["naive", "provision", "app"],
        choices=[
            "naive",
            "provision",
            "lookup",
            "cap",
            "app",
            "translated",
            "hybrid",
            "hybrid-full",
            "hybrid-rerank",
        ],
    )
    parser.add_argument(
        "--halves", action="store_true", help="also score the tuning and the held-out half"
    )
    parser.add_argument(
        "--answers", action="store_true", help="also generate and score answers (costs a few cents)"
    )
    parser.add_argument(
        "--max-cost",
        type=float,
        default=0.25,
        metavar="USD",
        help="stop generating answers once they cost this much in total (default 0.25)",
    )
    parser.add_argument("--k", type=int, default=6)
    args = parser.parse_args()

    settings = get_settings()
    items = load_golden(settings.config_dir / "golden_set.yaml")
    seed = [i for i in items if i.seed]
    statuses = {i.status for i in items}
    embeddings = get_embeddings(settings)

    run: dict = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "label": args.label,
        "golden_status": "reviewed" if statuses == {"reviewed"} else "draft",
        "golden_items": len(items),
        "k": args.k,
        "retrieval": {},
        "answers": {},
    }
    details: dict = {"retrieval": {}, "answers": {}}
    for name in args.setups:
        retriever, naive = make_retriever(name, settings, embeddings)
        subsets = {"seed": seed} if naive else {"seed": seed, "all": items}
        if args.halves and not naive:
            subsets["tune"] = [i for i in items if half_of(i.id) == "tune"]
            subsets["test"] = [i for i in items if half_of(i.id) == "test"]
        run["retrieval"][name] = {}
        translator = None
        if name == "translated":
            option = ModelOption(id=settings.translation_model, label=settings.translation_model)
            translator = chat_model(option, settings)
        # Every question is searched once per set-up; the subsets are cut from those rows.
        scored = score_retrieval(
            retriever, seed if naive else items, args.k, naive, strategy_of(name), translator
        )["items"]
        for subset, chosen in subsets.items():
            ids = {i.id for i in chosen}
            rows = [r for r in scored if r["id"] in ids]
            result = {**_summarise(rows), "slices": slices_of(rows)}
            details["retrieval"][f"{name}/{subset}"] = rows
            run["retrieval"][name][subset] = result
            print(
                f"{name:10} {subset:5} n={result['n']:2}  hit@{args.k} {result['hit_at_k']:.2f}  "
                f"recall {result['recall_at_k']:.2f}  MRR {result['mrr']:.2f}"
            )

    if args.answers:
        models = chat_models(settings)
        default = load_models(settings.models_file)[0].id
        remaining = args.max_cost
        answered = ("naive", "app", "translated")
        for name in [s for s in args.setups if s in answered or s.startswith("hybrid")]:
            if remaining <= 0:
                print(f"answers {name:6} skipped: cost cap of {args.max_cost} $ reached")
                continue
            retriever, naive = make_retriever(name, settings, embeddings)
            tools = None
            if name != "naive":
                from .rulechecks import tool_factory  # the app's own Rule Checks

                tools = tool_factory
            service = AnswerService(
                retriever,
                models,
                default,
                args.k,
                tools,
                strategy=strategy_of(name),
                prompts=system_prompts(settings.models_file),
                translators=(
                    helper_models(settings, models, settings.translation_model)
                    if name == "translated"
                    else None
                ),
            )
            result = score_answers(service, seed if naive else items, naive, remaining)
            remaining -= result["cost_usd"]
            details["answers"][name] = result.pop("items")
            run["answers"][name] = result
            print(
                f"answers {name:6} n={result['n']:2}  citations {result['answers_with_citations']:.2f}  "
                f"valid {result['citations_valid']:.2f}  expected {result['cites_expected']:.2f}  "
                f"{result['avg_seconds']} s  {result['cost_usd']} $"
            )
            if result["n"] < result["planned"]:
                print(
                    f"  stopped by the cost cap after {result['n']} of {result['planned']} questions"
                )

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(run, ensure_ascii=False) + "\n")
    detail_dir = settings.data_dir / "eval"
    detail_dir.mkdir(parents=True, exist_ok=True)
    detail_file = (
        detail_dir
        / f"{run['run_at'][:19].replace(':', '')}-{re.sub(r'[^a-z0-9]+', '-', args.label.lower())}.json"
    )
    detail_file.write_text(
        json.dumps({**run, "details": details}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_report()
    print(
        f"Logged to {RESULTS.relative_to(PROJECT_ROOT)}; details in {detail_file.relative_to(PROJECT_ROOT)}; "
        f"report {REPORT.relative_to(PROJECT_ROOT)}"
    )
