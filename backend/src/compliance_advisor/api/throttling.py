"""Rate limits at the API (config/limits.yaml): questions per guest browser or Account, the app's
daily cost ceiling, and registration and login attempts."""

import time
from datetime import UTC, datetime
from functools import lru_cache

from fastapi import HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError

from ..audit import AuditStore
from ..limits import RateLimiter, load_limits, subject_of
from ..settings import get_settings


@lru_cache
def limiter() -> RateLimiter:
    return RateLimiter(load_limits(get_settings().limits_file))


def throttle(request: Request, user: dict | None, audit: AuditStore | None) -> None:
    """Refuses with 429 when the subject's limit or the app's daily cost ceiling is reached."""
    subject, guest = subject_of(request, user, get_settings().trust_x_forwarded_for)
    retry_at = limiter().allow(subject, guest)
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
        if spent >= limiter().limits.daily_cost_usd:
            raise HTTPException(
                status_code=429,
                detail="The app's daily cost limit is reached; please try again tomorrow",
                headers={
                    "Retry-After": str(int((today.timestamp() + 86400) - time.time())),
                    "X-Limit": "daily-cost",
                },
            )


def limit_attempts(subject: str, per_hour: int, what: str) -> None:
    retry_at = limiter().attempt(subject, per_hour)
    if retry_at is not None:
        when = datetime.fromtimestamp(retry_at, UTC)
        raise HTTPException(
            status_code=429,
            detail=f"Too many {what}; please try again at {when:%H:%M} UTC",
            headers={"Retry-After": str(max(1, int(retry_at - time.time())))},
        )
