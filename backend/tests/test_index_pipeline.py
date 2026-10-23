"""Loaders, chunkers and registry: the index pipeline without network or database."""

import zipfile

import pytest

from compliance_advisor import loaders
from compliance_advisor.chunker import chunk_fixed, chunk_provisions, passage_id
from compliance_advisor.loaders import LoadedSource, Section, link_for
from compliance_advisor.registry import Source, load_sources

EU = Source(
    id="eu-dora",
    title="DORA",
    short_title="DORA",
    regime="dora",
    layer="eu_level_1",
    issuer="EP",
    language="en",
    format="html",
    url="https://publications.europa.eu/resource/celex/32022R2554",
    display_url="https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32022R2554",
)
DE = Source(
    id="de-gwg",
    title="GwG",
    short_title="GwG",
    regime="aml",
    layer="national_law",
    issuer="Bund",
    language="de",
    format="gii_xml",
    url="https://www.gesetze-im-internet.de/gwg_2017/xml.zip",
    display_url="https://www.gesetze-im-internet.de/gwg_2017/",
)
PDF = Source(
    id="de-bafin",
    title="AuA",
    short_title="BaFin AuA GwG",
    regime="aml",
    layer="supervisory_practice",
    issuer="BaFin",
    language="de",
    format="pdf",
    url="https://www.bafin.de/doc.pdf?__blob=publicationFile&v=1",
    display_url="https://www.bafin.de/doc.html",
)


def test_html_loader_returns_articles_and_recitals_with_anchors(tmp_path):
    path = tmp_path / "act.html"
    path.write_text(
        """<html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title></head><body>
        <div class="eli-subdivision" id="rct_3"><table><tr>
          <td><p class="oj-normal">(3)</p></td>
          <td><p class="oj-normal">the Council
            (<a href="#n6"><span class="oj-super">6</span></a>) and</p></td>
        </tr></table></div>
        <div class="eli-subdivision" id="art_8">
          <p class="oj-ti-art">Article 8</p>
          <div class="eli-title" id="art_8.tit_1"><p class="oj-sti-art">Major incidents</p></div>
          <table><tr>
            <td><p class="oj-normal">(a)</p></td>
            <td><p class="oj-normal">costs for maintenance;</p></td>
          </tr></table>
        </div></body></html>"""
    )
    recital, article = loaders.load_html(path)
    assert (recital.label, recital.target) == ("Recital 3", "#rct_3")
    assert "(3) the Council (6) and" in recital.text
    assert (article.label, article.title, article.target) == ("Art. 8", "Major incidents", "#art_8")
    assert "(a) costs for maintenance;" in article.text


def test_gii_loader_returns_paragraphs_with_nested_lists_and_page_targets(tmp_path):
    xml = (
        "<dokumente>"
        "<norm><metadaten><enbez>Inhaltsübersicht</enbez></metadaten>"
        "<textdaten><text><Content><P>§ 10 ...</P></Content></text></textdaten></norm>"
        "<norm><metadaten><enbez>§ 10</enbez><titel>Allgemeine Sorgfaltspflichten</titel>"
        "</metadaten><textdaten><text><Content><P>(1) Die Pflichten sind:<DL>"
        "<DT>1.</DT><DD><LA>die Identifizierung,</LA></DD>"
        "<DT>2.</DT><DD><LA>die Abklärung</LA></DD></DL></P></Content></text></textdaten>"
        "</norm></dokumente>"
    )
    path = tmp_path / "act.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("act.xml", xml)
    (section,) = loaders.load_gii_xml(path)  # the table of contents is skipped
    assert (section.label, section.target) == ("§ 10", "__10.html")
    assert section.text == (
        "§ 10 Allgemeine Sorgfaltspflichten\n(1) Die Pflichten sind:\n"
        "1. die Identifizierung,\n2. die Abklärung"
    )


