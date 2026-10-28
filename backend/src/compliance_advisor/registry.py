"""The Source Registry: reads and validates config/sources.yaml."""

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ValidationError

Regime = Literal["dora", "aml", "payments", "insurance", "banking", "digital"]
Layer = Literal["eu_level_1", "eu_level_2", "eu_level_3", "national_law", "supervisory_practice"]
Language = Literal["en", "de"]
Format = Literal["html", "gii_xml", "pdf", "web_html"]
LegalStatus = Literal["in_force", "applies_later", "pending_proposal"]


class Milestone(BaseModel, extra="forbid"):
    date: date
    what: str


class Source(BaseModel, extra="forbid"):
    id: str
    title: str
    short_title: str
    regime: Regime
    layer: Layer
    issuer: str
    language: Language
    format: Format
    url: str  # where the file is downloaded from
    display_url: str = ""  # the page a person opens to read the Source; defaults to url
    legal_status: LegalStatus = "in_force"
    version: str = ""  # which text: "OJ L 333, 27.12.2022" or "last amended 29.6.2026"
    milestones: list[Milestone] = []
    notes: str = ""

    @property
    def link(self) -> str:
        return self.display_url or self.url


def load_sources(path: Path) -> list[Source]:
    """The Source Registry, parsed once per file version (it is read on every question)."""
    return _load_sources(path, path.stat().st_mtime_ns)


@lru_cache(maxsize=4)
def _load_sources(path: Path, version: int) -> list[Source]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("sources") or []
    sources, problems = [], []
    for i, entry in enumerate(entries):
        try:
            sources.append(Source.model_validate(entry))
        except ValidationError as e:
            name = (
                entry.get("id", f"entry {i + 1}") if isinstance(entry, dict) else f"entry {i + 1}"
            )
            for err in e.errors():
                field = ".".join(str(x) for x in err["loc"])
                problems.append(f"{name}: {field}: {err['msg']}")
    ids = [s.id for s in sources]
    problems += [f"{d}: duplicate id" for d in sorted({i for i in ids if ids.count(i) > 1})]
    if problems:
        raise SystemExit(f"{path} has problems:\n  " + "\n  ".join(problems))
    return sources


def select(sources: list[Source], ids: list[str] | None) -> list[Source]:
    if not ids:
        return sources
    by_id = {s.id: s for s in sources}
    unknown = [i for i in ids if i not in by_id]
    if unknown:
        raise SystemExit(f"Unknown source id(s): {', '.join(unknown)}. Known: {', '.join(by_id)}")
    return [by_id[i] for i in ids]
