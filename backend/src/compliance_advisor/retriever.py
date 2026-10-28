"""Retriever: question in, the most relevant Passages out. Two Search Strategies: vector search
(cosine similarity in pgvector) and hybrid search (vector search merged with keyword search)."""

import re
from dataclasses import dataclass

from langchain_core.documents import Document
from langchain_postgres import PGVector
from sqlalchemy import text

SEARCH_STRATEGIES = ("vector", "hybrid")
RRF_K = 60  # the usual constant of reciprocal rank fusion; damps the weight of the very top ranks

# The question's words are joined with OR ("|"), so a Passage needs only some of them; ts_rank
# with normalisation 1 keeps long Passages from winning just by holding more words. The question
# is stemmed in both languages, and each Passage is matched in its own.
KEYWORD_SQL = text(
    """
    WITH q AS (
        SELECT to_tsquery('german', replace(plainto_tsquery('german', :question)::text, ' & ', ' | ')) AS de,
               to_tsquery('english', replace(plainto_tsquery('english', :question)::text, ' & ', ' | ')) AS en
    )
    SELECT e.document, e.cmetadata, e.embedding <=> CAST(:vector AS vector) AS distance
    FROM langchain_pg_embedding e, q
    WHERE e.collection_id = :collection
      AND (CAST(:only AS text[]) IS NULL OR e.cmetadata->>'passage_id' = ANY(CAST(:only AS text[])))
      AND ((e.cmetadata->>'language' = 'de' AND e.keywords @@ q.de)
        OR (e.cmetadata->>'language' <> 'de' AND e.keywords @@ q.en))
    ORDER BY ts_rank(e.keywords, CASE WHEN e.cmetadata->>'language' = 'de' THEN q.de ELSE q.en END, 1) DESC
    LIMIT :k
    """
)


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


def merge_ranked(
    *rankings: list[RetrievedPassage], weights: tuple[float, ...] | None = None
) -> list[RetrievedPassage]:
    """Reciprocal rank fusion: every list adds weight / (60 + rank) for each Passage it holds, so
    a Passage that both searches found rises to the top. The shown score stays the cosine
    similarity, because keyword ranks and cosine scores are not on one scale."""
    weights = weights or (1.0,) * len(rankings)
    fused: dict[str, float] = {}
    first: dict[str, RetrievedPassage] = {}
    for ranking, weight in zip(rankings, weights, strict=True):
        for rank, hit in enumerate(ranking, start=1):
            passage_id = hit.document.metadata["passage_id"]
            fused[passage_id] = fused.get(passage_id, 0.0) + weight / (RRF_K + rank)
            first.setdefault(passage_id, hit)
    return sorted(first.values(), key=lambda hit: -fused[hit.document.metadata["passage_id"]])


