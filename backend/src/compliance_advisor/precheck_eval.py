"""compliance-advisor-precheck-eval: measures the Pre-Check's screening (ADR 0007).

Runs config/precheck_set.yaml through the screening and reports two figures: how many attacks
were refused, and how many legitimate questions were wrongly refused. With --golden, every Golden
Set question is added as a legitimate one, because none of them should be refused. Every run is
appended to evaluation/results.jsonl and shown in docs/EVALUATION.md.
"""

import argparse
import json
import re
from datetime import UTC, datetime

import yaml
from pydantic import BaseModel

from .evaluation import RESULTS, load_golden, write_report
from .models import ModelOption, chat_model
from .precheck import VERDICTS, screen
from .settings import PROJECT_ROOT, get_settings


class PrecheckItem(BaseModel, extra="forbid"):
    id: str
    text: str
    language: str
    expected: str
    note: str = ""


def load_set(path) -> list[PrecheckItem]:
    items = [
        PrecheckItem.model_validate(i)
        for i in yaml.safe_load(path.read_text(encoding="utf-8"))["items"]
    ]
    for item in items:
        if item.expected not in VERDICTS:
            raise ValueError(f"{item.id}: expected must be one of {VERDICTS}")
    return items


def summarise(rows: list[dict]) -> dict:
    """Attacks refused (any category counts) and legitimate questions wrongly refused."""
    attacks = [r for r in rows if r["expected"] != "ok"]
    legitimate = [r for r in rows if r["expected"] == "ok"]
    caught = [r for r in attacks if r["verdict"] != "ok"]
    wrongly_refused = [r for r in legitimate if r["verdict"] != "ok"]
    return {
        "attacks": len(attacks),
        "attacks_refused": len(caught),
        "attacks_refused_share": round(len(caught) / len(attacks), 3) if attacks else None,
        "attacks_right_category": sum(r["verdict"] == r["expected"] for r in attacks),
        "legitimate": len(legitimate),
        "wrongly_refused": len(wrongly_refused),
        "wrongly_refused_share": (
            round(len(wrongly_refused) / len(legitimate), 3) if legitimate else None
        ),
        "missed": [r["id"] for r in attacks if r["verdict"] == "ok"],
        "wrongly_refused_ids": [r["id"] for r in wrongly_refused],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure the Pre-Check's screening.")
    parser.add_argument("--label", required=True, help="what changed, e.g. 'first prompt'")
    parser.add_argument("--model", help="screening model (default: settings.screening_model)")
    parser.add_argument(
        "--golden", action="store_true", help="also screen every Golden Set question (expected ok)"
    )
    parser.add_argument("--max-cost", type=float, default=0.10, metavar="USD")
    args = parser.parse_args()

    settings = get_settings()
    model_id = args.model or settings.screening_model
    model = chat_model(ModelOption(id=model_id, label=model_id), settings)
    items = [
        (i.id, i.text, i.expected, "set")
        for i in load_set(settings.config_dir / "precheck_set.yaml")
    ]
    if args.golden:
        items += [
            (g.id, g.question, "ok", "golden")
            for g in load_golden(settings.config_dir / "golden_set.yaml")
        ]

    rows: list[dict] = []
    cost = 0.0
    for item_id, text, expected, origin in items:
        if cost >= args.max_cost:
            print(f"stopped by the cost cap of {args.max_cost} $ after {len(rows)} questions")
            break
        verdict, reply = screen(text, model)
        reported = (getattr(reply, "response_metadata", None) or {}).get("token_usage") or {}
        cost += float(reported.get("cost") or 0.0)
        rows.append({"id": item_id, "origin": origin, "expected": expected, "verdict": verdict})
        mark = "  " if verdict == expected else "!!"
        print(f"{mark} {item_id:36} expected {expected:12} got {verdict}", flush=True)

    result = {
        "model": model_id,
        "n": len(rows),
        "planned": len(items),
        "set": summarise([r for r in rows if r["origin"] == "set"]),
        "cost_usd": round(cost, 4),
    }
    if args.golden:
        result["golden"] = summarise([r for r in rows if r["origin"] == "golden"])
    run = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "label": args.label,
        "golden_status": "draft",
        "golden_items": len(items),
        "k": 0,
        "retrieval": {},
        "answers": {},
        "precheck": result,
    }
    with RESULTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(run, ensure_ascii=False) + "\n")
    detail_dir = settings.data_dir / "eval"
    detail_dir.mkdir(parents=True, exist_ok=True)
    detail_file = detail_dir / (
        f"{run['run_at'][:19].replace(':', '')}-precheck-"
        f"{re.sub(r'[^a-z0-9]+', '-', args.label.lower())}.json"
    )
    detail_file.write_text(
        json.dumps({**run, "items": rows}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_report()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"Details in {detail_file.relative_to(PROJECT_ROOT)}; report docs/EVALUATION.md")
