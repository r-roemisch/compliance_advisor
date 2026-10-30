"""The FastAPI app: the routers, the MCP server at /mcp, the guest cookie, the request id and the
error handlers. main() serves it and schedules the Update Runs."""

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from ..accounts import COOKIE
from ..limits import GuestCookie
from ..logs import RequestId, configure_logging
from ..mcp_server import build_mcp_app
from ..prompt import DISCLAIMER
from ..rulechecks import tool_factory
from ..settings import get_settings
from ..update import start_scheduler, try_start
from . import deps
from .errors import add_error_handlers
from .routes import account, ask, auth, corpus, history, operator
from .throttling import limiter

log = logging.getLogger("compliance_advisor.api")

# The MCP server (mcp_server.py) shares the app's Rule Checks, Retriever, API keys and limits.
mcp_app = build_mcp_app(
    tool_factory,
    lambda: deps.get_service().retriever,
    lambda key: deps.get_api_keys().user_for(key),
    lambda subject, guest: limiter().allow(subject, guest),
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """The mounted MCP app's session manager must run for the app's lifetime."""
    async with mcp_app.router.lifespan_context(mcp_app):
        yield


app = FastAPI(title="Compliance Advisor", description=DISCLAIMER, lifespan=lifespan)
app.mount("/mcp", mcp_app)
# Guests get a cookie on their first response, so the rate limit counts per browser (limits.py).
app.add_middleware(GuestCookie, session_cookie=COOKIE, secure=get_settings().cookie_secure)
# Added last, so it runs first: every log line of a request carries its id (logs.py).
app.add_middleware(RequestId)
add_error_handlers(app)
for routes in (ask, history, auth, account, operator, corpus):
    app.include_router(routes.router)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_format)
    if settings.update_runs:
        start_scheduler(
            settings.update_hour, lambda: try_start(lambda: operator.update_corpus("scheduled"))
        )
        log.info("update runs scheduled daily at %02d:00 UTC", settings.update_hour)
    # log_config=None: uvicorn's own loggers go through the handler above, in the same format
    uvicorn.run(app, host=settings.api_host, port=settings.api_port, log_config=None)
