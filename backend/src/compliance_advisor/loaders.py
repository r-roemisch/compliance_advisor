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


def load_html(path: Path) -> str:
    """EU acts as XHTML from the EU Publications Office: every block element becomes a line."""
    soup = BeautifulSoup(path.read_bytes(), "lxml")
    for tag in soup(["script", "style", "head", "nav"]):
        tag.decompose()
    return _tidy(soup.get_text("\n"))


def _words(element) -> str:
    return " ".join(" ".join(element.itertext()).split())


def _lines(content) -> list[str]:
    """Paragraphs stay paragraphs; in numbered lists each item gets its own line ("1. text")."""
    lines = []
    for child in content:
        if child.tag == "DL":
            for dt in child.iterfind("DT"):
                dd = dt.getnext()
                item = _words(dd) if dd is not None and dd.tag == "DD" else ""
                lines.append(f"{_words(dt)} {item}".strip())
        else:
            lines.append(_words(child))
    return [line for line in lines if line]


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


def load_pdf(path: Path) -> str:
    """PDF documents, for example BaFin guidance, read page by page."""
    reader = PdfReader(path)
    return _tidy("\n\n".join(page.extract_text() or "" for page in reader.pages))


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
