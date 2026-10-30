"""Rate limits and API keys: the limiter without a clock, the key hashing, and the API rules."""

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from compliance_advisor.answer import AnswerService
from compliance_advisor.api import app, deps, throttling
from compliance_advisor.apikeys import PREFIX, key_hash, public
from compliance_advisor.limits import DAY, HOUR, Limits, RateLimiter

from .test_answering import FakeModel, FakeRetriever


def test_rate_limiter_counts_per_hour_and_per_day():
    now = [1000.0]
    limiter = RateLimiter(
        Limits(guest_per_hour=2, account_per_hour=3, account_per_day=4), lambda: now[0]
    )
    assert limiter.allow("ip:1", guest=True) is None
    assert limiter.allow("ip:1", guest=True) is None
    assert limiter.allow("ip:1", guest=True) == 1000.0 + HOUR  # third within the hour: wait
    assert limiter.allow("ip:2", guest=True) is None  # another address is unaffected
    now[0] += HOUR + 1
    assert limiter.allow("ip:1", guest=True) is None  # the hour has passed

    for _ in range(3):
        assert limiter.allow("user:a", guest=False) is None
    assert limiter.allow("user:a", guest=False) is not None  # hour limit
    now[0] += HOUR + 1
    assert limiter.allow("user:a", guest=False) is None  # fourth of the day
    now[0] += HOUR + 1
    assert limiter.allow("user:a", guest=False) == 1000.0 + HOUR + 1 + DAY  # day limit


def test_keys_are_hashed_and_shown_only_as_prefix():
    secret = PREFIX + "abcdefghijklmnop"
    assert key_hash(secret) != secret and len(key_hash(secret)) == 64
    row = {
        "id": "k1",
        "name": "ci",
        "prefix": secret[:10],
        "created_at": None,
        "last_used_at": None,
        "key_hash": "x",
        "user_id": "u",
    }
    assert "key_hash" not in public(row) and "user_id" not in public(row)


def _client(user):
    service = AnswerService(FakeRetriever(), FakeModel(AIMessage(content="Yes [1].")), "m", top_k=6)
    app.dependency_overrides[deps.get_service] = lambda: service
    app.dependency_overrides[deps.get_audit] = lambda: None
    app.dependency_overrides[deps.current_user] = lambda: user
    throttling.limiter.cache_clear()
    return TestClient(app)


def test_api_key_may_ask_but_not_read_the_account():
    client = _client({"id": "u1", "email": "a@b.de", "name": "", "profile": None, "api_key": "ci"})
    assert client.post("/api/ask", json={"question": "Major incidents?"}).status_code == 200
    assert client.get("/api/me/keys").status_code == 403
    assert client.get("/api/history").status_code == 403
    assert client.get("/api/auth/me").status_code == 403


def _ask(client):
    return client.post("/api/ask", json={"question": "Major incidents?"})


def test_guests_are_limited_per_browser_not_per_address():
    limit = throttling.limiter().limits.guest_per_hour
    browser_a = _client(None)
    first = _ask(browser_a)
    assert first.status_code == 200
    cookie = first.headers["set-cookie"]
    assert cookie.startswith("ca_guest=") and "HttpOnly" in cookie and "SameSite=Lax" in cookie
    # The first question counted against the address (no cookie yet); the next `limit` count
    # against this browser's cookie, which the test client now sends back.
    for _ in range(limit):
        assert _ask(browser_a).status_code == 200
    blocked = _ask(browser_a)
    assert blocked.status_code == 429
    assert "try again at" in blocked.json()["detail"] and "Retry-After" in blocked.headers
    # Another browser from the same address (the test client, like the Next.js proxy) still may.
    browser_b = TestClient(app)
    assert _ask(browser_b).status_code == 200
    assert _ask(browser_b).status_code == 200


def test_forged_guest_cookies_fall_back_to_the_address_bucket():
    limit = throttling.limiter().limits.guest_per_hour
    client = _client(None)
    for n in range(limit):
        client.cookies.clear()
        client.cookies.set("ca_guest", f"minted-{n}.0000000000000000000000ff")  # not our signature
        response = _ask(client)
        assert response.status_code == 200
        assert response.headers["set-cookie"].startswith("ca_guest=")  # replaced by a signed one
    client.cookies.clear()
    client.cookies.set("ca_guest", "minted-x.0000000000000000000000ff")
    assert _ask(client).status_code == 429


def test_forwarded_address_is_only_believed_behind_a_trusted_proxy(monkeypatch):
    from compliance_advisor.settings import Settings

    limit = throttling.limiter().limits.guest_per_hour
    client = _client(None)
    for n in range(limit):
        client.cookies.clear()
        assert _ask_from(client, f"10.0.0.{n}").status_code == 200
    client.cookies.clear()
    assert _ask_from(client, "10.0.0.99").status_code == 429  # header ignored: one address
    monkeypatch.setattr(throttling, "get_settings", lambda: Settings(trust_x_forwarded_for=True))
    throttling.limiter.cache_clear()
    for n in range(limit + 2):
        client.cookies.clear()
        assert _ask_from(client, f"10.0.0.{n}").status_code == 200  # now one bucket per address


def _ask_from(client, forwarded):
    return client.post(
        "/api/ask", json={"question": "Major incidents?"}, headers={"x-forwarded-for": forwarded}
    )


def test_requests_without_any_cookie_share_the_address_bucket():
    limit = throttling.limiter().limits.guest_per_hour
    client = _client(None)
    for _ in range(limit):
        client.cookies.clear()  # a script that drops the cookie every time
        assert _ask(client).status_code == 200
    client.cookies.clear()
    assert _ask(client).status_code == 429


def test_mcp_and_signed_in_requests_get_no_guest_cookie():
    client = _client({"id": "u1", "email": "a@b.de", "name": "", "profile": None})
    client.cookies.set("ca_session", "x")
    assert "set-cookie" not in _ask(client).headers


# --- Registration and login limits (review fix A6) -------------------------------------------


def test_registrations_are_limited_per_address(monkeypatch):
    class Accounts:
        def register(self, email, password, name=""):
            return {"id": email, "email": email, "name": name, "profile": None}

        def start_session(self, user_id):
            return "token"

    monkeypatch.setattr(deps, "get_accounts", lambda: Accounts())
    client = TestClient(app)
    limit = throttling.limiter().limits.registrations_per_hour
    for n in range(limit):
        body = {"email": f"u{n}@example.org", "password": "Secret-123"}
        assert client.post("/api/auth/register", json=body).status_code == 200
    response = client.post(
        "/api/auth/register", json={"email": "x@example.org", "password": "Secret-123"}
    )
    assert response.status_code == 429 and "registrations" in response.json()["detail"]


def test_login_attempts_are_limited_per_email(monkeypatch):
    from compliance_advisor.accounts import AccountError

    class Accounts:
        def authenticate(self, email, password):
            raise AccountError("Email address or password is wrong.")

    monkeypatch.setattr(deps, "get_accounts", lambda: Accounts())
    client = TestClient(app)
    limit = throttling.limiter().limits.login_attempts_per_hour
    for _ in range(limit):
        assert (
            client.post(
                "/api/auth/login", json={"email": "Victim@example.org", "password": "x"}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/auth/login", json={"email": "victim@example.org", "password": "x"}
        ).status_code
        == 429
    )
    assert (
        client.post(
            "/api/auth/login", json={"email": "other@example.org", "password": "x"}
        ).status_code
        == 401
    )
