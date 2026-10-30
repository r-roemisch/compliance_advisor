"""Log lines: one JSON object per line (or plain text), each with the id of the request that
caused it, and one line for every failed prompt. No log line holds a question text (ADR 0006).

A failed prompt is logged on its own logger, `compliance_advisor.failures`, as
"prompt failed step=<step> ... error=<error>", so a log collector can catch every one. ERROR: the
question got no answer. WARNING: it went on without the step that failed, or its answer breaks
the format the system prompt asks for. The steps:

start        the Answer Service could not be built (no API key, database down)
precheck     the Pre-Check
screening    the Pre-Check's screening call; the question passes unscreened (WARNING)
translation  the Query Translation call; the question is searched alone (WARNING)
search       the search for Passages (embedding service or database)
answer       the Answer Model's round with its Rule Checks; WARNING when the answer arrived but
             is cut off, empty, without the Coverage line or without a citation
storage      writing the answer to the history; the person still gets it (WARNING)
obligations  extracting the Obligations behind a stored answer
"""

import json
import logging
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime

import openai
from starlette.datastructures import MutableHeaders

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
failures = logging.getLogger("compliance_advisor.failures")

# Attributes every log record has; any other came in through `extra` and becomes a JSON field.
# uvicorn adds color_message, its message with terminal colours.
_RECORD = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "color_message"}


class JsonFormatter(logging.Formatter):
    """One JSON object per log line, so a log collector can read fields without parsing."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        entry |= {k: v for k, v in vars(record).items() if k not in _RECORD and k not in entry}
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


class RequestIdFilter(logging.Filter):
    """Adds the id of the request being served, if any, to each log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if (current := request_id.get()) is not None:
            record.request_id = current
        return True


def configure_logging(fmt: str) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s",
                defaults={"request_id": "-"},
            )
        )
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


class RequestId:
    """ASGI middleware: gives every request an id, which its log lines carry and its response
    returns as X-Request-ID, so the lines of one failed prompt can be found together. The id
    stays set after the request: the handler for unexpected errors runs outside this middleware
    and logs it too, and every request runs in a task of its own."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        current = uuid.uuid4().hex[:12]
        request_id.set(current)

        async def send_with_id(message):
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append("x-request-id", current)
            await send(message)

        await self.app(scope, receive, send_with_id)


def describe(error: BaseException) -> str:
    """The class and the first line of the message of what caused the error (an UpstreamError's
    OpenRouter error). OpenRouter's error metadata is left out: a moderation error quotes the
    flagged part of the question."""
    error = error.__cause__ or error
    if isinstance(error, openai.APIStatusError):
        message = error.body.get("message", "") if isinstance(error.body, dict) else ""
        text = f"{error.status_code} {message}"
    else:
        text = str(error)
    first = text.strip().splitlines()[0][:300] if text.strip() else ""
    return f"{type(error).__name__}: {first}" if first else type(error).__name__


def prompt_failed(
    step: str, error: BaseException | str, level: int = logging.ERROR, **context
) -> None:
    """Logs one failed prompt (see above); `context` adds the model and figures, never the
    question. In JSON lines, the step, the error and the context are fields of their own."""
    reason = error if isinstance(error, str) else describe(error)
    fields = {key: value for key, value in context.items() if value is not None}
    failures.log(
        level,
        "prompt failed step=%s%s error=%s",
        step,
        "".join(f" {key}={value}" for key, value in fields.items()),
        reason,
        extra={"step": step, **fields, "error": reason},
    )
