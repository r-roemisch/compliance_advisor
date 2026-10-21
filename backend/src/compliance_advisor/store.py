"""The vector store: Postgres with pgvector, one collection per embedding model."""

import hashlib

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_postgres import PGVector
from sqlalchemy import delete

from .settings import Settings


def get_store(settings: Settings, embeddings: Embeddings) -> PGVector:
    return PGVector(
        embeddings=embeddings,
        collection_name=settings.embedding_model,  # a new model gets its own collection
        connection=settings.database_url,
        use_jsonb=True,
    )


def row_id(collection: str, passage_id: str) -> str:
    """Row ids must be unique across collections; the Passage id stays in the metadata."""
    return hashlib.sha256(f"{collection}\x00{passage_id}".encode()).hexdigest()[:32]


def delete_source(store: PGVector, source_id: str) -> int:
    """Removes every Passage of one Source from this store's collection; returns how many."""
    table = store.EmbeddingStore
    with store.session_maker() as session:
        collection = store.get_collection(session)
        if collection is None:
            return 0
        result = session.execute(
            delete(table).where(
                table.collection_id == collection.uuid,
                table.cmetadata["source_id"].astext == source_id,
            )
        )
        session.commit()
        return result.rowcount or 0


def add_passages(store: PGVector, passages: list[Document], vectors: list[list[float]]) -> None:
    """Stores Passages with embeddings computed beforehand."""
    store.add_embeddings(
        texts=[p.page_content for p in passages],
        embeddings=vectors,
        metadatas=[p.metadata for p in passages],
        ids=[row_id(store.collection_name, p.metadata["passage_id"]) for p in passages],
    )
