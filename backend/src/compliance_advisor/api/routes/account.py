"""The logged-in Account's own pages: dashboard, questions, Obligations, Sources that changed
since its answers, API keys, Firm Profile, and deleting the Account."""

from datetime import date

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import ValidationError

from ... import analytics
from ...accounts import COOKIE
from ...answer import DatabaseError
from ...profile import FirmProfile
from ...registry import load_sources
from ...schemas import KeyRequest, ProfileUpdate
from ...settings import get_settings
from ...tools import ProvisionLinks, check_applicability
from ...update import current_version, same_text
from .. import deps
from .corpus import milestones

router = APIRouter()


def _question_row(record: dict) -> dict:
    """What the question tables show: no Obligation rows, Provisions or Sources."""
    hidden = ("obligations", "provisions", "sources")
    return {k: v for k, v in record.items() if k not in hidden} | {
        "obligation_count": len(record["obligations"])
    }


@router.get("/api/me/dashboard")
def dashboard(user: deps.SessionUser, audit: deps.Audit, days: int = 30) -> dict:
    """Overview for the chosen period (7, 30 or 90 days, or 0 for every question): key figures,
    questions per day, Regimes, most-cited Provisions and latest questions. Blind Spots look at
    every question, and the upcoming Milestones follow the saved Firm Profile."""
    user = deps.require_user(user)
    if audit is None:
        raise DatabaseError("the database is not reachable")
    days = deps.period(days)
    today = date.today()
    records = audit.records(user["id"])
    period = analytics.in_period(records, days, today)
    try:
        profile = FirmProfile(**user["profile"]) if user["profile"] else None
    except ValidationError:  # saved with values that no longer exist
        profile = None
    upcoming = milestones(profile, upcoming_only=True)["entries"]
    spots = None
    if profile:
        sources = load_sources(get_settings().sources_file)
        findings = check_applicability(profile, ProvisionLinks(sources)).findings
        spots = analytics.blind_spots(records, findings, sources)
    return {
        "user": deps.public_user(user),
        "days": days,
        "stats": {
            "questions": len(period),
            "refused": sum(1 for r in period if r.get("refused")),
            "questions_total": len(records),
            "obligations": sum(len(r["obligations"]) for r in period),
        },
        "activity": analytics.activity(records, days, today),
        "regimes": analytics.regime_counts(period),
        "provisions": analytics.top_provisions(period),
        "blind_spots": spots,
        "recent": [_question_row(r) for r in period[:5]],
        "upcoming": upcoming[:8],
    }


@router.get("/api/me/questions")
def my_questions(
    user: deps.SessionUser,
    audit: deps.Audit,
    q: str = "",
    regime: str = "",
    provision: str = "",
    day: date | None = None,
    days: int = 0,
) -> dict:
    """The account's questions, newest first, narrowed by a search and by what was clicked on the
    dashboard: a Regime, a Provision, a day or a period."""
    user = deps.require_user(user)
    if audit is None:
        raise DatabaseError("the database is not reachable")
    rows = analytics.filter_records(
        audit.records(user["id"], q[:200]),
        regime=regime,
        provision=provision[:200],
        day=day,
        days=deps.period(days),
        today=date.today(),
    )
    return {"items": [_question_row(r) for r in rows]}


@router.get("/api/me/obligations")
def my_obligations(user: deps.SessionUser, audit: deps.Audit) -> dict:
    """Every extracted Obligation of the account, with the question it came from."""
    user = deps.require_user(user)
    if audit is None:
        raise DatabaseError("the database is not reachable")
    rows = [
        {**o, "answer_id": r["id"], "question": r["question"], "created_at": r["created_at"]}
        for r in audit.records(user["id"])
        for o in r["obligations"]
    ]
    return {"rows": rows}


@router.get("/api/me/changes")
def my_changes(user: deps.SessionUser, audit: deps.Audit) -> dict:
    """ "Your Sources have changed": Sources the account's answers relied on whose text changed
    since, with the Change Record and how many answers used an older version."""
    user = deps.require_user(user)
    if audit is None:
        raise DatabaseError("the database is not reachable")
    settings = get_settings()
    used = audit.versions_used(user["id"])
    stale = {}
    for source_id, entry in used.items():
        current = current_version(settings.raw_dir, source_id)
        older = [v for v in entry["versions"] if not same_text(v, current)]
        if older:
            stale[source_id] = {"answers": len(older)}
    if not stale:
        return {"changes": []}
    titles = {s.id: s.short_title for s in load_sources(settings.sources_file)}
    latest: dict[str, dict] = {}
    for record in deps.get_updates().changes(set(stale)):
        latest.setdefault(record["source_id"], record)
    return {
        "changes": [
            {
                "source_id": source_id,
                "short_title": titles.get(source_id, source_id),
                "answers": entry["answers"],
                "at": latest[source_id]["at"] if source_id in latest else None,
                "added": latest[source_id]["added"] if source_id in latest else None,
                "removed": latest[source_id]["removed"] if source_id in latest else None,
                "changed": latest[source_id]["changed"] if source_id in latest else None,
            }
            for source_id, entry in sorted(stale.items())
        ]
    }


@router.get("/api/me/keys")
def list_keys(user: deps.SessionUser) -> dict:
    return {"keys": deps.get_api_keys().list(deps.require_user(user)["id"])}


@router.post("/api/me/keys")
def create_key(body: KeyRequest, user: deps.SessionUser) -> dict:
    """Creates a key and returns its secret once; it is not stored and cannot be shown again."""
    key, secret = deps.get_api_keys().create(deps.require_user(user)["id"], body.name)
    return {"key": key, "secret": secret}


@router.delete("/api/me/keys/{key_id}")
def revoke_key(key_id: str, user: deps.SessionUser) -> dict:
    if not deps.get_api_keys().revoke(deps.require_user(user)["id"], key_id):
        raise HTTPException(status_code=404, detail="No active key with this id")
    return {"revoked": True}


@router.put("/api/me/profile")
def save_profile(body: ProfileUpdate, user: deps.SessionUser) -> dict:
    user = deps.require_user(user)
    profile = body.profile.model_dump() if body.profile else None
    deps.get_accounts().save_profile(user["id"], profile)
    return {"user": deps.public_user({**user, "profile": profile})}


@router.delete("/api/me")
def delete_account(request: Request, response: Response, user: deps.SessionUser) -> dict:
    """Deletes the account and every question it asked. This cannot be undone."""
    user = deps.require_user(user)
    removed = deps.get_accounts().delete(user["id"])
    response.delete_cookie(COOKIE, path="/")
    return {"deleted": True, "answers_removed": removed}
