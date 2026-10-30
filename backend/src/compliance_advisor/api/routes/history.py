"""Stored answers: the history of an Account or of a guest browser, one answer with the Sources
that changed since, its export, and the Obligations extracted from it."""

import json

import openai
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.exc import SQLAlchemyError

from ...answer import DatabaseError, UpstreamError
from ...audit import to_markdown
from ...limits import guest_identity
from ...logs import prompt_failed
from ...models import chat_model, list_price, load_models
from ...obligations import extract_obligations
from ...registry import load_sources
from ...settings import get_settings
from ...update import changed_since
from .. import deps
from ..throttling import throttle

router = APIRouter()


@router.get("/api/history")
def history(
    audit: deps.Audit,
    user: deps.SessionUser,
    http: Request,
    q: str = "",
    limit: int = 50,
) -> dict:
    """Your own answers when logged in, the answers asked from this browser otherwise; `q`
    searches questions."""
    if audit is None:
        raise DatabaseError("the database is not reachable")
    return {
        "items": audit.recent(
            user["id"] if user else None,
            q[:200],
            min(max(limit, 1), 200),
            guest_id=None if user else guest_identity(http),
        )
    }


def _owns(record: dict | None, user: dict | None, http: Request) -> bool:
    """An account owns its answers; a guest browser the ones asked from it. Nobody else: an
    unknown id answers "not found", never "forbidden" (ADR 0005)."""
    if record is None:
        return False
    if user:
        return record.get("user_id") == user["id"]
    guest = guest_identity(http)
    return record.get("user_id") is None and guest is not None and record.get("guest_id") == guest


@router.get("/api/history/{answer_id}")
def history_item(
    answer_id: str,
    audit: deps.Audit,
    user: deps.SessionUser,
    http: Request,
) -> dict:
    if audit is None:
        raise DatabaseError("the database is not reachable")
    record = audit.get(answer_id)
    if not _owns(record, user, http):
        raise HTTPException(status_code=404, detail="No stored answer with this id")
    return record | {"changed_sources": _changed_sources(record.get("source_versions") or {})}


def _changed_sources(versions: dict) -> list[dict]:
    """Sources an answer used whose text has changed since, with the latest Change Record."""
    settings = get_settings()
    changed = changed_since(settings.raw_dir, versions)
    if not changed:
        return []
    titles = {s.id: s.short_title for s in load_sources(settings.sources_file)}
    latest: dict[str, dict] = {}
    try:
        for record in deps.get_updates().changes(set(changed)):
            latest.setdefault(record["source_id"], record)
    except (DatabaseError, SQLAlchemyError):
        pass
    return [
        {
            "source_id": source_id,
            "short_title": titles.get(source_id, source_id),
            "at": latest[source_id]["at"] if source_id in latest else None,
            "added": latest[source_id]["added"] if source_id in latest else None,
            "removed": latest[source_id]["removed"] if source_id in latest else None,
            "changed": latest[source_id]["changed"] if source_id in latest else None,
        }
        for source_id in changed
    ]


@router.get("/api/history/{answer_id}/export")
def export(
    answer_id: str,
    audit: deps.Audit,
    user: deps.SessionUser,
    http: Request,
    format: str = "md",
) -> Response:
    """The stored answer as Markdown or JSON, with Passages and Source versions."""
    record = history_item(answer_id, audit, user, http)
    name = f"compliance-advisor-{record['created_at']:%Y%m%d-%H%M%S}"
    if format == "json":
        body = json.dumps(record, default=str, ensure_ascii=False, indent=2)
        media, ext = "application/json", "json"
    elif format == "md":
        body, media, ext = to_markdown(record), "text/markdown; charset=utf-8", "md"
    else:
        raise HTTPException(status_code=422, detail="format must be md or json")
    return Response(
        body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{name}.{ext}"'},
    )


@router.post("/api/history/{answer_id}/obligations")
def obligations(
    answer_id: str,
    audit: deps.Audit,
    user: deps.SessionUser,
    http: Request,
) -> dict:
    """Extracts the Obligations behind a stored answer and stores them with it. Counts against
    the same rate limit as a question, runs on the Answer Model the answer used (an EU-hosted
    answer stays in the EU, ADR 0007), and its cost is kept with the answer."""
    record = history_item(answer_id, audit, user, http)
    response = record["response"]
    if response.get("refusal") or not response["passages"]:
        return {"rows": [], "cost_usd": 0.0}  # nothing to extract from, no model call
    throttle(http, user, audit)
    settings = get_settings()
    options = {m.id: m for m in load_models(settings.models_file)}
    option = options.get(response.get("model")) or next(iter(options.values()))
    try:
        model = chat_model(option, settings)
        rows, raw = extract_obligations(
            model, response["question"], response["passages"], response["cited"]
        )
    except SystemExit as e:
        prompt_failed("obligations", e, model=option.id)
        raise UpstreamError(str(e)) from None
    except openai.APIError as e:
        prompt_failed("obligations", e, model=option.id)
        raise UpstreamError(f"the answer model did not respond: {e}") from e
    except Exception as e:
        prompt_failed("obligations", e, model=option.id)
        raise
    data = [r.model_dump() for r in rows]
    cost = float(
        ((getattr(raw, "response_metadata", None) or {}).get("token_usage") or {}).get("cost") or 0
    )
    if not cost and (prices := list_price(option.id)):
        meta = getattr(raw, "usage_metadata", None) or {}
        cost = meta.get("input_tokens", 0) * prices[0] + meta.get("output_tokens", 0) * prices[1]
    audit.save_obligations(answer_id, data, round(cost, 6))
    return {"rows": data, "cost_usd": round(cost, 6)}
