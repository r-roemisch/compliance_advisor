"""Accounts: optional sign-up so a Compliance Officer's questions and Firm Profile stay private.

Passwords are stored only as salted scrypt hashes (Python standard library). A login creates a
random session token; the browser keeps it in an httpOnly cookie, the database keeps only its
SHA-256 hash, so a copy of the database contains no usable passwords or sessions.
"""

import hashlib
import hmac
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Column, DateTime, ForeignKey, String, Table, delete, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from .audit import answers, metadata

SESSION_DAYS = 30
COOKIE = "ca_session"
MIN_PASSWORD = 10

users = Table(
    "users",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("email", String(320), nullable=False, unique=True),
    Column("name", String(200), nullable=False, default=""),
    Column("password_hash", String(300), nullable=False),
    Column("profile", JSONB),  # the Firm Profile, saved with the account
    Column("created_at", DateTime(timezone=True), nullable=False),
)

sessions = Table(
    "sessions",
    metadata,
    Column("token_hash", String(64), primary_key=True),
    Column(
        "user_id",
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AccountError(ValueError):
    """Wrong input for an account action; the message is safe to show."""


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        candidate = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate.hex(), digest)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def public(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "profile": user["profile"],
    }


class AccountStore:
    def __init__(self, engine: Engine):
        self.engine = engine
        metadata.create_all(engine, checkfirst=True)

    def register(self, email: str, password: str, name: str = "") -> dict:
        email = email.strip().lower()
        if not _EMAIL.match(email):
            raise AccountError("Please enter a valid email address.")
        if len(password) < MIN_PASSWORD:
            raise AccountError(f"The password needs at least {MIN_PASSWORD} characters.")
        user = {
            "id": str(uuid.uuid4()),
            "email": email,
            "name": name.strip()[:200],
            "password_hash": hash_password(password),
            "profile": None,
            "created_at": datetime.now(UTC),
        }
        try:
            with self.engine.begin() as connection:
                connection.execute(users.insert().values(**user))
        except IntegrityError:
            raise AccountError("An account with this email address already exists.") from None
        return user

    def authenticate(self, email: str, password: str) -> dict:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(users).where(users.c.email == email.strip().lower())
            ).first()
        if row is None or not verify_password(password, row.password_hash):
            raise AccountError("Email address or password is wrong.")  # same message for both
        return dict(row._mapping)

    def start_session(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        with self.engine.begin() as connection:
            connection.execute(
                sessions.insert().values(
                    token_hash=_token_hash(token),
                    user_id=user_id,
                    expires_at=datetime.now(UTC) + timedelta(days=SESSION_DAYS),
                )
            )
        return token

    def user_for(self, token: str | None) -> dict | None:
        if not token:
            return None
        query = (
            select(users)
            .join(sessions, sessions.c.user_id == users.c.id)
            .where(
                sessions.c.token_hash == _token_hash(token),
                sessions.c.expires_at > datetime.now(UTC),
            )
        )
        with self.engine.connect() as connection:
            row = connection.execute(query).first()
        return dict(row._mapping) if row else None

    def end_session(self, token: str | None) -> None:
        if token:
            with self.engine.begin() as connection:
                connection.execute(
                    delete(sessions).where(sessions.c.token_hash == _token_hash(token))
                )

    def save_profile(self, user_id: str, profile: dict | None) -> None:
        with self.engine.begin() as connection:
            connection.execute(update(users).where(users.c.id == user_id).values(profile=profile))

    def delete(self, user_id: str) -> int:
        """Deletes the account, its sessions and every answer it asked; returns the answer count."""
        with self.engine.begin() as connection:
            removed = connection.execute(
                delete(answers).where(answers.c.user_id == user_id)
            ).rowcount
            connection.execute(delete(users).where(users.c.id == user_id))
        return removed or 0
