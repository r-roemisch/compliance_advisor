"""The HTTP API: ask a question, history and export, models, presets, health, the Corpus."""

import json
import logging
import queue
import threading
from functools import lru_cache
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from .answer import AnswerService, DatabaseError, UpstreamError
from .audit import AuditStore, to_markdown
from .embeddings import get_embeddings
from .models import chat_models, load_models
from .profile import PRESETS, FirmProfile
from .prompt import DISCLAIMER
from .registry import load_sources
from .retriever import Retriever
from .schemas import AskRequest, AskResponse, SourceOut, SourcesResponse
from .settings import get_settings
from .store import get_store
from .tools import ProvisionLinks, make_tools

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
    )


@lru_cache
def _audit() -> AuditStore:
    return AuditStore(_engine(), get_settings().raw_dir)


def get_audit() -> AuditStore | None:
    try:
        return _audit()
    except SQLAlchemyError:
        return None  # answers still work; they are just not stored


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


def _store(audit: AuditStore | None, response: AskResponse, request: AskRequest) -> AskResponse:
    if audit is None:
        return response
    try:
        return audit.save(response, request.profile.model_dump() if request.profile else None)
    except SQLAlchemyError as e:
        log.warning("answer not stored in the audit trail: %s", e)
        return response


@app.post("/api/ask", response_model=AskResponse)
def ask(
    request: AskRequest,
    service: Annotated[AnswerService, Depends(get_service)],
    audit: Annotated[AuditStore | None, Depends(get_audit)],
) -> AskResponse:
    response = service.ask(request.question, request.top_k, request.profile, request.model)
    return _store(audit, response, request)


def _event(data: dict) -> str:
    return f"data: {json.dumps(data, default=str)}\n\n"


@app.post("/api/ask/stream")
def ask_stream(
    request: AskRequest,
    service: Annotated[AnswerService, Depends(get_service)],
    audit: Annotated[AuditStore | None, Depends(get_audit)],
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
            response = _store(audit, response, request)
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
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


@app.get("/api/models")
def models() -> dict:
    """The Answer Models the interface offers; the first is the default."""
    return {
        "models": [
            m.model_dump(exclude={"provider_only"}) for m in load_models(get_settings().models_file)
        ]
    }


@app.get("/api/history")
def history(audit: Annotated[AuditStore | None, Depends(get_audit)], limit: int = 50) -> dict:
    if audit is None:
        raise DatabaseError("the database is not reachable")
    return {"items": audit.recent(min(max(limit, 1), 200))}


@app.get("/api/history/{answer_id}")
def history_item(answer_id: str, audit: Annotated[AuditStore | None, Depends(get_audit)]) -> dict:
    if audit is None:
        raise DatabaseError("the database is not reachable")
    record = audit.get(answer_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No stored answer with this id")
    return record


@app.get("/api/history/{answer_id}/export")
def export(
    answer_id: str, audit: Annotated[AuditStore | None, Depends(get_audit)], format: str = "md"
) -> Response:
    """The stored answer as Markdown or JSON, with Passages and Source versions."""
    record = history_item(answer_id, audit)
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
