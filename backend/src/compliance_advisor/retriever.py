"""Retriever: question in, the most similar Passages out (cosine similarity in pgvector)."""

import re
from dataclasses import dataclass

from langchain_core.documents import Document
from langchain_postgres import PGVector


@dataclass
class RetrievedPassage:
    document: Document
    score: float  # cosine similarity, 1.0 = same direction


def named_provisions(question: str, short_titles: list[str]) -> list[str]:
    """Provision labels a question names explicitly, in the index's form: "§ 25a KWG",
    "Art. 6 AI Act". Paragraph and point references ("Abs. 1", "(2)") are ignored."""
    if not short_titles:
        return []
    titles = "|".join(re.escape(t) for t in sorted(short_titles, key=len, reverse=True))
    pattern = re.compile(
        r"(?P<kind>§|Art\.?|Artikel|Article)\s*(?P<number>\d+[a-z]?)"
        r"(?:\s*(?:\(\w+\))+|\s+(?:Abs\.|Absatz|para\.?|paragraph)\s*\d+)*"
        r"(?:\s+(?:of the|of|des|der|the))?\s+(?P<title>" + titles + r")\b",
        re.IGNORECASE,
    )
    by_lower = {t.lower(): t for t in short_titles}
    labels = []
    for match in pattern.finditer(question):
        kind = "§" if match["kind"] == "§" else "Art."
        label = f"{kind} {match['number']} {by_lower[match['title'].lower()]}"
        if label not in labels:
            labels.append(label)
    return labels


class Retriever:
    """Top-k by cosine similarity, with at most `max_per_source` Passages from one Source, so
    one closely related act cannot fill every slot (0 switches the cap off). Provisions the
    question names explicitly ("§ 25a KWG") are looked up directly and come first."""

    def __init__(
        self,
        store: PGVector,
        max_per_source: int = 0,
        candidates: int = 24,
        short_titles: list[str] | None = None,
    ):
        self.store = store
        self.max_per_source = max_per_source
        self.candidates = candidates
        self.short_titles = short_titles or []

    def _search(self, question: str, k: int, filter: dict | None = None) -> list[RetrievedPassage]:
        hits = self.store.similarity_search_with_score(question, k=k, filter=filter)
        # pgvector returns the cosine distance; similarity = 1 - distance.
        return [RetrievedPassage(doc, round(1.0 - distance, 4)) for doc, distance in hits]

    def retrieve(self, question: str, k: int) -> list[RetrievedPassage]:
        named: list[RetrievedPassage] = []
        for label in named_provisions(question, self.short_titles)[:3]:
            named += self._search(question, 2, filter={"provision": {"$eq": label}})
        fetch = max(k, self.candidates) if self.max_per_source else k
        ranked = cap_per_source(self._search(question, fetch), k, self.max_per_source)
        seen = {hit.document.metadata["passage_id"] for hit in named}
        rest = [hit for hit in ranked if hit.document.metadata["passage_id"] not in seen]
        return (named[: k // 2] + rest)[:k]


def cap_per_source(
    ranked: list[RetrievedPassage], k: int, max_per_source: int
) -> list[RetrievedPassage]:
    """Prefer variety: take the best Passages with at most `max_per_source` per Source. If
    that leaves slots empty (all candidates come from one or two Sources), fill them with the
    next best Passages anyway, so a question about one act still gets k Passages."""
    if not max_per_source:
        return ranked[:k]
    chosen: list[RetrievedPassage] = []
    held_back: list[RetrievedPassage] = []
    per_source: dict[str, int] = {}
    for hit in ranked:
        source = hit.document.metadata["source_id"]
        if per_source.get(source, 0) < max_per_source:
            chosen.append(hit)
            per_source[source] = per_source.get(source, 0) + 1
        else:
            held_back.append(hit)
        if len(chosen) == k:
            return chosen
    chosen += held_back[: k - len(chosen)]
    return sorted(chosen, key=lambda hit: -hit.score)
