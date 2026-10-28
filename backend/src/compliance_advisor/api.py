"""The HTTP API: ask a question, history and export, models, presets, health, the Corpus."""

import json
import logging
import queue
import threading
import time
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from typing import Annotated

import openai
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from . import analytics
from .accounts import COOKIE, SESSION_DAYS, AccountError, AccountStore, public
from .answer import AnswerService, DatabaseError, UpstreamError
from .apikeys import ApiKeyStore
from .audit import AuditStore, to_markdown
from .db import engine
from .embeddings import get_embeddings
from .limits import GuestCookie, RateLimiter, client_address, load_limits, subject_of
from .mcp_server import build_mcp_app
from .models import ModelOption, chat_model, chat_models, list_price, load_models
from .monitoring import EventStore, configure_logging, memory_errors
from .monitoring import overview as operator_overview
from .obligations import extract_obligations
from .profile import PRESETS, FirmProfile
from .prompt import DISCLAIMER
from .registry import load_sources
from .retriever import SEARCH_STRATEGIES, Retriever
from .rulechecks import clear_link_cache, tool_factory
from .schemas import (
    AskRequest,
    AskResponse,
    KeyRequest,
    LoginRequest,
    ProfileUpdate,
    RegisterRequest,
    SourceOut,
    SourcesResponse,
    TimelineRequest,
)
from .settings import Settings, get_settings
from .store import get_store
from .tools import ProvisionLinks, check_applicability, compliance_timeline
from .update import (
    UpdateStore,
    changed_since,
    current_version,
    is_running,
    run_update,
    same_text,
    start_scheduler,
    try_start,
)

app = FastAPI(title="Compliance Advisor", description=DISCLAIMER)


_engine = engine  # the process's one engine (db.py)


@lru_cache
def _service() -> AnswerService:
    settings = get_settings()
    store = get_store(settings, get_embeddings(settings))
    models = chat_models(settings)
    return AnswerService(
        Retriever(
            store,
            settings.max_per_source,
            settings.candidates,
            [s.short_title for s in load_sources(settings.sources_file)],
            keyword_weight=settings.keyword_weight,
        ),
        models,
        load_models(settings.models_file)[0].id,
        settings.top_k,
        tool_factory,
        list_price,
        settings.search_strategy,
        screeners(settings, models) if settings.screening else None,
    )


def screeners(settings: Settings, models: dict) -> dict:
    """Which model screens for which Answer Model (ADR 0007): an EU-hosted Answer Model screens
    its own questions, so they never go to another provider; the rest use the cheap default."""
    default = models.get(settings.screening_model) or chat_model(
        ModelOption(id=settings.screening_model, label=settings.screening_model), settings
    )
    return {
        m.id: models[m.id] if m.eu_hosted else default for m in load_models(settings.models_file)
    }


# The MCP server (mcp_server.py) shares the app's Rule Checks, Retriever, API keys and limits.
mcp_app = build_mcp_app(
    tool_factory,
    lambda: get_service().retriever,
    lambda key: get_api_keys().user_for(key),
    lambda subject, guest: _limiter().allow(subject, guest),
)
app.mount("/mcp", mcp_app)
# Guests get a cookie on their first response, so the rate limit counts per browser (limits.py).
app.add_middleware(GuestCookie, session_cookie=COOKIE, secure=get_settings().cookie_secure)


@asynccontextmanager
async def _lifespan(_app):
    """The mounted MCP app's session manager must run for the app's lifetime."""
    async with mcp_app.router.lifespan_context(mcp_app):
        yield


app.router.lifespan_context = _lifespan


@lru_cache
def _audit() -> AuditStore:
    return AuditStore(_engine(), get_settings().raw_dir)


def get_audit() -> AuditStore | None:
    try:
        return _audit()
    except SQLAlchemyError:
        return None  # answers still work; they are just not stored


