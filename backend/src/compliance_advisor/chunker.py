"""Chunker: cuts a loaded Source into Passages of fixed size with overlap."""

import hashlib

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .loaders import LoadedSource


def passage_id(source_id: str, position: int, text: str) -> str:
    """Same Source, position and text always give the same id, so re-runs never duplicate."""
    digest = hashlib.sha256(f"{source_id}\x00{position}\x00{text}".encode()).hexdigest()
    return f"{source_id}:{position}:{digest[:12]}"


def chunk(loaded: LoadedSource, chunk_size: int, chunk_overlap: int) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    passages = []
    for position, text in enumerate(splitter.split_text(loaded.text)):
        metadata = {
            **loaded.metadata,
            "position": position,
            "passage_id": passage_id(loaded.metadata["source_id"], position, text),
        }
        passages.append(Document(page_content=text, metadata=metadata))
    return passages
