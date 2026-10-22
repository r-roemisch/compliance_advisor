"""Chunkers: cut a loaded Source into Passages.

- provision: one Passage per Provision (article, recital, annex, §, guideline section);
  long Provisions are split into parts that all keep the Provision's label and link.
- fixed: the naive baseline, fixed-size pieces of the flattened text with overlap.
"""

import hashlib

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .loaders import LoadedSource, link_for
from .registry import Source
from .settings import Settings


def passage_id(source_id: str, position: int, text: str) -> str:
    """Same Source, position and text always give the same id, so re-runs never duplicate."""
    digest = hashlib.sha256(f"{source_id}\x00{position}\x00{text}".encode()).hexdigest()
    return f"{source_id}:{position}:{digest[:12]}"


def _passage(loaded: LoadedSource, position: int, text: str, **extra) -> Document:
    metadata = {
        **loaded.metadata,
        **extra,
        "position": position,
        "passage_id": passage_id(loaded.metadata["source_id"], position, text),
    }
    return Document(page_content=text, metadata=metadata)


def chunk_fixed(loaded: LoadedSource, chunk_size: int, chunk_overlap: int) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return [
        _passage(loaded, position, text)
        for position, text in enumerate(splitter.split_text(loaded.text))
    ]


def chunk_provisions(
    loaded: LoadedSource, source: Source, max_chars: int, overlap: int
) -> list[Document]:
    passages: list[Document] = []
    short = loaded.metadata["short_title"]
    for section in loaded.sections:
        provision = f"{section.label} {short}"
        header = f"{provision} – {section.title}" if section.title else provision
        extra = {
            "provision": provision,
            "provision_title": section.title,
            "link": link_for(source, section.target),
        }
        body = section.text
        if len(body) <= max_chars:
            pieces = [body]
        else:
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=max_chars - len(header) - 20, chunk_overlap=overlap
            )
            pieces = splitter.split_text(body)
        for i, piece in enumerate(pieces, start=1):
            part = f" (part {i} of {len(pieces)})" if len(pieces) > 1 else ""
            # The label leads every Passage, so a split part still says which Provision it is.
            text = f"{header}{part}\n{piece}"
            passages.append(_passage(loaded, len(passages), text, **extra))
    return passages


def chunk(loaded: LoadedSource, source: Source, settings: Settings) -> list[Document]:
    if settings.chunker == "fixed":
        return chunk_fixed(loaded, settings.chunk_size, settings.chunk_overlap)
    if settings.chunker == "provision":
        return chunk_provisions(
            loaded, source, settings.provision_max_chars, settings.provision_overlap
        )
    raise SystemExit(f"Unknown CHUNKER {settings.chunker!r}; use provision or fixed.")
