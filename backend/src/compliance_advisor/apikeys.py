"""API keys: an Account lets its own programs or an MCP client ask questions and run Rule Checks.

A key is shown once, when it is created; the database keeps only its SHA-256 hash and a short
prefix so keys can be told apart. A key may only ask questions and run Rule Checks (ADR 0005:
nothing else of the Account is reachable with it), so a leaked key does limited damage.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Table, select, update
from sqlalchemy.engine import Engine

from . import accounts
from .audit import metadata

api_keys = Table(
    "api_keys",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "user_id",
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("name", String(100), nullable=False),
    Column("key_hash", String(64), nullable=False, unique=True),
    Column("prefix", String(12), nullable=False),  # the first characters, to tell keys apart
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_used_at", DateTime(timezone=True)),
    Column("revoked_at", DateTime(timezone=True)),
)

PREFIX = "ca_"


def key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def public(row: dict) -> dict:
    return {k: row[k] for k in ("id", "name", "prefix", "created_at", "last_used_at")}


class ApiKeyStore:
    def __init__(self, engine: Engine):
        self.engine = engine
        metadata.create_all(engine, checkfirst=True)

    def create(self, user_id: str, name: str) -> tuple[dict, str]:
        """Returns the key's public row and the secret, which is never stored."""
        secret = PREFIX + secrets.token_urlsafe(32)
        row = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "name": name.strip()[:100] or "key",
            "key_hash": key_hash(secret),
            "prefix": secret[:10],
            "created_at": datetime.now(UTC),
            "last_used_at": None,
            "revoked_at": None,
        }
        with self.engine.begin() as connection:
            connection.execute(api_keys.insert().values(**row))
        return public(row), secret

    def list(self, user_id: str) -> list[dict]:
        query = (
            select(api_keys)
            .where(api_keys.c.user_id == user_id, api_keys.c.revoked_at.is_(None))
            .order_by(api_keys.c.created_at.desc())
        )
        with self.engine.connect() as connection:
            return [public(dict(r._mapping)) for r in connection.execute(query)]

    def revoke(self, user_id: str, key_id: str) -> bool:
        with self.engine.begin() as connection:
            result = connection.execute(
                update(api_keys)
                .where(
                    api_keys.c.id == key_id,
                    api_keys.c.user_id == user_id,
                    api_keys.c.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(UTC))
            )
        return bool(result.rowcount)

    def user_for(self, secret: str) -> dict | None:
        """The Account behind a key, with the key's name under "api_key"; None for an unknown or
        revoked key. Records when the key was last used."""
        if not secret.startswith(PREFIX):
            return None
        query = (
            select(accounts.users, api_keys.c.id.label("key_id"), api_keys.c.name.label("api_key"))
            .join(api_keys, api_keys.c.user_id == accounts.users.c.id)
            .where(api_keys.c.key_hash == key_hash(secret), api_keys.c.revoked_at.is_(None))
        )
        with self.engine.begin() as connection:
            row = connection.execute(query).first()
            if row is None:
                return None
            connection.execute(
                update(api_keys)
                .where(api_keys.c.id == row.key_id)
                .values(last_used_at=datetime.now(UTC))
            )
        user = dict(row._mapping)
        user.pop("key_id")
        return user
