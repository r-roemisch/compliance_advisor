"""The Corpus: its Sources with legal status and Passage counts, their Milestones, and whether the
database that holds it is reachable."""

import json
from datetime import date

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ...answer import DatabaseError
from ...db import engine
from ...profile import FirmProfile
from ...prompt import DISCLAIMER
from ...registry import load_sources
from ...schemas import SourceOut, SourcesResponse, TimelineRequest
from ...settings import get_settings
from ...tools import ProvisionLinks, check_applicability, compliance_timeline

router = APIRouter()


def passage_counts() -> dict[str, int]:
    query = text(
        "select e.cmetadata->>'source_id', count(*) from langchain_pg_embedding e "
        "join langchain_pg_collection c on c.uuid = e.collection_id "
        "where c.name = :collection group by 1"
    )
    try:
        with engine().connect() as connection:
            rows = connection.execute(query, {"collection": get_settings().collection})
            return {source_id: count for source_id, count in rows}
    except SQLAlchemyError as e:
        if "does not exist" in str(e):  # nothing ingested yet
            return {}
        raise DatabaseError("the database is not reachable") from e


def fetched_on(raw_dir, source_id: str) -> str:
    """The date the app's copy of a Source was downloaded, from data/raw/<id>/meta.json."""
    meta = raw_dir / source_id / "meta.json"
    try:
        return json.loads(meta.read_text())["fetched_at"][:10]
    except (OSError, ValueError, KeyError):
        return ""


def milestones(profile: FirmProfile | None, upcoming_only: bool) -> dict:
    """Milestones of all Sources, or of those the Firm Profile makes applicable."""
    settings = get_settings()
    sources = load_sources(settings.sources_file)
    applicable_titles: set[str] | None = None
    if profile:
        result = check_applicability(profile, ProvisionLinks(sources))
        applicable_titles = {
            title
            for f in result.findings
            if f.applies in ("yes", "later", "check")
            for title in f.sources
        }
        sources = [s for s in sources if s.short_title in applicable_titles]
    result = compliance_timeline(sources, date.today(), None, upcoming_only)
    return {
        "today": result.today,
        "entries": [e.model_dump() for e in result.entries],
        "filtered": profile is not None,
    }


@router.post("/api/timeline")
def timeline(request: TimelineRequest) -> dict:
    """Milestones of all Sources, or of those the Firm Profile makes applicable."""
    return milestones(request.profile, request.upcoming_only)


@router.get("/api/sources", response_model=SourcesResponse)
def sources() -> SourcesResponse:
    settings = get_settings()
    counts = passage_counts()
    return SourcesResponse(
        sources=[
            SourceOut(
                **s.model_dump(
                    include={
                        "id",
                        "title",
                        "short_title",
                        "regime",
                        "layer",
                        "issuer",
                        "language",
                        "legal_status",
                        "version",
                    }
                ),
                milestones=[m.model_dump(mode="json") for m in s.milestones],
                as_of=fetched_on(settings.raw_dir, s.id),
                url=s.link,
                passages=counts.get(s.id, 0),
            )
            for s in load_sources(settings.sources_file)
        ],
        disclaimer=DISCLAIMER,
    )


@router.get("/api/health")
def health() -> JSONResponse:
    try:
        with engine().connect() as connection:
            connection.execute(text("select 1"))
        return JSONResponse({"status": "ok", "database": "reachable"})
    except SQLAlchemyError:
        return JSONResponse({"status": "degraded", "database": "unreachable"}, status_code=503)
