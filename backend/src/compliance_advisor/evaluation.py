"""compliance-advisor-eval: scores retrieval (and optionally answers) against the Golden Set.

Retrieval set-ups, so each change is measured on its own:
  naive        fixed-size Passages of the first six Sources, plain top-k   (the step 1 baseline)
  provision    one Passage per Provision, plain top-k
  lookup       one Passage per Provision, direct lookup of named Provisions, no cap
  cap          one Passage per Provision, per-Source cap, no lookup
  app          one Passage per Provision, per-Source cap, direct lookup of named Provisions

Every run is appended to evaluation/results.jsonl and summarised in docs/EVALUATION.md.
"""

import argparse
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
from .models import chat_models, load_models
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


def score_retrieval(retriever: Retriever, items: list[GoldenItem], k: int, naive: bool) -> dict:
    rows = []
    for item in items:
        hits = retriever.retrieve(item.question, k)
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
            }
        )
    return {
        "n": len(rows),
        "hit_at_k": round(sum(r["hit"] for r in rows) / len(rows), 3),
        "recall_at_k": round(statistics.mean(r["recall"] for r in rows), 3),
        "mrr": round(statistics.mean(1 / r["rank"] if r["rank"] else 0 for r in rows), 3),
        "items": rows,
    }


# --- Answer scoring ----------------------------------------------------------------------------

_NUMBERS = re.compile(r"\[(\d+)\]")


def score_answers(service: AnswerService, items: list[GoldenItem], naive: bool) -> dict:
    rows = []
    for item in items:
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
        "answers_with_citations": round(sum(r["has_citation"] for r in rows) / n, 3),
        "citations_valid": round(sum(not r["invalid_numbers"] for r in rows) / n, 3),
        "cites_expected": round(sum(r["cites_expected"] for r in rows) / n, 3),
        "avg_seconds": round(statistics.mean(r["seconds"] for r in rows), 1),
        "cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
        "items": rows,
    }


# --- Set-ups -----------------------------------------------------------------------------------


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
    return Retriever(store, settings.max_per_source, settings.candidates, titles), False


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
                lines.append(
                    f"| {run['run_at'][:16]} | {run['label']} | {setup} | {m['n']} | {m['answers_with_citations']:.2f} | "
                    f"{m['citations_valid']:.2f} | {m['cites_expected']:.2f} | {m['avg_seconds']} | {m['cost_usd']} |"
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
        choices=["naive", "provision", "lookup", "cap", "app"],
    )
    parser.add_argument(
        "--answers", action="store_true", help="also generate and score answers (costs a few cents)"
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
        run["retrieval"][name] = {}
        for subset, chosen in subsets.items():
            result = score_retrieval(retriever, chosen, args.k, naive)
            details["retrieval"][f"{name}/{subset}"] = result.pop("items")
            run["retrieval"][name][subset] = result
            print(
                f"{name:10} {subset:5} n={result['n']:2}  hit@{args.k} {result['hit_at_k']:.2f}  "
                f"recall {result['recall_at_k']:.2f}  MRR {result['mrr']:.2f}"
            )

    if args.answers:
        models = chat_models(settings)
        default = load_models(settings.models_file)[0].id
        for name in [s for s in args.setups if s in ("naive", "app")]:
            retriever, naive = make_retriever(name, settings, embeddings)
            tools = None
            if name == "app":
                from .api import tool_factory  # the app's own Rule Checks

                tools = tool_factory
            service = AnswerService(retriever, models, default, args.k, tools)
            result = score_answers(service, seed if naive else items, naive)
            details["answers"][name] = result.pop("items")
            run["answers"][name] = result
            print(
                f"answers {name:6} n={result['n']:2}  citations {result['answers_with_citations']:.2f}  "
                f"valid {result['citations_valid']:.2f}  expected {result['cites_expected']:.2f}  "
                f"{result['avg_seconds']} s  {result['cost_usd']} $"
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
