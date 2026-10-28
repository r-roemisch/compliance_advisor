"""Monitoring for the Operator (ADR 0006): figures across all Accounts, never question texts.

Two sources: the audit trail (one row per answer, with model, Search Strategy, cost, seconds and
whether the Pre-Check refused it) and an events table for what the audit trail cannot hold,
such as failed requests. Logs are structured (one JSON object per line) and carry no question
text either.
"""

import json
import logging
import uuid
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Column, DateTime, String, Table, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

from .audit import answers, metadata

# Failed requests that could not be written to the database (a 503 means it is down), kept
# in memory since the backend started.
memory_errors: Counter = Counter()

events = Table(
    "events",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("at", DateTime(timezone=True), nullable=False, index=True),
    Column("kind", String(40), nullable=False),  # error | update_run
    Column("data", JSONB, nullable=False),  # figures and codes only, no question text
)


class JsonFormatter(logging.Formatter):
    """One JSON object per log line, so a log collector can read fields without parsing."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(fmt: str) -> None:
    handler = logging.StreamHandler()
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


class EventStore:
    def __init__(self, engine: Engine):
        self.engine = engine
        metadata.create_all(engine, checkfirst=True)

    def record(self, kind: str, **data) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                events.insert().values(
                    id=str(uuid.uuid4()), at=datetime.now(UTC), kind=kind, data=data
                )
            )

    def since(self, start: datetime | None, kind: str | None = None) -> list[dict]:
        query = select(events.c.at, events.c.kind, events.c.data).order_by(events.c.at.desc())
        if start is not None:
            query = query.where(events.c.at >= start)
        if kind:
            query = query.where(events.c.kind == kind)
        with self.engine.connect() as connection:
            return [dict(r._mapping) for r in connection.execute(query)]

    def answer_rows(self, start: datetime | None) -> list[dict]:
        """What the overview needs from every answer, across all Accounts: no question text."""
        response = answers.c.response
        query = select(
            answers.c.created_at,
            answers.c.model,
            answers.c.user_id,
            answers.c.api_key,
            response["strategy"].astext.label("strategy"),
            response["refusal"].astext.label("refusal"),
            (
                response["usage"]["cost_usd"].as_float()
                + func.coalesce(answers.c.obligations_cost, 0.0)
            ).label("cost"),
            response["trace"]["seconds"]["total"].as_float().label("seconds"),
            response["passages"][0]["score"].as_float().label("top_score"),
            response["coverage"].astext.label("coverage"),
            func.jsonb_array_length(response["cited"]).label("cited"),
        )
        if start is not None:
            query = query.where(answers.c.created_at >= start)
        with self.engine.connect() as connection:
            return [dict(r._mapping) for r in connection.execute(query)]


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def overview(rows: list[dict], errors: list[dict], days: int, today: date) -> dict:
    """The Operator's figures for the period: volume, cost, speed, quality signals, refusals and
    errors. `rows` come from EventStore.answer_rows, `errors` from EventStore.since."""
    answered = [r for r in rows if not r["refusal"]]
    by_day: Counter = Counter(r["created_at"].date().isoformat() for r in rows)
    first = today - timedelta(days=days - 1) if days else None
    if first is None and rows:
        first = min(r["created_at"].date() for r in rows)
    activity = []
    if first:
        d = first
        while d <= today:
            activity.append({"date": d.isoformat(), "count": by_day.get(d.isoformat(), 0)})
            d += timedelta(days=1)

    def group(key: str) -> list[dict]:
        cost: dict[str, float] = defaultdict(float)
        count: Counter = Counter()
        for r in rows:
            name = r[key] or "vector"
            cost[name] += r["cost"] or 0.0
            count[name] += 1
        return [
            {"id": k, "questions": count[k], "cost_usd": round(cost[k], 4)}
            for k in sorted(count, key=lambda k: -count[k])
        ]

    error_kinds: Counter = Counter(e["data"].get("status", "?") for e in errors)
    return {
        "days": days,
        "stats": {
            "questions": len(rows),
            "answered": len(answered),
            "refused": len(rows) - len(answered),
            "accounts": len({r["user_id"] for r in rows if r["user_id"]}),
            "guest_questions": sum(1 for r in rows if not r["user_id"]),
            "via_api_key": sum(1 for r in rows if r["api_key"]),
            "cost_usd": round(sum(r["cost"] or 0.0 for r in rows), 4),
            "errors": len(errors),
            "avg_seconds": _mean([r["seconds"] for r in answered if r["seconds"] is not None]),
            "avg_top_score": _mean(
                [r["top_score"] for r in answered if r["top_score"] is not None]
            ),
            "cited_share": _mean([1.0 if (r["cited"] or 0) > 0 else 0.0 for r in answered]),
            "coverage_full_share": _mean(
                [1.0 if r["coverage"] == "full" else 0.0 for r in answered]
            ),
        },
        "activity": activity,
        "models": group("model"),
        "strategies": group("strategy"),
        "refusals": [
            {"reason": reason, "count": n}
            for reason, n in Counter(r["refusal"] for r in rows if r["refusal"]).most_common()
        ],
        "errors": [{"status": str(k), "count": n} for k, n in error_kinds.most_common()],
    }