def test_pdf_loader_follows_the_table_of_contents(tmp_path, monkeypatch):
    pages = {
        1: "Hinweise S 1\nInhaltsverzeichnis\n1. Adressaten 2\n1.1 Banken 2\n1.2 Versicherer 2\n"
        "2. Pflichten 3\n2.1 Identifizierung 4\nEnde 1",
        2: "Hinweise S 2\n1. Adressaten\nText über Adressaten.\n1.1 Banken\n2. Eine Aufzählung\n"
        "1.2 Versicherer\nEnde 2",
        3: "Hinweise S 3\n2. Pflichten\nText über Pflichten.\nmehr Text\nEnde 3",
        4: "Hinweise S 4\n2.1 Identifizierung\nzur Identifizierung\nweiter\nEnde 4",
    }

    class Page:
        def __init__(self, number):
            self.number = number

        def extract_text(self):
            return pages[self.number]

    class Reader:
        def __init__(self, path):
            self.pages = [Page(n) for n in pages]

    monkeypatch.setattr(loaders, "PdfReader", Reader)
    sections = loaders.load_pdf(tmp_path / "doc.pdf")
    assert [(s.label, s.target) for s in sections] == [
        ("1", "#page=2"),
        ("1.1", "#page=2"),
        ("1.2", "#page=2"),
        ("2", "#page=3"),
        ("2.1", "#page=4"),
    ]
    assert "2. Eine Aufzählung" in sections[1].text  # a list item, not the heading of section 2
    assert "Hinweise" not in "".join(s.text for s in sections)  # running header removed


def test_links_open_the_exact_provision():
    assert link_for(EU, "#art_17").endswith("?uri=CELEX:32022R2554#art_17")
    assert link_for(DE, "__10.html") == "https://www.gesetze-im-internet.de/gwg_2017/__10.html"
    assert link_for(PDF, "#page=67") == PDF.url + "#page=67"
    assert link_for(DE, "") == DE.display_url  # annexes without own page open the act


def test_passage_ids_are_stable_and_depend_on_position_and_text():
    assert passage_id("de-gwg", 0, "text") == passage_id("de-gwg", 0, "text")
    assert passage_id("de-gwg", 0, "text") != passage_id("de-gwg", 1, "text")
    assert passage_id("de-gwg", 0, "text") != passage_id("de-gwg", 0, "other")


def test_provision_chunker_splits_long_provisions_and_keeps_the_label():
    loaded = LoadedSource(
        sections=[
            Section("§ 1", "Kurz", "__1.html", "§ 1 Kurz\nEin Satz."),
            Section("§ 10", "Lang", "__10.html", "§ 10 Lang\n" + "Satz. " * 800),
        ],
        metadata={"source_id": "de-gwg", "short_title": "GwG", "layer": "national_law"},
    )
    passages = chunk_provisions(loaded, DE, max_chars=2500, overlap=200)
    assert passages[0].metadata["provision"] == "§ 1 GwG"
    assert passages[0].page_content.startswith("§ 1 GwG – Kurz\n")
    long_parts = passages[1:]
    assert len(long_parts) >= 2 and all(len(p.page_content) <= 2500 for p in long_parts)
    assert long_parts[0].page_content.startswith(f"§ 10 GwG – Lang (part 1 of {len(long_parts)})")
    assert {p.metadata["link"] for p in long_parts} == {DE.display_url + "__10.html"}


def test_fixed_chunker_cuts_with_overlap_and_copies_metadata():
    loaded = LoadedSource(
        sections=[Section("§ 1", "", "", "Satz. " * 400)],
        metadata={"source_id": "de-gwg", "layer": "x"},
    )
    passages = chunk_fixed(loaded, chunk_size=1000, chunk_overlap=150)
    assert len(passages) > 1 and all(len(p.page_content) <= 1000 for p in passages)
    assert [p.metadata["position"] for p in passages] == list(range(len(passages)))
    assert passages[0].page_content[-100:] in passages[1].page_content


def test_registry_rejects_unknown_values(tmp_path):
    path = tmp_path / "sources.yaml"
    path.write_text(
        "sources:\n  - id: x\n    title: t\n    short_title: t\n    regime: dora\n"
        "    layer: eu_level_9\n    issuer: i\n    language: en\n    format: html\n    url: u\n"
    )
    with pytest.raises(SystemExit, match="layer"):
        load_sources(path)


def test_number_tables_are_not_indexed():
    from compliance_advisor.chunker import mostly_text

    assert not mostly_text("76 98 80 82 85 75 NP\n77 99 81 83 86 76 NR")
    assert mostly_text(
        "Art. 19 DORA: Financial entities shall report major incidents within 4 hours."
    )
