"""The HTTP API: the app (server.py), what its routers share (deps.py, throttling.py, errors.py),
and one router per area (routes/)."""

from .server import app, main

__all__ = ["app", "main"]
