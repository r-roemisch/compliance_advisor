"""The MCP server: an API key is required, the tools are listed, and a Rule Check runs."""

import json
import types

from fastapi.testclient import TestClient

from compliance_advisor import api

HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}


def _rpc(client, key, method, params=None, id=1):
    body = {"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}}
    headers = HEADERS | ({"authorization": f"Bearer {key}"} if key else {})
    return client.post("/mcp/", json=body, headers=headers)


class FakeRetriever:
    def __init__(self):
        self.questions = []

    def retrieve(self, question, k, strategy="vector"):
        self.questions.append(question)
        return []


def test_mcp_requires_an_api_key(monkeypatch):
    class Keys:
        def user_for(self, secret):
            return {"id": "u1", "email": "a@b.de", "api_key": "ci"} if secret == "ca_good" else None

    monkeypatch.setattr(api, "get_api_keys", lambda: Keys())
    retriever = FakeRetriever()
    monkeypatch.setattr(api, "get_service", lambda: types.SimpleNamespace(retriever=retriever))
    with TestClient(api.app) as client:
        assert _rpc(client, None, "tools/list").status_code == 401
        assert _rpc(client, "ca_bad", "tools/list").status_code == 401
        response = _rpc(client, "ca_good", "tools/list")
        assert response.status_code == 200, response.text
        names = {t["name"] for t in response.json()["result"]["tools"]}
        assert names == {
            "check_applicability",
            "compliance_timeline",
            "classify_dora_incident",
            "check_ai_act_use_case",
            "search_corpus",
        }
        # A Rule Check runs for the key's Account (the session manager starts once per app,
        # so this stays in the same client session).
        response = _rpc(
            client,
            "ca_good",
            "tools/call",
            {
                "name": "check_applicability",
                "arguments": {
                    "firm_type": "payment_institution",
                    "size": "small",
                    "activities": [],
                },
            },
            id=2,
        )
        assert response.status_code == 200, response.text
        result = response.json()["result"]
        assert not result.get("isError"), result
        text = json.loads(result["content"][0]["text"])
        assert text["findings"] and any(f["applies"] == "yes" for f in text["findings"])
        # search_corpus gets the same Pre-Check as the question field: length and personal data
        short = _rpc(
            client,
            "ca_good",
            "tools/call",
            {"name": "search_corpus", "arguments": {"question": "ab"}},
            id=3,
        )
        assert short.json()["result"].get("isError") is True
        call = {
            "name": "search_corpus",
            "arguments": {"question": "Konto DE89 3704 0044 0532 0130 00 und Meldung?"},
        }
        ok = _rpc(client, "ca_good", "tools/call", call, id=4)
        assert not ok.json()["result"].get("isError"), ok.text
        assert retriever.questions == ["Konto [IBAN removed] und Meldung?"]
