"""Rate limits (config/limits.yaml): questions per hour and per day for an Account or a guest
browser, and a daily cost ceiling for the whole app as a safety net.

A guest is told apart by a signed random id in an httpOnly cookie the backend sets on the first
response, not by address: behind the Next.js proxy every browser arrives from the proxy's address
(the proxy adds no x-forwarded-for of its own). Only tokens this backend signed count; a forged or
missing cookie falls back to one bucket per address, so minting cookies buys nothing. A client can
also send its own x-forwarded-for header, which the proxy passes through, so the header is only
believed when TRUST_X_FORWARDED_FOR says a trusted reverse proxy sets it (its last entry is used).

The per-subject counters live in the process's memory and start again with it, which is enough
for one backend; the daily cost comes from the audit trail, so it survives restarts.
"""

import hashlib
import hmac
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path

import yaml
from pydantic import BaseModel
from starlette.datastructures import MutableHeaders
from starlette.requests import Request

GUEST_COOKIE = "ca_guest"
GUEST_COOKIE_DAYS = 365
# Signing key for guest tokens: one per process, so a restart reissues cookies (the counters
# start again with the process anyway) and nobody can mint tokens without it.
_SECRET = secrets.token_bytes(32)
SWEEP_EVERY = 1000  # calls between evictions of idle subjects

HOUR = 3600
DAY = 24 * HOUR


class Limits(BaseModel, extra="forbid"):
    guest_per_hour: int = 10
    account_per_hour: int = 30
    account_per_day: int = 200
    registrations_per_hour: int = 5  # per address
    login_attempts_per_hour: int = 10  # per email address
    daily_cost_usd: float = 5.0


def load_limits(path: Path) -> Limits:
    if not path.exists():
        return Limits()
    return Limits.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


class RateLimiter:
    def __init__(self, limits: Limits, clock: Callable[[], float] = time.time):
        self.limits = limits
        self.clock = clock
        self._asked: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._calls = 0

    def allow(self, subject: str, guest: bool) -> float | None:
        """Records one question for `subject` and returns None, or returns the time (epoch
        seconds) from which the next question is allowed, recording nothing."""
        per_hour = self.limits.guest_per_hour if guest else self.limits.account_per_hour
        per_day = None if guest else self.limits.account_per_day
        return self._take(subject, per_hour, per_day)

    def attempt(self, subject: str, per_hour: int) -> float | None:
        """The same for other counted actions, such as registrations or login attempts."""
        return self._take(subject, per_hour, None)

    def _take(self, subject: str, per_hour: int, per_day: int | None) -> float | None:
        now = self.clock()
        with self._lock:
            self._calls += 1
            if self._calls % SWEEP_EVERY == 0:  # forget subjects silent for a day
                for stale in [s for s, q in self._asked.items() if not q or q[-1] <= now - DAY]:
                    del self._asked[stale]
            asked = self._asked.setdefault(subject, deque())
            while asked and asked[0] <= now - DAY:
                asked.popleft()
            last_hour = [t for t in asked if t > now - HOUR]
            if len(last_hour) >= per_hour:
                return last_hour[0] + HOUR
            if per_day is not None and len(asked) >= per_day:
                return asked[0] + DAY
            asked.append(now)
            return None


def _sign(raw: str) -> str:
    return hmac.new(_SECRET, raw.encode(), "sha256").hexdigest()[:24]


def issue_guest_token() -> str:
    raw = secrets.token_urlsafe(16)
    return f"{raw}.{_sign(raw)}"


def valid_guest_token(token: str | None) -> bool:
    if not token:
        return False
    raw, _, signature = token.partition(".")
    return bool(raw) and hmac.compare_digest(_sign(raw), signature)


def guest_identity(request: Request) -> str | None:
    """What a guest's answers are filed under: a hash of the browser's signed guest token (the
    one it sent, or the one this response sets), so a copy of the database holds no usable
    cookie. None for a request without any guest token, such as a plain API call."""
    token = request.cookies.get(GUEST_COOKIE)
    if not valid_guest_token(token):
        token = getattr(request.state, "guest_token", None)
    if not token:
        return None
    return hashlib.sha256(token.encode()).hexdigest()[:32]


def client_address(request: Request, trust_forwarded: bool) -> str:
    """The connecting address, or the last x-forwarded-for entry (the one a trusted reverse
    proxy appended) when the deployment says there is such a proxy."""
    if trust_forwarded:
        forwarded = [a.strip() for a in request.headers.get("x-forwarded-for", "").split(",")]
        if forwarded[-1]:
            return forwarded[-1]
    return request.client.host if request.client else "?"


def subject_of(
    request: Request, user: dict | None, trust_forwarded: bool = False
) -> tuple[str, bool]:
    """Who a question counts against: the Account, else a guest token this backend signed, else
    the address. Returns (subject, is_guest)."""
    if user:
        return f"user:{user['id']}", False
    token = request.cookies.get(GUEST_COOKIE)
    if valid_guest_token(token):
        return f"guest:{token}", True
    return f"ip:{client_address(request, trust_forwarded)}", True


class GuestCookie:
    """ASGI middleware: gives every request without a session cookie or a valid guest cookie a
    fresh signed guest id, set on the response. Pure ASGI, so streamed answers pass through."""

    def __init__(self, app, session_cookie: str, secure: bool, skip_prefix: str = "/mcp"):
        self.app = app
        self.session_cookie = session_cookie
        self.secure = secure
        self.skip_prefix = skip_prefix

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"].startswith(self.skip_prefix):
            await self.app(scope, receive, send)
            return
        cookies = Request(scope).cookies
        if self.session_cookie in cookies or valid_guest_token(cookies.get(GUEST_COOKIE)):
            await self.app(scope, receive, send)
            return
        token = issue_guest_token()
        scope.setdefault("state", {})["guest_token"] = token  # this request already counts as it
        value = (
            f"{GUEST_COOKIE}={token}; Path=/; Max-Age={GUEST_COOKIE_DAYS * 24 * 3600}; "
            "HttpOnly; SameSite=Lax" + ("; Secure" if self.secure else "")
        )

        async def send_with_cookie(message):
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append("set-cookie", value)
            await send(message)

        await self.app(scope, receive, send_with_cookie)
