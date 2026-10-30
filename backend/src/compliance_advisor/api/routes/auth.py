"""Accounts: register, log in and out, and who is logged in. The session is an httpOnly cookie."""

from fastapi import APIRouter, HTTPException, Request, Response

from ...accounts import COOKIE, SESSION_DAYS, AccountError, AccountStore
from ...limits import client_address
from ...schemas import LoginRequest, RegisterRequest
from ...settings import get_settings
from .. import deps
from ..throttling import limit_attempts, limiter

router = APIRouter()


def _login(response: Response, accounts: AccountStore, user: dict) -> dict:
    token = accounts.start_session(user["id"])
    response.set_cookie(
        COOKIE,
        token,
        max_age=SESSION_DAYS * 24 * 3600,
        httponly=True,  # not readable by page scripts
        samesite="lax",
        secure=get_settings().cookie_secure,
        path="/",
    )
    return {"user": deps.public_user(user)}


@router.post("/api/auth/register")
def register(body: RegisterRequest, response: Response, http: Request) -> dict:
    limits = limiter().limits
    address = client_address(http, get_settings().trust_x_forwarded_for)
    limit_attempts(f"register:{address}", limits.registrations_per_hour, "registrations")
    accounts = deps.get_accounts()
    user = accounts.register(body.email, body.password, body.name)
    return _login(response, accounts, user)


@router.post("/api/auth/login")
def login(body: LoginRequest, response: Response) -> dict:
    limits = limiter().limits
    email = body.email.strip().lower()
    limit_attempts(f"login:{email}", limits.login_attempts_per_hour, "login attempts")
    accounts = deps.get_accounts()
    try:
        user = accounts.authenticate(body.email, body.password)
    except AccountError as e:
        raise HTTPException(status_code=401, detail=str(e)) from None
    return _login(response, accounts, user)


@router.post("/api/auth/logout")
def logout(request: Request, response: Response) -> dict:
    deps.get_accounts().end_session(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/")
    return {"user": None}


@router.get("/api/auth/me")
def me(user: deps.SessionUser) -> dict:
    return {"user": deps.public_user(user) if user else None}