@lru_cache
def _accounts() -> AccountStore:
    return AccountStore(_engine())


def get_accounts() -> AccountStore:
    try:
        return _accounts()
    except SQLAlchemyError as e:
        raise DatabaseError("the database is not reachable") from e


@lru_cache
def _api_keys() -> ApiKeyStore:
    return ApiKeyStore(_engine())


def get_api_keys() -> ApiKeyStore:
    try:
        return _api_keys()
    except SQLAlchemyError as e:
        raise DatabaseError("the database is not reachable") from e


def _public(user: dict) -> dict:
    """What the interface may know about an Account, plus whether it is an Operator."""
    return public(user) | {"operator": bool(user.get("operator"))}


@lru_cache
def _events() -> EventStore:
    return EventStore(_engine())


def get_events() -> EventStore | None:
    try:
        return _events()
    except SQLAlchemyError:
        return None


def _record_error(status: int, where: str) -> None:
    """Keeps a count of failed requests for the Operator; never the question. A 503 means the
    database is down, so it is counted in memory instead of being written to the database."""
    if status == 503:
        memory_errors[status] += 1
        return
    try:
        store = get_events()
        if store is not None:
            store.record("error", status=status, where=where)
    except SQLAlchemyError:
        memory_errors[status] += 1


def current_user(request: Request) -> dict | None:
    """The logged-in account, from the session cookie or an API key in the Authorization header
    ("Bearer ca_..."); None for guests. With a key, the dict carries the key's name as "api_key"."""
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        try:
            user = get_api_keys().user_for(header[7:].strip())
        except (DatabaseError, SQLAlchemyError):
            user = None
        if user is None:
            raise HTTPException(status_code=401, detail="Unknown or revoked API key")
        return user
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    try:
        return get_accounts().user_for(token)
    except (DatabaseError, SQLAlchemyError):
        return None


def session_user(user: Annotated[dict | None, Depends(current_user)]) -> dict | None:
    """Everything except asking questions needs a session: an API key is refused here."""
    if user and user.get("api_key"):
        raise HTTPException(
            status_code=403, detail="API keys may only ask questions and run rule checks"
        )
    return user


User = Annotated[dict | None, Depends(current_user)]
SessionUser = Annotated[dict | None, Depends(session_user)]


@lru_cache
def _limiter() -> RateLimiter:
    return RateLimiter(load_limits(get_settings().limits_file))


def _throttle(request: Request, user: dict | None, audit: AuditStore | None) -> None:
    """Refuses with 429 when the subject's limit or the app's daily cost ceiling is reached."""
    subject, guest = subject_of(request, user, get_settings().trust_x_forwarded_for)
    retry_at = _limiter().allow(subject, guest)
    if retry_at is not None:
        when = datetime.fromtimestamp(retry_at, UTC)
        raise HTTPException(
            status_code=429,
            detail=f"Too many questions; please try again at {when:%H:%M} UTC",
            headers={
                "Retry-After": str(max(1, int(retry_at - time.time()))),
                "X-Limit": "questions",
            },
        )
    if audit is not None:
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            spent = audit.cost_since(today)
        except SQLAlchemyError:
            return
        if spent >= _limiter().limits.daily_cost_usd:
            raise HTTPException(
                status_code=429,
                detail="The app's daily cost limit is reached; please try again tomorrow",
                headers={
                    "Retry-After": str(int((today.timestamp() + 86400) - time.time())),
                    "X-Limit": "daily-cost",
                },
            )


def get_service() -> AnswerService:
    try:
        return _service()  # built on first use; not cached while the database is down
    except SQLAlchemyError as e:
        raise DatabaseError("the database is not reachable") from e
    except SystemExit as e:  # missing API key: report it instead of stopping the server
        raise UpstreamError(str(e)) from None


