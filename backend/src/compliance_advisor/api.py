"""The HTTP API: ask a question, check health, list the Corpus."""

import json
import logging
from functools import lru_cache
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from .answer import AnswerService, DatabaseError, UpstreamError, get_answer_model
from .embeddings import get_embeddings
from .prompt import DISCLAIMER
from .registry import load_sources
from .retriever import Retriever
from .schemas import AskRequest, AskResponse, SourceOut, SourcesResponse
from .settings import get_settings
from .store import get_store

app = FastAPI(title="Compliance Advisor", description=DISCLAIMER)


@lru_cache
def _engine():
    return create_engine(get_settings().database_url, pool_pre_ping=True)


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
        get_answer_model(settings),
        settings.answer_model,
        settings.top_k,
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


@app.exception_handler(UpstreamError)
async def upstream_failed(request: Request, exc: UpstreamError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc).capitalize()})


@app.exception_handler(DatabaseError)
async def database_down(request: Request, exc: DatabaseError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc).capitalize()})


@app.post("/api/ask", response_model=AskResponse)
def ask(
    request: AskRequest, service: Annotated[AnswerService, Depends(get_service)]
) -> AskResponse:
    return service.ask(request.question, request.top_k)


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
