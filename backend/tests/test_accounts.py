"""Accounts: password hashing, sessions over the API, and private answers. No database."""

import pytest
from fastapi.testclient import TestClient

from compliance_advisor.accounts import COOKIE, AccountError, hash_password, public, verify_password
from compliance_advisor.api import app, deps


def test_password_hashes_are_salted_and_verifiable():
    first, second = hash_password("correct horse battery"), hash_password("correct horse battery")
    assert first != second and first.startswith("scrypt$")
    assert verify_password("correct horse battery", first)
    assert not verify_password("wrong password!", first)
    assert not verify_password("anything", "not-a-hash")


class FakeAccounts:
    """In-memory stand-in for AccountStore with the same rules."""

    def __init__(self):
        self.users, self.sessions = {}, {}

    def register(self, email, password, name=""):
        email = email.strip().lower()
        if "@" not in email:
            raise AccountError("Please enter a valid email address.")
        if len(password) < 10:
            raise AccountError("The password needs at least 10 characters.")
        if any(u["email"] == email for u in self.users.values()):
            raise AccountError("An account with this email address already exists.")
        user = {
            "id": f"u{len(self.users) + 1}",
            "email": email,
            "name": name,
            "profile": None,
            "password_hash": hash_password(password),
        }
        self.users[user["id"]] = user
        return user

    def authenticate(self, email, password):
        user = next((u for u in self.users.values() if u["email"] == email.strip().lower()), None)
        if user is None or not verify_password(password, user["password_hash"]):
            raise AccountError("Email address or password is wrong.")
        return user

    def start_session(self, user_id):
        token = f"t{len(self.sessions) + 1}"
        self.sessions[token] = user_id
        return token

    def user_for(self, token):
        return self.users.get(self.sessions.get(token or ""))

    def end_session(self, token):
        self.sessions.pop(token or "", None)

    def save_profile(self, user_id, profile):
        self.users[user_id]["profile"] = profile

    def delete(self, user_id):
        self.users.pop(user_id)
        return 0


class FakeAudit:
    def __init__(self, records):
        self.records = records

    def get(self, answer_id):
        return self.records.get(answer_id)


@pytest.fixture
def client(monkeypatch):
    accounts = FakeAccounts()
    monkeypatch.setattr(deps, "get_accounts", lambda: accounts)
    app.dependency_overrides.clear()
    return TestClient(app), accounts


def test_register_sets_an_httponly_cookie_and_me_returns_the_user(client):
    http, _ = client
    r = http.post(
        "/api/auth/register",
        json={"email": "Anna@Example.com", "password": "long enough pw", "name": "Anna"},
    )
    assert r.status_code == 200 and r.json()["user"]["email"] == "anna@example.com"
    cookie = r.headers["set-cookie"].lower()
    assert f"{COOKIE}=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert http.get("/api/auth/me").json()["user"]["name"] == "Anna"
    assert "password_hash" not in http.get("/api/auth/me").json()["user"]


def test_short_passwords_and_duplicate_emails_are_rejected(client):
    http, _ = client
    assert (
        http.post("/api/auth/register", json={"email": "a@b.de", "password": "short"}).status_code
        == 422
    )
    http.post("/api/auth/register", json={"email": "a@b.de", "password": "long enough pw"})
    again = http.post("/api/auth/register", json={"email": "A@B.de", "password": "long enough pw"})
    assert again.status_code == 422 and "already exists" in again.json()["detail"]


def test_wrong_password_gives_401_and_logout_ends_the_session(client):
    http, _ = client
    http.post("/api/auth/register", json={"email": "a@b.de", "password": "long enough pw"})
    http.post("/api/auth/logout")
    assert http.get("/api/auth/me").json()["user"] is None
    assert (
        http.post(
            "/api/auth/login", json={"email": "a@b.de", "password": "wrong password"}
        ).status_code
        == 401
    )
    assert (
        http.post(
            "/api/auth/login", json={"email": "a@b.de", "password": "long enough pw"}
        ).status_code
        == 200
    )


def test_profile_is_saved_with_the_account_and_requires_login(client):
    http, accounts = client
    assert (
        http.put("/api/me/profile", json={"profile": {"firm_type": "reinsurer"}}).status_code == 401
    )
    http.post("/api/auth/register", json={"email": "a@b.de", "password": "long enough pw"})
    r = http.put("/api/me/profile", json={"profile": {"firm_type": "reinsurer"}})
    assert r.json()["user"]["profile"]["firm_type"] == "reinsurer"
    assert public(accounts.users["u1"])["profile"]["firm_type"] == "reinsurer"


def test_answers_are_visible_only_to_their_owner(client):
    http, _ = client
    records = {"mine": {"id": "mine", "user_id": "u1"}, "guest": {"id": "guest", "user_id": None}}
    app.dependency_overrides[deps.get_audit] = lambda: FakeAudit(records)
    # a guest answer without a guest id (stored before 2026-10-28) belongs to nobody now
    assert http.get("/api/history/guest").status_code == 404
    assert http.get("/api/history/mine").status_code == 404  # but not account answers
    http.post("/api/auth/register", json={"email": "a@b.de", "password": "long enough pw"})
    assert http.get("/api/history/mine").status_code == 200
    assert http.get("/api/history/guest").status_code == 404
    http.post("/api/auth/logout")
    http.post("/api/auth/register", json={"email": "c@d.de", "password": "long enough pw"})
    assert http.get("/api/history/mine").status_code == 404  # another account
    app.dependency_overrides.clear()
