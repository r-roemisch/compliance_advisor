"""How each kind of error is answered, and the count of failed requests the Operator sees."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from ..answer import DatabaseError, UpstreamError
from ..logs import request_id
from ..monitoring import memory_errors
from . import deps

log = logging.getLogger("compliance_advisor.api")


def record_error(status: int, where: str) -> None:
    """Keeps a count of failed requests for the Operator, with the request id that finds their
    log lines; never the question. A 503 means the database is down, so it is counted in memory
    instead of being written to the database."""
    if status == 503:
        memory_errors[status] += 1
        return
    try:
        store = deps.get_events()
        if store is not None:
            store.record("error", status=status, where=where, request_id=request_id.get())
    except SQLAlchemyError:
        memory_errors[status] += 1


async def invalid_input(request: Request, exc: RequestValidationError) -> JSONResponse:
    messages = [
        f"{'.'.join(str(x) for x in err['loc'] if x != 'body')}: {err['msg']}"
        for err in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": "; ".join(messages)})


async def bad_value(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


async def upstream_failed(request: Request, exc: UpstreamError) -> JSONResponse:
    await run_in_threadpool(record_error, 502, request.url.path)  # a database write: off the loop
    return JSONResponse(status_code=502, content={"detail": str(exc).capitalize()})


async def unexpected(request: Request, exc: Exception) -> JSONResponse:
    """Anything unforeseen: counted for the Operator, logged with its trace, and answered without
    the exception's text, which may hold more than the person should see. This handler runs
    outside the middleware, so it adds the request id header itself."""
    log.exception("unexpected error on %s", request.url.path)
    await run_in_threadpool(record_error, 500, request.url.path)
    current = request_id.get()
    return JSONResponse(
        status_code=500,
        content={"detail": "Unexpected error"},
        headers={"X-Request-ID": current} if current else None,
    )


async def database_down(request: Request, exc: DatabaseError) -> JSONResponse:
    record_error(503, request.url.path)
    return JSONResponse(status_code=503, content={"detail": str(exc).capitalize()})


def add_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, invalid_input)
    app.add_exception_handler(ValueError, bad_value)
    app.add_exception_handler(UpstreamError, upstream_failed)
    app.add_exception_handler(Exception, unexpected)
    app.add_exception_handler(DatabaseError, database_down)
