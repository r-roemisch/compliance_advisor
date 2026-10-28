"""Dashboard analytics over an account's stored answers: the chosen period, questions per day,
Regimes, most-cited Provisions, Blind Spots, and the filters behind each click-through.

Pure functions over the rows AuditStore.records returns, so they are tested without a database.
"""

from collections import Counter
from collections.abc import Iterable
from datetime import date, timedelta

from .registry import Source
from .tools import RegimeFinding

PERIODS = (7, 30, 90, 0)  # days; 0 = every question
LONGEST_CHART = 365  # "every question" draws at most one year of days

# How strongly a Source applies, strongest first; "no" and "not_in_corpus" are not Blind Spots.
_APPLIES_RANK = {"yes": 0, "later": 1, "check": 2}
# A Rule Check stands for its Source as much as a cited Passage does.
_TOOL_SOURCES = {"classify_dora_incident": "DORA", "check_ai_act_use_case": "AI Act"}


def _day(record: dict) -> date:
    return record["created_at"].date()


def period_start(days: int, today: date) -> date | None:
    """First day of the period; None for every question."""
    return today - timedelta(days=days - 1) if days else None


def in_period(records: list[dict], days: int, today: date) -> list[dict]:
    start = period_start(days, today)
    return [r for r in records if start is None or _day(r) >= start]


def activity(records: list[dict], days: int, today: date) -> list[dict]:
    """Questions per day over the period, one entry per day including empty ones."""
    start = period_start(days, today)
    if start is None:
        first = min((_day(r) for r in records), default=today)
        start = max(first, today - timedelta(days=LONGEST_CHART - 1))
    per_day = {start + timedelta(days=i): 0 for i in range((today - start).days + 1)}
    for r in records:
        if _day(r) in per_day:
            per_day[_day(r)] += 1
    return [{"date": d.isoformat(), "count": n} for d, n in per_day.items()]


def regime_counts(records: list[dict]) -> list[dict]:
    counts = Counter(regime for r in records for regime in r["regimes"])
    return [
        {"regime": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    ]


def top_provisions(records: list[dict], limit: int = 8) -> list[dict]:
    """The Provisions cited in the most answers; an answer counts once per Provision."""
    counts: Counter[str] = Counter()
    info: dict[str, dict] = {}
    for r in records:
        for p in {p["provision"]: p for p in r["provisions"]}.values():
            counts[p["provision"]] += 1
            info.setdefault(p["provision"], p)
    ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:limit]
    return [info[label] | {"count": n} for label, n in ranked]


def sources_touched(record: dict) -> set[str]:
    return set(record["sources"]) | {
        _TOOL_SOURCES[t] for t in record["tools"] if t in _TOOL_SOURCES
    }


def blind_spots(
    records: list[dict], findings: Iterable[RegimeFinding], sources: list[Source]
) -> list[dict]:
    """Every indexed Source that applies to the Firm Profile, with how many questions touched it.
    Never asked about comes first, then by how firmly it applies."""
    by_title = {s.short_title: s for s in sources}
    applies: dict[str, str] = {}
    for f in findings:
        if f.applies not in _APPLIES_RANK:
            continue
        for title in f.sources:
            if title in by_title and _APPLIES_RANK[f.applies] < _APPLIES_RANK.get(
                applies.get(title, ""), 99
            ):
                applies[title] = f.applies
    asked = Counter(title for r in records for title in sources_touched(r))
    rows = [
        {
            "short_title": title,
            "regime": by_title[title].regime,
            "layer": by_title[title].layer,
            "url": by_title[title].link,
            "applies": status,
            "questions": asked[title],
        }
        for title, status in applies.items()
    ]
    return sorted(
        rows, key=lambda r: (r["questions"] > 0, _APPLIES_RANK[r["applies"]], r["short_title"])
    )


def filter_records(
    records: list[dict],
    *,
    regime: str = "",
    provision: str = "",
    day: date | None = None,
    days: int = 0,
    today: date,
) -> list[dict]:
    """The questions behind one bar of the dashboard: a Regime, a Provision, a day or a period."""
    rows = in_period(records, days, today)
    if regime:
        rows = [r for r in rows if regime in r["regimes"]]
    if provision:
        rows = [r for r in rows if any(p["provision"] == provision for p in r["provisions"])]
    if day:
        rows = [r for r in rows if _day(r) == day]
    return rows
