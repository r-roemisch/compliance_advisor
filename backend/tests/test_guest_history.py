"""Guest answers belong to the browser that asked (ADR 0005, amended 2026-10-28)."""

import hashlib

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from compliance_advisor.answer import AnswerService
from compliance_advisor.api import app, deps
from compliance_advisor.limits import issue_guest_token

from .test_answering import FakeModel, FakeRetriever


class FakeAudit:
    """Keeps what was saved and answers `recent` and `get` the way the real store filters."""

    def __init__(self):
        self.rows = []

    def save(self, response, profile, user_id=None, api_key=None, guest_id=None):
        response = response.model_copy(update={"id": f"a{len(self.rows) + 1}"})
        self.rows.append(
            {
                "id": response.id,
                "user_id": user_id,
                "guest_id": guest_id,
                "response": response.model_dump(),
            }
        )
        return response

    def recent(self, user_id=None, search="", limit=50, guest_id=None):
        if user_id:
            return [r for r in self.rows if r["user_id"] == user_id]
        return [
            r for r in self.rows if r["user_id"] is None and guest_id and r["guest_id"] == guest_id
        ]

    def get(self, answer_id):
        return next((r for r in self.rows if r["id"] == answer_id), None)

    def cost_since(self, since):
        return 0.0


def _app(audit):
    service = AnswerService(FakeRetriever(), FakeModel(AIMessage(content="Yes [1].")), "m", top_k=6)
    app.dependency_overrides[deps.get_service] = lambda: service
    app.dependency_overrides[deps.get_audit] = lambda: audit
    app.dependency_overrides[deps.current_user] = lambda: None
    return audit


def test_a_guests_first_answer_is_filed_under_the_cookie_the_response_sets():
    audit = _app(FakeAudit())
    browser = TestClient(app)
    response = browser.post("/api/ask", json={"question": "Major incidents?"})
    assert response.status_code == 200
    token = browser.cookies.get("ca_guest")
    assert audit.rows[0]["guest_id"] == hashlib.sha256(token.encode()).hexdigest()[:32]
    # the same browser sees it in its history and may open it
    assert [r["id"] for r in browser.get("/api/history").json()["items"]] == ["a1"]
    assert browser.get("/api/history/a1").status_code == 200


def test_another_browser_sees_neither_the_list_nor_the_answer():
    _app(FakeAudit())
    browser_a = TestClient(app)
    browser_a.post("/api/ask", json={"question": "Major incidents?"})
    browser_b = TestClient(app)
    assert browser_b.get("/api/history").json()["items"] == []
    assert browser_b.get("/api/history/a1").status_code == 404
    assert browser_b.get("/api/history/a1/export").status_code == 404
    # a forged cookie is no identity either
    browser_b.cookies.set("ca_guest", "minted.0000000000000000000000ff")
    assert browser_b.get("/api/history").json()["items"] == []


def test_guest_answers_are_invisible_to_accounts_and_the_other_way_round():
    audit = _app(FakeAudit())
    browser = TestClient(app)
    browser.post("/api/ask", json={"question": "Major incidents?"})
    app.dependency_overrides[deps.current_user] = lambda: {
        "id": "u1",
        "email": "a@b.de",
        "name": "",
        "profile": None,
    }
    signed_in = TestClient(app)
    signed_in.cookies.set("ca_guest", issue_guest_token())
    assert signed_in.get("/api/history").json()["items"] == []
    assert signed_in.get("/api/history/a1").status_code == 404
    signed_in.post("/api/ask", json={"question": "Major incidents?"})
    assert audit.rows[1]["user_id"] == "u1" and audit.rows[1]["guest_id"] is None
