"""The Operator's pages (ADR 0006): figures across all Accounts, never question texts, and the
Update Runs that keep the Corpus current."""

from datetime import UTC, date, datetime, timedelta
from functools import lru_cache

from fastapi import APIRouter, HTTPException

from ...answer import DatabaseError
from ...embeddings import get_embeddings
from ...monitoring import memory_errors
from ...monitoring import overview as operator_overview
from ...registry import load_sources
from ...rulechecks import clear_link_cache
from ...settings import get_settings
from ...store import get_store
from ...update import is_running, run_update, try_start
from .. import deps

router = APIRouter()


@router.get("/api/operator/overview")
def operator_figures(user: deps.SessionUser, days: int = 30) -> dict:
    """Figures across all Accounts for the Operator (ADR 0006): volume, cost per Answer Model
    and Search Strategy, answer time, retrieval and citation signals, Refusals, failed requests."""
    deps.require_operator(user)
    days = deps.period(days)
    store = deps.get_events()
    if store is None:
        raise DatabaseError("the database is not reachable")
    today = date.today()
    start = (
        datetime.combine(today - timedelta(days=days - 1), datetime.min.time(), UTC)
        if days
        else None
    )
    errors = store.since(start, "error") + [
        {"at": None, "kind": "error", "data": {"status": status}}
        for status, n in memory_errors.items()
        for _ in range(n)  # counted since the backend started, not per period
    ]
    return operator_overview(store.answer_rows(start), errors, days, today)


@lru_cache
def _baseline_store():
    """The naive fixed-size collection (the evaluation's step 1 baseline), kept in step with
    the Corpus by Update Runs so the comparison stays fair."""
    settings = get_settings()
    return get_store(settings.model_copy(update={"chunker": "fixed"}), get_embeddings(settings))


def update_corpus(trigger: str) -> dict:
    """One Update Run on the app's own store, by hand ("manual") or on the schedule."""
    settings = get_settings()
    store = deps.get_service().retriever.store  # the app's own store, not a second engine
    try:
        return run_update(
            settings, deps.get_updates(), store, trigger, baseline_store=_baseline_store()
        )
    finally:
        clear_link_cache()  # Rule Check links may point at new pages


@router.get("/api/operator/update-runs")
def update_runs_list(user: deps.SessionUser) -> dict:
    """The latest Update Runs and Change Records, for the Operator."""
    deps.require_operator(user)
    settings = get_settings()
    updates = deps.get_updates()
    titles = {s.id: s.short_title for s in load_sources(settings.sources_file)}
    return {
        "running": is_running() or updates.running(),
        "scheduled": settings.update_runs,
        "hour": settings.update_hour,
        "runs": updates.runs(),
        "changes": [
            c | {"short_title": titles.get(c["source_id"], c["source_id"])}
            for c in updates.changes()
        ],
    }


@router.post("/api/operator/update-runs", status_code=202)
def update_run_start(user: deps.SessionUser) -> dict:
    """ "Check now": starts an Update Run in the background; one at a time."""
    deps.require_operator(user)
    if not try_start(lambda: update_corpus("manual")):
        raise HTTPException(status_code=409, detail="An update run is already in progress")
    return {"started": True}
