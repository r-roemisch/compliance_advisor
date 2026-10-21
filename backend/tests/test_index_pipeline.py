"""Loaders, chunker and registry: the index pipeline without network or database."""

import zipfile

import pytest

from compliance_advisor import loaders
from compliance_advisor.chunker import chunk, passage_id
from compliance_advisor.loaders import LoadedSource
from compliance_advisor.registry import load_sources


def test_html_loader_keeps_markers_in_their_sentence(tmp_path):
    path = tmp_path / "act.html"
    path.write_text(
        """<html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title></head><body>
        <p class="oj-ti-art">Article 8</p>
        <p class="oj-normal">the Council
           (<a href="#n6"><span class="oj-super">6</span></a>) and</p>
        <table><tr>
          <td><p class="oj-normal">(a)</p></td>
          <td><p class="oj-normal">costs for maintenance;</p></td>
        </tr></table></body></html>"""
    )
    text = loaders.load_html(path)
    assert "Article 8" in text
    assert "the Council (6) and" in text
    assert "(a) costs for maintenance;" in text


def test_gii_loader_keeps_nested_lists_with_their_paragraph(tmp_path):
    xml = (
        "<dokumente><norm><metadaten><enbez>§ 10</enbez><titel>Allgemeine Sorgfaltspflichten"
        "</titel></metadaten><textdaten><text><Content><P>(1) Die Pflichten sind:<DL>"
        "<DT>1.</DT><DD><LA>die Identifizierung,</LA></DD>"
        "<DT>2.</DT><DD><LA>die Abklärung</LA></DD></DL></P></Content></text></textdaten>"
        "</norm></dokumente>"
    )
    path = tmp_path / "act.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("act.xml", xml)
    assert loaders.load_gii_xml(path) == (
        "§ 10 Allgemeine Sorgfaltspflichten\n(1) Die Pflichten sind:\n"
        "1. die Identifizierung,\n2. die Abklärung"
    )


def test_pdf_loader_drops_running_headers(tmp_path, monkeypatch):
    class Page:
        def __init__(self, number):
            self.number = number

        def extract_text(self):
            return (
                f"Hinweise zum GwG Seite {self.number} von 4\nAbschnitt {self.number}\n"
                f"Inhalt der Seite {self.number}\nText {self.number}\nEnde {self.number}"
            )

    class Reader:
        def __init__(self, path):
            self.pages = [Page(n) for n in range(1, 5)]

    monkeypatch.setattr(loaders, "PdfReader", Reader)
    text = loaders.load_pdf(tmp_path / "doc.pdf")
    assert "Hinweise zum GwG" not in text  # the running header is gone
    assert "Inhalt der Seite 3" in text  # a mid-page line of the same shape on every page stays


def test_passage_ids_are_stable_and_depend_on_position_and_text():
    assert passage_id("de-gwg", 0, "text") == passage_id("de-gwg", 0, "text")
    assert passage_id("de-gwg", 0, "text") != passage_id("de-gwg", 1, "text")
    assert passage_id("de-gwg", 0, "text") != passage_id("de-gwg", 0, "other")


def test_chunker_cuts_with_overlap_and_copies_metadata():
    loaded = LoadedSource(text="Satz. " * 400, metadata={"source_id": "de-gwg", "layer": "x"})
    passages = chunk(loaded, chunk_size=1000, chunk_overlap=150)
    assert len(passages) > 1
    assert all(len(p.page_content) <= 1000 for p in passages)
    assert [p.metadata["position"] for p in passages] == list(range(len(passages)))
    assert all(p.metadata["source_id"] == "de-gwg" for p in passages)
    first, second = passages[0].page_content, passages[1].page_content
    assert first[-100:] in second  # the overlap repeats the end of the previous Passage


def test_registry_rejects_unknown_values(tmp_path):
    path = tmp_path / "sources.yaml"
    path.write_text(
        "sources:\n  - id: x\n    title: t\n    short_title: t\n    regime: dora\n"
        "    layer: eu_level_9\n    issuer: i\n    language: en\n    format: html\n    url: u\n"
    )
    with pytest.raises(SystemExit, match="layer"):
        load_sources(path)
