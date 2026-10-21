"""Loaders: turn one downloaded file into plain text plus the Source's metadata.

One function per file format, chosen by the `format` field of the registry entry.
"""

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup
from lxml import etree
from pypdf import PdfReader

from .fetch import FILE_NAMES
from .registry import Source


@dataclass
class LoadedSource:
    text: str
    metadata: dict[str, str]


def _tidy(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


_BLOCKS = ["p", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br", "table"]


def load_html(path: Path) -> str:
    """EU acts as XHTML from the EU Publications Office.

    Block elements (paragraphs, table rows) become lines; inline elements such as footnote
    markers stay inside their sentence; table cells in a row are joined with a space, so a
    recital number stays next to its text.
    """
    soup = BeautifulSoup(path.read_bytes(), "xml")
    for tag in soup(["script", "style", "head", "nav"]):
        tag.decompose()
    # The file's own indentation and line breaks between tags are not part of the text.
    for string in soup.find_all(string=True):
        string.replace_with(re.sub(r"\s+", " ", string))
    for cell in soup.find_all(["td", "th"]):
        cell.append(" ")
    for block in soup.find_all(_BLOCKS):
        inside_cell = block.name != "tr" and block.find_parent(["td", "th"]) is not None
        block.append(" " if inside_cell else "\n")
    return _tidy(soup.get_text())


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


def load_gii_xml(path: Path) -> str:
    """German acts from gesetze-im-internet.de: a zip with one XML file, one <norm> per paragraph."""
    with zipfile.ZipFile(path) as archive:
        xml_name = next(n for n in archive.namelist() if n.lower().endswith(".xml"))
        root = etree.parse(io.BytesIO(archive.read(xml_name))).getroot()
    blocks = []
    for norm in root.iter("norm"):
        heading = " ".join(
            t.strip()
            for t in (norm.findtext("metadaten/enbez"), norm.findtext("metadaten/titel"))
            if t and t.strip()
        )
        content = norm.find("textdaten/text/Content")
        body = "\n".join(_lines(content)) if content is not None else ""
        if heading or body:
            blocks.append(f"{heading}\n{body}".strip())
    return _tidy("\n\n".join(blocks))


def _shape(line: str) -> str:
    return re.sub(r"\d+", "#", line.strip())


def load_pdf(path: Path) -> str:
    """PDF documents, for example BaFin guidance, read page by page.

    Running headers and footers are dropped: a line among the first or last two lines of a
    page whose shape (ignoring numbers) recurs there on at least half of the pages, such as
    "... Stand: Juli 2025 Seite 3 von 105". Lines in the middle of a page are always kept.
    """
    pages = [
        [line for line in (page.extract_text() or "").splitlines() if line.strip()]
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
    kept = [
        "\n".join(
            line
            for i, line in enumerate(lines)
            if not (i in edges(lines) and _shape(line) in repeated)
        )
        for lines in pages
    ]
    return _tidy("\n\n".join(kept))


LOADERS = {"html": load_html, "gii_xml": load_gii_xml, "pdf": load_pdf}


def load(source: Source, raw_dir: Path) -> LoadedSource:
    path = raw_dir / source.id / FILE_NAMES[source.format]
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing; run: uv run compliance-advisor-fetch --source {source.id}"
        )
    metadata = {
        "source_id": source.id,
        "source_title": source.title,
        "short_title": source.short_title,
        "regime": source.regime,
        "layer": source.layer,
        "issuer": source.issuer,
        "language": source.language,
        "url": source.link,
    }
    return LoadedSource(text=LOADERS[source.format](path), metadata=metadata)
