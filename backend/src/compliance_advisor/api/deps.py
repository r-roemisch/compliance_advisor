"""What the routers share: the Answer Service, the stores, who is asking, and the role checks.

Routers call these through the module (`deps.get_accounts()`), so a test can replace one of them
in a single place."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError

from .. import analytics
from ..accounts import COOKIE, AccountStore, public
from ..answer import AnswerService, DatabaseError, UpstreamError
from ..apikeys import ApiKeyStore
from ..audit import AuditStore
from ..db import engine
from ..embeddings import get_embeddings
from ..logs import prompt_failed
from ..models import chat_models, helper_models, list_price, load_models, system_prompts
from ..monitoring import EventStore
from ..registry import load_sources
from ..retriever import Retriever
from ..rulechecks import tool_factory
from ..settings import get_settings
from ..store import get_store
from ..update import UpdateStore


@lru_cache
def _service() -> AnswerService:
    settings = get_settings()
    store = get_store(settings, get_embeddings(settings))
    models = chat_models(settings)
    return AnswerService(
        Retriever(
            store,
            settings.max_per_source,
            settings.candidates,
            [s.short_title for s in load_sources(settings.sources_file)],
            keyword_weight=settings.keyword_weight,
        ),
        models,
        load_models(settings.models_file)[0].id,
        settings.top_k,
        tool_factory,
        list_price,
        settings.search_strategy,
        helper_models(settings, models, settings.screening_model) if settings.screening else None,
        prompts=system_prompts(settings.models_file),
        translators=(
            helper_models(settings, models, settings.translation_model)
            if settings.query_translation
            else None
        ),
    )


def get_service() -> AnswerService:
    try:
        return _service()  # built on first use; not cached while the database is down
    except SQLAlchemyError as e:
        prompt_failed("start", e)
        raise DatabaseError("the database is not reachable") from e
    except SystemExit as e:  # missing API key: report it instead of stopping the server
        prompt_failed("start", e)
        raise UpstreamError(str(e)) from None


@lru_cache
def _audit() -> AuditStore:
    return AuditStore(engine(), get_settings().raw_dir)


def get_audit() -> AuditStore | None:
    try:
        return _audit()
    except SQLAlchemyError:
        return None  # answers still work; they are just not stored


@lru_cache
def _accounts() -> AccountStore:
    return AccountStore(engine())


def get_accounts() -> AccountStore:
    try:
        return _accounts()
    except SQLAlchemyError as e:
        raise DatabaseError("the database is not reachable") from e


@lru_cache
def _api_keys() -> ApiKeyStore:
    return ApiKeyStore(engine())


def get_api_keys() -> ApiKeyStore:
    try:
        return _api_keys()
    except SQLAlchemyError as e:
        raise DatabaseError("the database is not reachable") from e


@lru_cache
def _events() -> EventStore:
    return EventStore(engine())


def get_events() -> EventStore | None:
    try:
        return _events()
    except SQLAlchemyError:
        return None


@lru_cache
def _updates() -> UpdateStore:
    return UpdateStore(engine())


def get_updates() -> UpdateStore:
    try:
        return _updates()
    except SQLAlchemyError as e:
        raise DatabaseError("the database is not reachable") from e


Service = Annotated[AnswerService, Depends(get_service)]
Audit = Annotated[AuditStore | None, Depends(get_audit)]


def current_user(request: Request) -> dict | None:
    """The logged-in account, from the session cookie or an API key in the Authorization header
    ("Bearer ca_..."); None for guests. With a key, the dict carries the key's name as "api_key"."""
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        try:
            user = get_api_keys().user_for(header[7:].strip())
        except (DatabaseError, SQLAlchemyError):
            user = None
        if user is None:
            raise HTTPException(status_code=401, detail="Unknown or revoked API key")
        return user
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    try:
        return get_accounts().user_for(token)
    except (DatabaseError, SQLAlchemyError):
        return None


def session_user(user: Annotated[dict | None, Depends(current_user)]) -> dict | None:
    """Everything except asking questions needs a session: an API key is refused here."""
    if user and user.get("api_key"):
        raise HTTPException(
            status_code=403, detail="API keys may only ask questions and run rule checks"
        )
    return user


User = Annotated[dict | None, Depends(current_user)]
SessionUser = Annotated[dict | None, Depends(session_user)]


def require_user(user: dict | None) -> dict:
    if user is None:
        raise HTTPException(status_code=401, detail="Please log in first")
    return user


def require_operator(user: dict | None) -> dict:
    """The Operator role is a flag on the account, granted with `compliance-advisor-accounts
    operator grant <email>` by whoever runs the backend (ADR 0006)."""
    user = require_user(user)
    if not user.get("operator"):
        raise HTTPException(status_code=403, detail="Operators only")
    return user


def public_user(user: dict) -> dict:
    """What the interface may know about an Account, plus whether it is an Operator."""
    return public(user) | {"operator": bool(user.get("operator"))}


def period(days: int) -> int:
    if days not in analytics.PERIODS:
        raise HTTPException(status_code=422, detail="days must be 7, 30, 90 or 0 (every question)")
    return days
