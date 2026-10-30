"""Asking a question: the answer at once or step by step, and the options the interface offers
for it (Answer Models, Search Strategies, Firm Profile presets)."""

import contextvars
import json
import logging
import queue
import threading

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError

from ...answer import DatabaseError, UpstreamError
from ...audit import AuditStore
from ...limits import guest_identity
from ...logs import prompt_failed
from ...models import load_models
from ...profile import PRESETS
from ...retriever import SEARCH_STRATEGIES
from ...schemas import AskRequest, AskResponse
from ...settings import get_settings
from .. import deps
from ..errors import record_error
from ..throttling import throttle

router = APIRouter()
log = logging.getLogger("compliance_advisor.api")


def _store(
    audit: AuditStore | None,
    response: AskResponse,
    request: AskRequest,
    user: dict | None,
    http: Request,
) -> AskResponse:
    if audit is None:
        return response
    try:
        return audit.save(
            response,
            request.profile.model_dump() if request.profile else None,
            user["id"] if user else None,
            user.get("api_key") if user else None,
            None if user else guest_identity(http),
        )
    except SQLAlchemyError as e:
        prompt_failed("storage", e, logging.WARNING, model=response.model)
        return response


@router.post("/api/ask", response_model=AskResponse)
def ask(
    request: AskRequest,
    service: deps.Service,
    audit: deps.Audit,
    user: deps.User,
    http: Request,
) -> AskResponse:
    throttle(http, user, audit)
    response = service.ask(
        request.question, request.top_k, request.profile, request.model, strategy=request.strategy
    )
    return _store(audit, response, request, user, http)


def _event(data: dict) -> str:
    return f"data: {json.dumps(data, default=str)}\n\n"


@router.post("/api/ask/stream")
def ask_stream(
    request: AskRequest,
    service: deps.Service,
    audit: deps.Audit,
    user: deps.User,
    http: Request,
) -> StreamingResponse:
    """Server-sent events: one per step (search, model, tools, writing), then the result."""
    throttle(http, user, audit)
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
            response = _store(audit, response, request, user, http)
            events.put({"stage": "done", "result": json.loads(response.model_dump_json())})
        except UpstreamError as e:
            record_error(502, "/api/ask/stream")
            events.put({"stage": "error", "status": 502, "detail": str(e).capitalize()})
        except DatabaseError as e:
            record_error(503, "/api/ask/stream")
            events.put({"stage": "error", "status": 503, "detail": str(e).capitalize()})
        except ValueError as e:
            events.put({"stage": "error", "status": 422, "detail": str(e)})
        except Exception:
            log.exception("unexpected error on /api/ask/stream")
            record_error(500, "/api/ask/stream")
            events.put({"stage": "error", "status": 500, "detail": "Unexpected error"})
        finally:
            events.put(None)

    # in a copy of the request's context, so the log lines of the answer carry its id
    threading.Thread(target=contextvars.copy_context().run, args=(work,), daemon=True).start()

    def stream():
        while (item := events.get()) is not None:
            yield _event(item)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        # no-transform: proxies (the Next.js server compresses responses) must not buffer the steps
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.get("/api/models")
def models() -> dict:
    """The Answer Models the interface offers (the first is the default), and the Search
    Strategies with the default one. Each model's system prompt stays on the server."""
    settings = get_settings()
    return {
        "models": [
            m.model_dump(exclude={"provider_only", "system_prompt"})
            for m in load_models(settings.models_file)
        ],
        "strategies": list(SEARCH_STRATEGIES),
        "default_strategy": settings.search_strategy,
    }


@router.get("/api/profiles")
def profiles() -> dict:
    """Firm Profile presets, by firm type only."""
    return {"presets": [p.model_dump() for p in PRESETS]}
