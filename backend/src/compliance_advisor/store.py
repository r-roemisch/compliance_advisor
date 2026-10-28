"""The vector store: Postgres with pgvector, one collection per embedding model, plus a keyword
index on the same rows for hybrid search."""

import hashlib

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_postgres import PGVector
from sqlalchemy import delete, text
from sqlalchemy.dialects.postgresql import insert

from .settings import Settings

# Keyword search for hybrid search: Postgres full-text search with each Passage's own language,
# so German words are reduced to their stems ("Meldefristen" -> "meldefrist") and English ones too.
# A generated column keeps the words in step with the text; nothing needs re-embedding.
KEYWORDS_DDL = [
    """ALTER TABLE langchain_pg_embedding ADD COLUMN IF NOT EXISTS keywords tsvector
       GENERATED ALWAYS AS (
           CASE WHEN cmetadata->>'language' = 'de' THEN to_tsvector('german', document)
                ELSE to_tsvector('english', document) END
       ) STORED""",
    """CREATE INDEX IF NOT EXISTS langchain_pg_embedding_keywords
       ON langchain_pg_embedding USING gin (keywords)""",
]


def get_store(settings: Settings, embeddings: Embeddings) -> PGVector:
    store = PGVector(
        embeddings=embeddings,
        collection_name=settings.collection,  # one per embedding model and chunker
        connection=settings.database_url,
        use_jsonb=True,
    )
    with store.session_maker() as session:
        for statement in KEYWORDS_DDL:
            session.execute(text(statement))
        session.commit()
    return store


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


def replace_source(
    store: PGVector, source_id: str, passages: list[Document], vectors: list[list[float]]
) -> int:
    """Removes a Source's old Passages and stores the new ones in one transaction, so a failure
    half-way leaves the old ones in place. Returns how many were removed."""
    table = store.EmbeddingStore
    with store.session_maker() as session:
        collection = store.get_collection(session)
        if collection is None:
            raise ValueError(f"collection {store.collection_name!r} not found")
        removed = session.execute(
            delete(table).where(
                table.collection_id == collection.uuid,
                table.cmetadata["source_id"].astext == source_id,
            )
        ).rowcount
        rows = [
            {
                "id": row_id(store.collection_name, p.metadata["passage_id"]),
                "collection_id": collection.uuid,
                "embedding": vector,
                "document": p.page_content,
                "cmetadata": p.metadata,
            }
            for p, vector in zip(passages, vectors, strict=True)
        ]
        if rows:
            statement = insert(table).values(rows)
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        "embedding": statement.excluded.embedding,
                        "document": statement.excluded.document,
                        "cmetadata": statement.excluded.cmetadata,
                    },
                )
            )
        session.commit()
    return removed or 0


def add_passages(store: PGVector, passages: list[Document], vectors: list[list[float]]) -> None:
    """Stores Passages with embeddings computed beforehand."""
    store.add_embeddings(
        texts=[p.page_content for p in passages],
        embeddings=vectors,
        metadatas=[p.metadata for p in passages],
        ids=[row_id(store.collection_name, p.metadata["passage_id"]) for p in passages],
    )
