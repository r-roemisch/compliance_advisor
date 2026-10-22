"""Loaders: turn one downloaded file into its Provisions, plus the Source's metadata.

One function per file format, chosen by the `format` field of the registry entry. Each
returns Sections: one per Provision (an article, recital, annex, § or numbered guideline
section), with a citable label and the link fragment that opens exactly that Provision.
"""

import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

from bs4 import BeautifulSoup
from lxml import etree
from pypdf import PdfReader

from .fetch import FILE_NAMES
from .registry import Source


@dataclass
class Section:
    label: str  # "Art. 17", "Recital 10", "Annex I", "§ 10", "5.7", "S. 3"
    title: str  # the Provision's heading, may be empty
    target: str  # how to reach it: "#art_17" (anchor), "__10.html" (page), "#page=67"
    text: str  # the Provision's full text, heading included


@dataclass
class LoadedSource:
    sections: list[Section]
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n\n".join(s.text for s in self.sections)


def _tidy(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# --- EU acts: XHTML from the EU Publications Office ---------------------------------------

_BLOCKS = ["p", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br", "table"]
_EU_UNIT = re.compile(r"^(rct_\d+|art_\w+|anx_.+)$")


def _prepare(soup: BeautifulSoup) -> None:
    """Block elements become lines; table cells in a row and footnote markers stay inline."""
    for tag in soup(["script", "style", "head", "nav"]):
        tag.decompose()
    # The file's own indentation and line breaks between tags are not part of the text.
    for string in soup.find_all(string=True):
        string.replace_with(re.sub(r"\s+", " ", string))
    for cell in soup.find_all(["td", "th"]):
        cell.append(" ")
    # Consolidated texts put a point's number ("(1)") in its own column next to the text.
    for marker in soup.find_all(class_="grid-list-column-1"):
        marker.append(" ")
        marker.name = "span"
    for block in soup.find_all(_BLOCKS):
        inside_cell = block.name != "tr" and block.find_parent(["td", "th"]) is not None
        block.append(" " if inside_cell else "\n")


_AMENDMENT_MARKER = re.compile(r"[►▼]\s?[A-Z]\d*|◄")  # "►M3 … ◄" in consolidated texts


def _eu_section(element) -> Section:
    unit_id = element["id"]
    text = _tidy(_AMENDMENT_MARKER.sub("", element.get_text()))
    kind, number = unit_id.split("_", 1)
    number = number.replace("\xa0", " ").strip()
    if kind == "art":
        subtitle = element.find(class_="oj-sti-art") or element.find(class_="eli-title")
        title = _tidy(_AMENDMENT_MARKER.sub("", subtitle.get_text())) if subtitle else ""
        label = f"Art. {number}"
    elif kind == "rct":
        title, label = "", f"Recital {number}"
    else:
        lines = text.split("\n")
        title = lines[1] if len(lines) > 1 and len(lines[1]) < 200 else ""
        label = f"Annex {number}"
    return Section(label=label, title=title, target="#" + quote(unit_id), text=text)


def load_html(path: Path) -> list[Section]:
    """EU acts, original (Official Journal) or consolidated: one Section per recital, article
    and annex. Both formats mark these units with the same ids ("art_17", "anx_I")."""
    soup = BeautifulSoup(path.read_bytes(), "xml")
    _prepare(soup)
    units = [e for e in soup.find_all(id=_EU_UNIT) if not e.find_parent(id=_EU_UNIT)]
    return [s for s in (_eu_section(e) for e in units) if s.text]


# --- German acts: gesetze-im-internet.de ---------------------------------------------------


def _lines(content) -> list[str]:
    """Paragraphs become lines. Numbered lists, also when nested inside a paragraph or inside
    another list item, put each item on its own line ("1. text", "a) text")."""
    lines: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        text = " ".join(" ".join(buffer).split())
        if text:
            lines.append(text)
        buffer.clear()

    def walk(element) -> None:
        if element.tag == "DL":
            flush()
            for item in element:
                if item.tag == "DT":
                    flush()
                walk_inner(item)
            flush()
        else:
            walk_inner(element)
        if element.tail:
            buffer.append(element.tail)

    def walk_inner(element) -> None:
        if element.text:
            buffer.append(element.text)
        for child in element:
            walk(child)

    for child in content:
        walk(child)
        flush()
    return lines


def _gii_target(designation: str) -> str:
    """ "§ 10" -> "__10.html", "§ 25a" -> "__25a.html"; anything else opens the act's page."""
    match = re.fullmatch(r"§\s*(\d+[a-z]?)", designation)
    return f"__{match.group(1)}.html" if match else ""


def load_gii_xml(path: Path) -> list[Section]:
    """German acts: a zip with one XML file, one <norm> per §, annex or heading."""
    with zipfile.ZipFile(path) as archive:
        xml_name = next(n for n in archive.namelist() if n.lower().endswith(".xml"))
        root = etree.parse(io.BytesIO(archive.read(xml_name))).getroot()
    sections = []
    for norm in root.iter("norm"):
        designation = " ".join((norm.findtext("metadaten/enbez") or "").split())
        title = " ".join((norm.findtext("metadaten/titel") or "").split())
        if not designation or designation == "Inhaltsübersicht":
            continue  # structural headings and the table of contents are not Provisions
        content = norm.find("textdaten/text/Content")
        body = "\n".join(_lines(content)) if content is not None else ""
        if not body:
            continue  # repealed ("weggefallen") Provisions have no text
        sections.append(
            Section(
                label=designation,
                title=title,
                target=_gii_target(designation),
                text=_tidy(f"{designation} {title}\n{body}"),
            )
        )
    return sections


# --- PDFs: BaFin guidance and circulars ----------------------------------------------------


def _shape(line: str) -> str:
    return re.sub(r"\d+", "#", line.strip())


def _pdf_pages(path: Path) -> list[list[str]]:
    """Page lines without running headers and footers: a line among the first or last two of
    a page whose shape (ignoring numbers) recurs there on at least half of the pages."""
    pages = [
        [line.strip() for line in (page.extract_text() or "").splitlines() if line.strip()]
        for page in PdfReader(path).pages
    ]

    def edges(lines: list[str]) -> set[int]:
        return {i for i in (0, 1, len(lines) - 2, len(lines) - 1) if 0 <= i < len(lines)}

    repeated: set[str] = set()
    if len(pages) >= 4:
        counts: dict[str, int] = {}
        for lines in pages:
            for shape in {_shape(lines[i]) for i in edges(lines)}:
                counts[shape] = counts.get(shape, 0) + 1
        repeated = {shape for shape, n in counts.items() if n >= len(pages) / 2}
    return [
        [
            line
            for i, line in enumerate(lines)
            if not (i in edges(lines) and _shape(line) in repeated)
        ]
        for lines in pages
    ]


_TOC_LINE = re.compile(r"\s\d{1,3}$")  # "5.7 Zeitpunkt der Identifizierung 67"
_HEADING = re.compile(
    r"^(?P<number>(?:AT|BT|BTO|BTR)\s?\d+(?:\.\d+)*|\d{1,2}(?:\.\d{1,2}){0,4})\.?\s+"
    r"(?P<title>[A-ZÄÖÜ][^\n]{2,110})$"
)


def _is_toc(lines: list[str]) -> bool:
    return len(lines) >= 5 and sum(bool(_TOC_LINE.search(x)) for x in lines) / len(lines) > 0.5


def load_pdf(path: Path) -> list[Section]:
    """PDFs: one Section per numbered heading ("5.7 …", "AT 4.4.2 …"). Pages that are mostly
    table of contents are skipped, and their entries decide which numbered lines count as
    headings, so numbered list items ("1. …") are not mistaken for sections. Without a table
    of contents, only multi-level numbers ("5.7") and MaRisk-style modules ("AT 4.4.2") count.
    Each Section links to the page where it starts."""
    pages = _pdf_pages(path)
    toc_pages = {i for i, lines in enumerate(pages) if _is_toc(lines)}
    # Section numbers in table-of-contents order; headings must follow this order.
    toc = list(
        dict.fromkeys(
            heading["number"]
            for i in sorted(toc_pages)
            for line in pages[i]
            if (heading := _HEADING.match(_TOC_LINE.sub("", line)))
        )
    )
    position = -1  # index in `toc` of the last heading found
    # Where each numbered line occurs (as a running line index), to judge skipped headings.
    occurrences: dict[str, list[int]] = {}
    index = 0
    for i, lines in enumerate(pages):
        for line in lines:
            if i not in toc_pages and (heading := _HEADING.match(line)):
                occurrences.setdefault(heading["number"], []).append(index)
            index += 1
    here = -1  # running line index of the line being read

    used: set[str] = set()

    def is_heading(number: str) -> bool:
        nonlocal position
        if number in used:
            return False  # each section number heads exactly one section; later hits are list items
        if toc:
            # The next entry, or the one after it if a heading was missed; anything further
            # ahead is a numbered list item that happens to share a section number.
            if position + 1 < len(toc) and toc[position + 1] == number:
                position += 1
                return True
            skipped = toc[position + 1] if position + 1 < len(toc) else None
            if (
                position + 2 < len(toc)
                and toc[position + 2] == number
                and not any(i > here for i in occurrences.get(skipped, []))
            ):
                position += 2  # the skipped heading never appears, e.g. split over two lines
                return True
            return False
        return "." in number or number[:2] in ("AT", "BT")

    sections: list[Section] = []
    label, title, page_of_section, buffer = "", "", 1, []

    def flush() -> None:
        # Words hyphenated at a line end ("kön-\nnen") are joined again.
        text = _tidy(re.sub(r"(\w)-\n([a-zäöüß])", r"\1\2", "\n".join(buffer)))
        if text:
            shown = label or f"S. {page_of_section}"
            sections.append(Section(shown, title, f"#page={page_of_section}", text))
        buffer.clear()

    for page_number, lines in enumerate(pages, start=1):
        if page_number - 1 in toc_pages:
            here += len(lines)
            continue
        for line in lines:
            here += 1
            heading = _HEADING.match(line)
            if heading and not _TOC_LINE.search(line) and is_heading(heading["number"]):
                flush()
                label, title = heading["number"], heading["title"].strip()
                used.add(label)
                page_of_section = page_number
            elif not buffer and not label:
                page_of_section = page_number
            buffer.append(line)
    flush()
    return sections


# --- BaFin circulars published as web pages ------------------------------------------------

_NUMBERED = re.compile(r"^(?P<number>\d{1,2}(?:\.\d{1,2}){0,4})\.?\s+(?P<title>\S.*)$")
_MARK = "\u2063HEADING\u2063"


def load_web_html(path: Path) -> list[Section]:
    """BaFin web pages: one Section per numbered heading ("9.1.1 Allgemeines"). Headings carry
    no anchors, so each Section links with a text fragment that scrolls to its heading."""
    soup = BeautifulSoup(path.read_bytes(), "lxml")
    main = soup.find("main") or soup.body
    for noise in main.find_all(["nav", "form", "aside"]):
        noise.decompose()
    toc = main.find(id="headerToc")
    if toc is not None:
        container = toc.find_parent(["div", "section"]) or toc
        container.decompose()
    headings = []
    for heading in main.find_all(["h2", "h3", "h4", "h5"]):
        text = " ".join(heading.get_text(" ").split())
        if _NUMBERED.match(text):
            headings.append(text)
            heading.replace_with(f"{_MARK}{len(headings) - 1}{_MARK}")
    _prepare(main)
    parts = main.get_text().split(_MARK)
    sections = []
    for index, body in zip(parts[1::2], parts[2::2]):
        heading = headings[int(index)]
        match = _NUMBERED.match(heading)
        sections.append(
            Section(
                label=match["number"],
                title=match["title"],
                target="#:~:text=" + quote(heading),
                text=_tidy(f"{heading}\n{body}"),
            )
        )
    return sections


LOADERS = {"html": load_html, "gii_xml": load_gii_xml, "pdf": load_pdf, "web_html": load_web_html}


def link_for(source: Source, target: str) -> str:
    """The address that opens one Provision: page links replace the act's index page,
    anchors and PDF pages are appended to the reading address."""
    if not target:
        return source.link
    if target.startswith("#"):
        base = source.link if source.format != "pdf" else source.url
        return base.split("#")[0] + target
    return source.link.rstrip("/") + "/" + target


def load(source: Source, raw_dir: Path) -> LoadedSource:
    path = raw_dir / source.id / FILE_NAMES[source.format]
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing; run: uv run compliance-advisor-fetch --source {source.id}"
        )
    meta_path = path.parent / "meta.json"
    fetched = json.loads(meta_path.read_text())["fetched_at"][:10] if meta_path.exists() else ""
    metadata = {
        "source_id": source.id,
        "source_title": source.title,
        "short_title": source.short_title,
        "regime": source.regime,
        "layer": source.layer,
        "issuer": source.issuer,
        "language": source.language,
        "url": source.link,
        "legal_status": source.legal_status,
        "version": source.version,
        "as_of": fetched,
    }
    return LoadedSource(sections=LOADERS[source.format](path), metadata=metadata)
