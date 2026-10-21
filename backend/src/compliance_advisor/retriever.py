"""Retriever: question in, the most similar Passages out (cosine similarity in pgvector)."""

from dataclasses import dataclass

from langchain_core.documents import Document
from langchain_postgres import PGVector


@dataclass
class RetrievedPassage:
    document: Document
    score: float  # cosine similarity, 1.0 = same direction


class Retriever:
    def __init__(self, store: PGVector):
        self.store = store

    def retrieve(self, question: str, k: int) -> list[RetrievedPassage]:
        hits = self.store.similarity_search_with_score(question, k=k)
        # pgvector returns the cosine distance; similarity = 1 - distance.
        return [RetrievedPassage(doc, round(1.0 - distance, 4)) for doc, distance in hits]
