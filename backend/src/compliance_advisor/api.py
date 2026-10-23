"""The HTTP API: ask a question, history and export, models, presets, health, the Corpus."""

import json
import logging
import queue
import threading
from datetime import date, timedelta
from functools import lru_cache
from typing import Annotated

import openai
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from .accounts import COOKIE, SESSION_DAYS, AccountError, AccountStore, public
from .answer import AnswerService, DatabaseError, UpstreamError
from .audit import AuditStore, to_markdown
from .embeddings import get_embeddings
from .models import chat_model, chat_models, list_price, load_models
from .obligations import extract_obligations
from .profile import PRESETS, FirmProfile
from .prompt import DISCLAIMER
from .registry import load_sources
from .retriever import Retriever
from .schemas import (
    AskRequest,
    AskResponse,
    LoginRequest,
    ProfileUpdate,
    RegisterRequest,
    SourceOut,
    SourcesResponse,
    TimelineRequest,
)
from .settings import get_settings
from .store import get_store
from .tools import ProvisionLinks, check_applicability, compliance_timeline, make_tools

app = FastAPI(title="Compliance Advisor", description=DISCLAIMER)


@lru_cache
def _engine():
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache(maxsize=512)
def provision_link(label: str) -> str | None:
    """The indexed link of a Provision label, such as "AT 2.1 MaRisk" -> its PDF page."""
    query = text(
        "select e.cmetadata->>'link' from langchain_pg_embedding e "
        "join langchain_pg_collection c on c.uuid = e.collection_id "
        "where c.name = :collection and e.cmetadata->>'provision' = :label limit 1"
    )
    try:
        with _engine().connect() as connection:
            row = connection.execute(
                query, {"collection": get_settings().collection, "label": label}
            ).first()
            return row[0] if row else None
    except SQLAlchemyError:
        return None


def tool_factory(profile: FirmProfile | None, today):
    sources = load_sources(get_settings().sources_file)
    return make_tools(profile, sources, ProvisionLinks(sources, provision_link), today)


@lru_cache
def _service() -> AnswerService:
    settings = get_settings()
    store = get_store(settings, get_embeddings(settings))
    return AnswerService(
        Retriever(
            store,
            settings.max_per_source,
            settings.candidates,
            [s.short_title for s in load_sources(settings.sources_file)],
        ),
        chat_models(settings),
        load_models(settings.models_file)[0].id,
        settings.top_k,
        tool_factory,
        list_price,
    )


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


def current_user(request: Request) -> dict | None:
    """The logged-in account, from the session cookie; None for guests."""
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    try:
        return get_accounts().user_for(token)
    except (DatabaseError, SQLAlchemyError):
        return None


User = Annotated[dict | None, Depends(current_user)]


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
    return JSONResponse(status_code=502, content={"detail": str(exc).capitalize()})


@app.exception_handler(DatabaseError)
async def database_down(request: Request, exc: DatabaseError) -> JSONResponse:
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
) -> AskResponse:
    response = service.ask(request.question, request.top_k, request.profile, request.model)
    return _store(audit, response, request, user)


def _event(data: dict) -> str:
    return f"data: {json.dumps(data, default=str)}\n\n"


@app.post("/api/ask/stream")
def ask_stream(
    request: AskRequest,
    service: Annotated[AnswerService, Depends(get_service)],
    audit: Annotated[AuditStore | None, Depends(get_audit)],
    user: User,
) -> StreamingResponse:
    """Server-sent events: one per step (search, model, tools, writing), then the result."""
    events: queue.Queue = queue.Queue()

    def work() -> None:
        try:
            response = service.ask(
                request.question,
                request.top_k,
                request.profile,
                request.model,
                on_stage=lambda stage, data: events.put({"stage": stage, **data}),
            )
            response = _store(audit, response, request, user)
            events.put({"stage": "done", "result": json.loads(response.model_dump_json())})
        except UpstreamError as e:
            events.put({"stage": "error", "status": 502, "detail": str(e).capitalize()})
        except DatabaseError as e:
            events.put({"stage": "error", "status": 503, "detail": str(e).capitalize()})
        except ValueError as e:
            events.put({"stage": "error", "status": 422, "detail": str(e)})
        except Exception as e:
            log.exception("ask failed")
            events.put({"stage": "error", "status": 500, "detail": f"Unexpected error: {e}"})
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
    answer_id: str, audit: Annotated[AuditStore | None, Depends(get_audit)], user: User
) -> dict:
    """Extracts the Obligations behind a stored answer and stores them with it."""
    record = history_item(answer_id, audit, user)
    settings = get_settings()
    try:
        model = chat_model(load_models(settings.models_file)[0], settings)
        response = record["response"]
        rows, raw = extract_obligations(
            model, response["question"], response["passages"], response["cited"]
        )
    except SystemExit as e:
        raise UpstreamError(str(e)) from None
    except openai.APIError as e:
        raise UpstreamError(f"the answer model did not respond: {e}") from e
    data = [r.model_dump() for r in rows]
    audit.save_obligations(answer_id, data)
    cost = float(
        ((getattr(raw, "response_metadata", None) or {}).get("token_usage") or {}).get("cost") or 0
    )
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
    """The Answer Models the interface offers; the first is the default."""
    return {
        "models": [
            m.model_dump(exclude={"provider_only"}) for m in load_models(get_settings().models_file)
        ]
    }