class Retriever:
    """Top-k by cosine similarity, or with hybrid search the vector and keyword results merged,
    with at most `max_per_source` Passages from one Source, so one closely related act cannot
    fill every slot (0 switches the cap off). Provisions the question names explicitly
    ("§ 25a KWG") are looked up directly and come first."""

    def __init__(
        self,
        store: PGVector,
        max_per_source: int = 0,
        candidates: int = 24,
        short_titles: list[str] | None = None,
        keyword_scope: str = "corpus",
        keyword_weight: float = 1.0,
    ):
        """For hybrid search, `keyword_scope` "corpus" lets keyword search bring in any Passage,
        "candidates" only re-sorts the Passages vector search found; `keyword_weight` is the
        weight of the keyword ranks against the vector ranks."""
        self.store = store
        self.max_per_source = max_per_source
        self.candidates = candidates
        self.short_titles = short_titles or []
        self.keyword_scope = keyword_scope
        self.keyword_weight = keyword_weight

    def _search(
        self, vector: list[float], k: int, filter: dict | None = None
    ) -> list[RetrievedPassage]:
        hits = self.store.similarity_search_with_score_by_vector(vector, k=k, filter=filter)
        # pgvector returns the cosine distance; similarity = 1 - distance.
        return [RetrievedPassage(doc, round(1.0 - distance, 4)) for doc, distance in hits]

    def _keyword_search(
        self, question: str, vector: list[float], k: int, only: list[str] | None = None
    ) -> list[RetrievedPassage]:
        with self.store.session_maker() as session:
            collection = self.store.get_collection(session)
            if collection is None:
                return []
            rows = session.execute(
                KEYWORD_SQL,
                {
                    "question": question,
                    "vector": str(vector),
                    "collection": collection.uuid,
                    "k": k,
                    "only": only,
                },
            ).all()
        return [
            RetrievedPassage(
                Document(page_content=document, metadata=metadata), round(1.0 - distance, 4)
            )
            for document, metadata, distance in rows
        ]

    def retrieve(self, question: str, k: int, strategy: str = "vector") -> list[RetrievedPassage]:
        return self.search(question, k, strategy)[0]

    def search(
        self, question: str, k: int, strategy: str = "vector"
    ) -> tuple[list[RetrievedPassage], dict]:
        """The Passages, and the Answer Trace of how they were found (schemas.Trace)."""
        if strategy not in SEARCH_STRATEGIES:
            raise ValueError(f"unknown search strategy {strategy!r}")
        vector = self.store.embeddings.embed_query(question)  # once, for every search below
        labels = named_provisions(question, self.short_titles)[:3]
        named: list[RetrievedPassage] = []
        for label in labels:
            named += self._search(vector, 2, filter={"provision": {"$eq": label}})
        hybrid = strategy == "hybrid"
        fetch = max(k, self.candidates) if self.max_per_source or hybrid else k
        by_vector = self._search(vector, fetch)
        ranked, keyword = by_vector, []
        if hybrid:
            only = None
            if self.keyword_scope == "candidates":
                only = [hit.document.metadata["passage_id"] for hit in by_vector]
            keyword = self._keyword_search(question, vector, fetch, only)
            ranked = merge_ranked(by_vector, keyword, weights=(1.0, self.keyword_weight))
        capped = cap_per_source(ranked, k, self.max_per_source)
        kept = named[: k // 2]  # named Provisions take at most half the slots
        seen = {hit.document.metadata["passage_id"] for hit in kept}
        rest = [hit for hit in capped if hit.document.metadata["passage_id"] not in seen]
        final = (kept + rest)[:k]

        def ids(hits: list[RetrievedPassage]) -> list[str]:
            return [hit.document.metadata["passage_id"] for hit in hits]

        in_vector, in_keyword = set(ids(by_vector)), set(ids(keyword))
        trace = {
            "strategy": strategy,
            "named": labels,
            "named_hits": [_trace_hit(h) for h in named],
            "vector": [_trace_hit(h) for h in by_vector],
            "keyword": [_trace_hit(h, rank=n) for n, h in enumerate(keyword, start=1)],
            "merged": ids(ranked) if hybrid else [],
            "max_per_source": self.max_per_source,
            "capped_out": sum(1 for h in ranked[:k] if h not in capped),
            "found_by": {
                pid: (
                    "named"
                    if pid in seen
                    else "both"
                    if pid in in_vector and pid in in_keyword
                    else "keyword"
                    if pid in in_keyword
                    else "vector"
                )
                for pid in ids(final)
            },
        }
        return final, trace


def _trace_hit(hit: RetrievedPassage, rank: int | None = None) -> dict:
    meta = hit.document.metadata
    return {
        "passage_id": meta["passage_id"],
        "provision": meta.get("provision", ""),
        "short_title": meta.get("short_title", ""),
        "score": hit.score,
        "rank": rank,
    }


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
    position = {id(hit): n for n, hit in enumerate(ranked)}
    return sorted(chosen, key=lambda hit: position[id(hit)])  # merged order, not only by score
