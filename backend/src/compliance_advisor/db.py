"""The one database engine of the process (Postgres); every store shares it."""

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from .settings import get_settings


@lru_cache
def engine() -> Engine:
    # connect_timeout: a request must not hang for a minute when Postgres is down.
    # hide_parameters: a database error's text must not carry a question into the logs (ADR 0006).
    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3},
        hide_parameters=True,
    )