@app.get("/api/history")
def history(
    audit: Annotated[AuditStore | None, Depends(get_audit)],
    user: User,
    q: str = "",
    limit: int = 50,
) -> dict:
    """Your own answers when logged in, the shared guest answers otherwise; `q` searches questions."""
    if audit is None:
        raise DatabaseError("the database is not reachable")
    return {"items": audit.recent(user["id"] if user else None, q[:200], min(max(limit, 1), 200))}


@app.get("/api/history/{answer_id}")
def history_item(
    answer_id: str, audit: Annotated[AuditStore | None, Depends(get_audit)], user: User
) -> dict:
    if audit is None:
        raise DatabaseError("the database is not reachable")
    record = audit.get(answer_id)
    owner = user["id"] if user else None
    if record is None or record.get("user_id") != owner:  # other people's answers stay invisible
        raise HTTPException(status_code=404, detail="No stored answer with this id")
    return record


@app.get("/api/history/{answer_id}/export")
def export(
    answer_id: str,
    audit: Annotated[AuditStore | None, Depends(get_audit)],
    user: User,
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
    return {"user": public(user)}


@app.post("/api/auth/register")
def register(body: RegisterRequest, response: Response) -> dict:
    accounts = get_accounts()
    user = accounts.register(body.email, body.password, body.name)
    return _login(response, accounts, user)


@app.post("/api/auth/login")
def login(body: LoginRequest, response: Response) -> dict:
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
def me(user: User) -> dict:
    return {"user": public(user) if user else None}


def _require(user: dict | None) -> dict:
    if user is None:
        raise HTTPException(status_code=401, detail="Please log in first")
    return user


@app.put("/api/me/profile")
def save_profile(body: ProfileUpdate, user: User) -> dict:
    user = _require(user)
    profile = body.profile.model_dump() if body.profile else None
    get_accounts().save_profile(user["id"], profile)
    return {"user": public({**user, "profile": profile})}


@app.get("/api/me/dashboard")
def dashboard(user: User, audit: Annotated[AuditStore | None, Depends(get_audit)]) -> dict:
    """Overview: key figures, questions per day (30 days), Regimes asked about, latest questions,
    and the upcoming Milestones for the saved Firm Profile."""
    user = _require(user)
    if audit is None:
        raise DatabaseError("the database is not reachable")
    records = audit.records(user["id"])
    today = date.today()
    days = [today - timedelta(days=i) for i in range(29, -1, -1)]
    per_day = {d: 0 for d in days}
    for r in records:
        day = r["created_at"].date()
        if day in per_day:
            per_day[day] += 1
    regimes: dict[str, int] = {}
    for r in records:
        for regime in r["regimes"]:
            regimes[regime] = regimes.get(regime, 0) + 1
    profile = FirmProfile(**user["profile"]) if user["profile"] else None
    upcoming = timeline(TimelineRequest(profile=profile, upcoming_only=True))["entries"]
    return {
        "user": public(user),
        "stats": {
            "questions": len(records),
            "questions_7d": sum(per_day[d] for d in days[-7:]),
            "obligations": sum(len(r["obligations"]) for r in records),
        },
        "activity": [{"date": d.isoformat(), "count": per_day[d]} for d in days],
        "regimes": sorted(
            ({"regime": k, "count": v} for k, v in regimes.items()), key=lambda x: -x["count"]
        ),
        "recent": [
            {k: v for k, v in r.items() if k != "obligations"}
            | {"obligation_count": len(r["obligations"])}
            for r in records[:5]
        ],
        "upcoming": upcoming[:8],
    }


@app.get("/api/me/questions")
def my_questions(
    user: User, audit: Annotated[AuditStore | None, Depends(get_audit)], q: str = ""
) -> dict:
    """All questions of the account, newest first, with Regimes, Rule Checks and obligation count."""
    user = _require(user)
    if audit is None:
        raise DatabaseError("the database is not reachable")
    return {
        "items": [
            {k: v for k, v in r.items() if k != "obligations"}
            | {"obligation_count": len(r["obligations"])}
            for r in audit.records(user["id"], q[:200])
        ]
    }


@app.get("/api/me/obligations")
def my_obligations(user: User, audit: Annotated[AuditStore | None, Depends(get_audit)]) -> dict:
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
def delete_account(request: Request, response: Response, user: User) -> dict:
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
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
