"""The app's Rule Checks wired to the Corpus: the link of a Provision label, and the tool
factory the Answer Model and the MCP server use. Lives apart from api.py so the evaluation
scripts can import it without building the web app."""

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .db import engine
from .profile import FirmProfile
from .registry import load_sources
from .settings import get_settings
from .tools import ProvisionLinks, make_tools

_LINKS: dict[str, str] = {}  # only links that were found; cleared after an Update Run


def provision_link(label: str) -> str | None:
    """The indexed link of a Provision label, such as "AT 2.1 MaRisk" -> its PDF page."""
    if label in _LINKS:
        return _LINKS[label]
    query = text(
        "select e.cmetadata->>'link' from langchain_pg_embedding e "
        "join langchain_pg_collection c on c.uuid = e.collection_id "
        "where c.name = :collection and e.cmetadata->>'provision' = :label limit 1"
    )
    try:
        with engine().connect() as connection:
            row = connection.execute(
                query, {"collection": get_settings().collection, "label": label}
            ).first()
    except SQLAlchemyError:
        return None  # not cached: the next lookup tries again
    if row and row[0]:
        _LINKS[label] = row[0]
        return row[0]
    return None


def clear_link_cache() -> None:
    _LINKS.clear()


def tool_factory(profile: FirmProfile | None, today):
    sources = load_sources(get_settings().sources_file)
    return make_tools(profile, sources, ProvisionLinks(sources, provision_link), today)