def passage_counts() -> dict[str, int]:
    query = text(
        "select e.cmetadata->>'source_id', count(*) from langchain_pg_embedding e "
        "join langchain_pg_collection c on c.uuid = e.collection_id "
        "where c.name = :collection group by 1"
    )
    try:
        with _engine().connect() as connection:
            rows = connection.execute(query, {"collection": get_settings().collection})
            return {source_id: count for source_id, count in rows}
    except SQLAlchemyError as e:
        if "does not exist" in str(e):  # nothing ingested yet
            return {}
        raise DatabaseError("the database is not reachable") from e


def fetched_on(raw_dir, source_id: str) -> str:
    """The date the app's copy of a Source was downloaded, from data/raw/<id>/meta.json."""
    meta = raw_dir / source_id / "meta.json"
    try:
        return json.loads(meta.read_text())["fetched_at"][:10]
    except (OSError, ValueError, KeyError):
        return ""


@app.exception_handler(RequestValidationError)
async def invalid_input(request: Request, exc: RequestValidationError) -> JSONResponse:
    messages = [
        f"{'.'.join(str(x) for x in err['loc'] if x != 'body')}: {err['msg']}"
        for err in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": "; ".join(messages)})


@app.exception_handler(ValueError)
async def bad_value(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(UpstreamError)
async def upstream_failed(request: Request, exc: UpstreamError) -> JSONResponse:
    await run_in_threadpool(_record_error, 502, request.url.path)  # a database write: off the loop
    return JSONResponse(status_code=502, content={"detail": str(exc).capitalize()})


@app.exception_handler(Exception)
async def unexpected(request: Request, exc: Exception) -> JSONResponse:
    """Anything unforeseen: counted for the Operator, logged with its trace, and answered without
    the exception's text, which may hold more than the person should see."""
    log.exception("unexpected error on %s", request.url.path)
    await run_in_threadpool(_record_error, 500, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Unexpected error"})


@app.exception_handler(DatabaseError)
async def database_down(request: Request, exc: DatabaseError) -> JSONResponse:
    _record_error(503, request.url.path)
    return JSONResponse(status_code=503, content={"detail": str(exc).capitalize()})


log = logging.getLogger("compliance_advisor.api")


def _store(
    audit: AuditStore | None, response: AskResponse, request: AskRequest, user: dict | None
) -> AskResponse:
    if audit is None:
        return response
    try:
        return audit.save(
            response,
            request.profile.model_dump() if request.profile else None,
            user["id"] if user else None,
            user.get("api_key") if user else None,
        )
    except SQLAlchemyError as e:
        log.warning("answer not stored in the audit trail: %s", e)
        return response


@app.post("/api/ask", response_model=AskResponse)
def ask(
    request: AskRequest,
    service: Annotated[AnswerService, Depends(get_service)],
    audit: Annotated[AuditStore | None, Depends(get_audit)],
    user: User,
    http: Request,
) -> AskResponse:
    _throttle(http, user, audit)
    response = service.ask(
        request.question, request.top_k, request.profile, request.model, strategy=request.strategy
    )
    return _store(audit, response, request, user)


def _event(data: dict) -> str:
    return f"data: {json.dumps(data, default=str)}\n\n"


@app.post("/api/ask/stream")
def ask_stream(
    request: AskRequest,
    service: Annotated[AnswerService, Depends(get_service)],
    audit: Annotated[AuditStore | None, Depends(get_audit)],
    user: User,
    http: Request,
) -> StreamingResponse:
    """Server-sent events: one per step (search, model, tools, writing), then the result."""
    _throttle(http, user, audit)
    events: queue.Queue = queue.Queue()

    def work() -> None:
        try:
            response = service.ask(
                request.question,
                request.top_k,
                request.profile,
                request.model,
                on_stage=lambda stage, data: events.put({"stage": stage, **data}),
                strategy=request.strategy,
            )
            response = _store(audit, response, request, user)
            events.put({"stage": "done", "result": json.loads(response.model_dump_json())})
        except UpstreamError as e:
            _record_error(502, "/api/ask/stream")
            events.put({"stage": "error", "status": 502, "detail": str(e).capitalize()})
        except DatabaseError as e:
            _record_error(503, "/api/ask/stream")
            events.put({"stage": "error", "status": 503, "detail": str(e).capitalize()})
        except ValueError as e:
            events.put({"stage": "error", "status": 422, "detail": str(e)})
        except Exception:
            log.exception("ask failed")
            _record_error(500, "/api/ask/stream")
            events.put({"stage": "error", "status": 500, "detail": "Unexpected error"})
        finally:
            events.put(None)

    threading.Thread(target=work, daemon=True).start()

    def stream():
        while (item := events.get()) is not None:
            yield _event(item)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        # no-transform: proxies (the Next.js server compresses responses) must not buffer the steps
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@app.post("/api/history/{answer_id}/obligations")
def obligations(
    answer_id: str,
    audit: Annotated[AuditStore | None, Depends(get_audit)],
    user: SessionUser,
    http: Request,
) -> dict:
    """Extracts the Obligations behind a stored answer and stores them with it. Counts against
    the same rate limit as a question, runs on the Answer Model the answer used (an EU-hosted
    answer stays in the EU, ADR 0007), and its cost is kept with the answer."""
    record = history_item(answer_id, audit, user)
    response = record["response"]
    if response.get("refusal") or not response["passages"]:
        return {"rows": [], "cost_usd": 0.0}  # nothing to extract from, no model call
    _throttle(http, user, audit)
    settings = get_settings()
    options = {m.id: m for m in load_models(settings.models_file)}
    option = options.get(response.get("model")) or next(iter(options.values()))
    try:
        model = chat_model(option, settings)
        rows, raw = extract_obligations(
            model, response["question"], response["passages"], response["cited"]
        )
    except SystemExit as e:
        raise UpstreamError(str(e)) from None
    except openai.APIError as e:
        raise UpstreamError(f"the answer model did not respond: {e}") from e
    data = [r.model_dump() for r in rows]
    cost = float(
        ((getattr(raw, "response_metadata", None) or {}).get("token_usage") or {}).get("cost") or 0
    )
    if not cost and (prices := list_price(option.id)):
        meta = getattr(raw, "usage_metadata", None) or {}
        cost = meta.get("input_tokens", 0) * prices[0] + meta.get("output_tokens", 0) * prices[1]
    audit.save_obligations(answer_id, data, round(cost, 6))
    return {"rows": data, "cost_usd": round(cost, 6)}


@app.post("/api/timeline")
def timeline(request: TimelineRequest) -> dict:
    """Milestones of all Sources, or of those the Firm Profile makes applicable."""
    settings = get_settings()
    sources = load_sources(settings.sources_file)
    applicable_titles: set[str] | None = None
    if request.profile:
        result = check_applicability(request.profile, ProvisionLinks(sources))
        applicable_titles = {
            title
            for f in result.findings
            if f.applies in ("yes", "later", "check")
            for title in f.sources
        }
        sources = [s for s in sources if s.short_title in applicable_titles]
    result = compliance_timeline(sources, date.today(), None, request.upcoming_only)
    return {
        "today": result.today,
        "entries": [e.model_dump() for e in result.entries],
        "filtered": request.profile is not None,
    }


@app.get("/api/models")
def models() -> dict:
    """The Answer Models the interface offers (the first is the default), and the Search
    Strategies with the default one."""
    settings = get_settings()
    return {
        "models": [
            m.model_dump(exclude={"provider_only"}) for m in load_models(settings.models_file)
        ],
        "strategies": list(SEARCH_STRATEGIES),
        "default_strategy": settings.search_strategy,
    }


@app.get("/api/history")
def history(
    audit: Annotated[AuditStore | None, Depends(get_audit)],
    user: SessionUser,
    q: str = "",
    limit: int = 50,
) -> dict:
    """Your own answers when logged in, the shared guest answers otherwise; `q` searches questions."""
    if audit is None:
        raise DatabaseError("the database is not reachable")
    return {"items": audit.recent(user["id"] if user else None, q[:200], min(max(limit, 1), 200))}


@app.get("/api/history/{answer_id}")
def history_item(
    answer_id: str, audit: Annotated[AuditStore | None, Depends(get_audit)], user: SessionUser
) -> dict:
    if audit is None:
        raise DatabaseError("the database is not reachable")
    record = audit.get(answer_id)
    owner = user["id"] if user else None
    if record is None or record.get("user_id") != owner:  # other people's answers stay invisible
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
        for record in get_updates().changes(set(changed)):
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


@lru_cache
def _updates() -> UpdateStore:
    return UpdateStore(_engine())


def get_updates() -> UpdateStore:
    try:
        return _updates()
    except SQLAlchemyError as e:
        raise DatabaseError("the database is not reachable") from e


@lru_cache
def _baseline_store():
    """The naive fixed-size collection (the evaluation's step 1 baseline), kept in step with
    the Corpus by Update Runs so the comparison stays fair."""
    settings = get_settings()
    return get_store(settings.model_copy(update={"chunker": "fixed"}), get_embeddings(settings))


def _run_update(trigger: str) -> dict:
    settings = get_settings()
    store = get_service().retriever.store  # the app's own store, not a second engine
    try:
        return run_update(settings, get_updates(), store, trigger, baseline_store=_baseline_store())
    finally:
        clear_link_cache()  # Rule Check links may point at new pages


@app.get("/api/operator/update-runs")
def update_runs_list(user: SessionUser) -> dict:
    """The latest Update Runs and Change Records, for the Operator."""
    _operator(user)
    settings = get_settings()
    updates = get_updates()
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


@app.post("/api/operator/update-runs", status_code=202)
def update_run_start(user: SessionUser) -> dict:
    """ "Check now": starts an Update Run in the background; one at a time."""
    _operator(user)
    if not try_start(lambda: _run_update("manual")):
        raise HTTPException(status_code=409, detail="An update run is already in progress")
    return {"started": True}


@app.get("/api/me/changes")
def my_changes(user: SessionUser, audit: Annotated[AuditStore | None, Depends(get_audit)]) -> dict:
    """ "Your Sources have changed": Sources the account's answers relied on whose text changed
    since, with the Change Record and how many answers used an older version."""
    user = _require(user)
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
    for record in get_updates().changes(set(stale)):
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


@app.get("/api/history/{answer_id}/export")
def export(
    answer_id: str,
    audit: Annotated[AuditStore | None, Depends(get_audit)],
    user: SessionUser,
    format: str = "md",
) -> Response:
    """The stored answer as Markdown or JSON, with Passages and Source versions."""
    record = history_item(answer_id, audit, user)
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


# --- Accounts -------------------------------------------------------------------------------


def _login(response: Response, accounts: AccountStore, user: dict) -> dict:
    token = accounts.start_session(user["id"])
    response.set_cookie(
        COOKIE,
        token,
        max_age=SESSION_DAYS * 24 * 3600,
        httponly=True,  # not readable by page scripts
        samesite="lax",
        secure=get_settings().cookie_secure,
        path="/",
    )
    return {"user": _public(user)}


@app.post("/api/auth/register")
def register(body: RegisterRequest, response: Response, http: Request) -> dict:
    limits = _limiter().limits
    address = client_address(http, get_settings().trust_x_forwarded_for)
    _limit_attempts(f"register:{address}", limits.registrations_per_hour, "registrations")
    accounts = get_accounts()
    user = accounts.register(body.email, body.password, body.name)
    return _login(response, accounts, user)


@app.post("/api/auth/login")
def login(body: LoginRequest, response: Response) -> dict:
    limits = _limiter().limits
    email = body.email.strip().lower()
    _limit_attempts(f"login:{email}", limits.login_attempts_per_hour, "login attempts")
    accounts = get_accounts()
    try:
        user = accounts.authenticate(body.email, body.password)
    except AccountError as e:
        raise HTTPException(status_code=401, detail=str(e)) from None
    return _login(response, accounts, user)


@app.post("/api/auth/logout")
def logout(request: Request, response: Response) -> dict:
    get_accounts().end_session(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/")
    return {"user": None}


@app.get("/api/auth/me")
def me(user: SessionUser) -> dict:
    return {"user": _public(user) if user else None}


def _require(user: dict | None) -> dict:
    if user is None:
        raise HTTPException(status_code=401, detail="Please log in first")
    return user


def _operator(user: dict | None) -> dict:
    """The Operator role is a flag on the account, granted with `compliance-advisor-accounts
    operator grant <email>` by whoever runs the backend (ADR 0006)."""
    user = _require(user)
    if not user.get("operator"):
        raise HTTPException(status_code=403, detail="Operators only")
    return user


def _limit_attempts(subject: str, per_hour: int, what: str) -> None:
    retry_at = _limiter().attempt(subject, per_hour)
    if retry_at is not None:
        when = datetime.fromtimestamp(retry_at, UTC)
        raise HTTPException(
            status_code=429,
            detail=f"Too many {what}; please try again at {when:%H:%M} UTC",
            headers={"Retry-After": str(max(1, int(retry_at - time.time())))},
        )


@app.get("/api/operator/overview")
def operator_figures(user: SessionUser, days: int = 30) -> dict:
    """Figures across all Accounts for the Operator (ADR 0006): volume, cost per Answer Model
    and Search Strategy, answer time, retrieval and citation signals, Refusals, failed requests."""
    _operator(user)
    days = _period(days)
    store = get_events()
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


@app.get("/api/me/keys")
def list_keys(user: SessionUser) -> dict:
    return {"keys": get_api_keys().list(_require(user)["id"])}


@app.post("/api/me/keys")
def create_key(body: KeyRequest, user: SessionUser) -> dict:
    """Creates a key and returns its secret once; it is not stored and cannot be shown again."""
    key, secret = get_api_keys().create(_require(user)["id"], body.name)
    return {"key": key, "secret": secret}


@app.delete("/api/me/keys/{key_id}")
def revoke_key(key_id: str, user: SessionUser) -> dict:
    if not get_api_keys().revoke(_require(user)["id"], key_id):
        raise HTTPException(status_code=404, detail="No active key with this id")
    return {"revoked": True}


@app.put("/api/me/profile")
def save_profile(body: ProfileUpdate, user: SessionUser) -> dict:
    user = _require(user)
    profile = body.profile.model_dump() if body.profile else None
    get_accounts().save_profile(user["id"], profile)
    return {"user": _public({**user, "profile": profile})}


def _question_row(record: dict) -> dict:
    """What the question tables show: no Obligation rows, Provisions or Sources."""
    hidden = ("obligations", "provisions", "sources")
    return {k: v for k, v in record.items() if k not in hidden} | {
        "obligation_count": len(record["obligations"])
    }


def _period(days: int) -> int:
    if days not in analytics.PERIODS:
        raise HTTPException(status_code=422, detail="days must be 7, 30, 90 or 0 (every question)")
    return days


@app.get("/api/me/dashboard")
def dashboard(
    user: SessionUser, audit: Annotated[AuditStore | None, Depends(get_audit)], days: int = 30
) -> dict:
    """Overview for the chosen period (7, 30 or 90 days, or 0 for every question): key figures,
    questions per day, Regimes, most-cited Provisions and latest questions. Blind Spots look at
    every question, and the upcoming Milestones follow the saved Firm Profile."""
    user = _require(user)
    if audit is None:
        raise DatabaseError("the database is not reachable")
    days = _period(days)
    today = date.today()
    records = audit.records(user["id"])
    period = analytics.in_period(records, days, today)
    try:
        profile = FirmProfile(**user["profile"]) if user["profile"] else None
    except ValidationError:  # saved with values that no longer exist
        profile = None
    upcoming = timeline(TimelineRequest(profile=profile, upcoming_only=True))["entries"]
    spots = None
    if profile:
        sources = load_sources(get_settings().sources_file)
        findings = check_applicability(profile, ProvisionLinks(sources)).findings
        spots = analytics.blind_spots(records, findings, sources)
    return {
        "user": _public(user),
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


@app.get("/api/me/questions")
def my_questions(
    user: SessionUser,
    audit: Annotated[AuditStore | None, Depends(get_audit)],
    q: str = "",
    regime: str = "",
    provision: str = "",
    day: date | None = None,
    days: int = 0,
) -> dict:
    """The account's questions, newest first, narrowed by a search and by what was clicked on the
    dashboard: a Regime, a Provision, a day or a period."""
    user = _require(user)
    if audit is None:
        raise DatabaseError("the database is not reachable")
    rows = analytics.filter_records(
        audit.records(user["id"], q[:200]),
        regime=regime,
        provision=provision[:200],
        day=day,
        days=_period(days),
        today=date.today(),
    )
    return {"items": [_question_row(r) for r in rows]}


@app.get("/api/me/obligations")
def my_obligations(
    user: SessionUser, audit: Annotated[AuditStore | None, Depends(get_audit)]
) -> dict:
    """Every extracted Obligation of the account, with the question it came from."""
    user = _require(user)
    if audit is None:
        raise DatabaseError("the database is not reachable")
    rows = [
        {**o, "answer_id": r["id"], "question": r["question"], "created_at": r["created_at"]}
        for r in audit.records(user["id"])
        for o in r["obligations"]
    ]
    return {"rows": rows}


@app.delete("/api/me")
def delete_account(request: Request, response: Response, user: SessionUser) -> dict:
    """Deletes the account and every question it asked. This cannot be undone."""
    user = _require(user)
    removed = get_accounts().delete(user["id"])
    response.delete_cookie(COOKIE, path="/")
    return {"deleted": True, "answers_removed": removed}


@app.get("/api/profiles")
def profiles() -> dict:
    """Firm Profile presets, by firm type only."""
    return {"presets": [p.model_dump() for p in PRESETS]}


@app.get("/api/health")
def health() -> JSONResponse:
    try:
        with _engine().connect() as connection:
            connection.execute(text("select 1"))
        return JSONResponse({"status": "ok", "database": "reachable"})
    except SQLAlchemyError:
        return JSONResponse({"status": "degraded", "database": "unreachable"}, status_code=503)


@app.get("/api/sources", response_model=SourcesResponse)
def sources() -> SourcesResponse:
    settings = get_settings()
    counts = passage_counts()
    return SourcesResponse(
        sources=[
            SourceOut(
                **s.model_dump(
                    include={
                        "id",
                        "title",
                        "short_title",
                        "regime",
                        "layer",
                        "issuer",
                        "language",
                        "legal_status",
                        "version",
                    }
                ),
                milestones=[m.model_dump(mode="json") for m in s.milestones],
                as_of=fetched_on(settings.raw_dir, s.id),
                url=s.link,
                passages=counts.get(s.id, 0),
            )
            for s in load_sources(settings.sources_file)
        ],
        disclaimer=DISCLAIMER,
    )


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_format)
    if settings.update_runs:
        start_scheduler(settings.update_hour, lambda: try_start(lambda: _run_update("scheduled")))
        log.info("update runs scheduled daily at %02d:00 UTC", settings.update_hour)
    # log_config=None: uvicorn's own loggers go through the handler above, in the same format
    uvicorn.run(app, host=settings.api_host, port=settings.api_port, log_config=None)
