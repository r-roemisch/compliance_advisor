"""Extract Obligations and the timeline endpoint, without network or database."""

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from compliance_advisor import api
from compliance_advisor.obligations import ExtractedRow, Extraction, extract_obligations

PASSAGES = [
    {
        "n": 1,
        "short_title": "DORA",
        "provision": "Art. 19 DORA",
        "link": "https://eur-lex/dora#art_19",
        "url": "https://eur-lex/dora",
        "text": "Financial entities shall report major ICT-related incidents.",
    },
    {
        "n": 2,
        "short_title": "DORA",
        "provision": "Art. 17 DORA",
        "link": "https://eur-lex/dora#art_17",
        "url": "https://eur-lex/dora",
        "text": "Financial entities shall record all ICT-related incidents.",
    },
]


class StructuredModel:
    def __init__(self, rows):
        self.rows = rows
        self.seen = None

    def with_structured_output(self, schema, include_raw=False):
        return self

    def invoke(self, messages):
        self.seen = messages[1].content
        return {"parsed": Extraction(obligations=self.rows), "raw": AIMessage(content="")}


def test_rows_take_provision_and_link_from_the_passage_and_drop_unknown_numbers():
    model = StructuredModel(
        [
            ExtractedRow(
                addressee="financial entity",
                action="Report major incidents",
                deadline="4 hours",
                passage=1,
            ),
            ExtractedRow(addressee="financial entity", action="Invented duty", passage=7),
        ]
    )
    rows, _ = extract_obligations(model, "When must we report?", PASSAGES, cited=[1])
    assert len(rows) == 1
    assert (rows[0].provision, rows[0].link, rows[0].deadline) == (
        "Art. 19 DORA",
        "https://eur-lex/dora#art_19",
        "4 hours",
    )
    assert "Art. 17" not in model.seen  # only cited passages are sent when there are any


def test_language_follows_the_question():
    model = StructuredModel([])
    extract_obligations(model, "Wann müssen wir melden?", PASSAGES, cited=[])
    assert "Language: German" in model.seen


def test_timeline_can_be_narrowed_to_the_firm_profile():
    client = TestClient(api.app)
    everything = client.post("/api/timeline", json={}).json()
    reinsurer = client.post("/api/timeline", json={"profile": {"firm_type": "reinsurer"}}).json()
    sources_all = {e["source"] for e in everything["entries"]}
    sources_re = {e["source"] for e in reinsurer["entries"]}
    assert reinsurer["filtered"] and sources_re < sources_all
    assert (
        "AMLR" not in sources_re and "Solvency II" in sources_re
    )  # reinsurers are not AML-obliged
