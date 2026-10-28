"""compliance-advisor-fetch: downloads Sources into data/raw/<id>/.

Downloads only what you name (--source) or everything (--all), skips files already there
unless --refresh is given, identifies itself honestly, and respects robots.txt.
"""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from .registry import Source, load_sources, select
from .settings import get_settings

USER_AGENT = "ComplianceAdvisor/0.1 (Turing College student project; non-commercial)"

FILE_NAMES = {
    "html": "source.html",
    "gii_xml": "source.zip",
    "pdf": "source.pdf",
    "web_html": "source.html",
}
ACCEPT = {
    "html": "application/xhtml+xml, text/html;q=0.9",
    "gii_xml": "application/zip",
    "pdf": "application/pdf",
    "web_html": "text/html",
}
# The EU Publications Office picks the language from ISO 639-2 codes (eng, deu).
ACCEPT_LANGUAGE = {"en": "eng, en;q=0.9", "de": "deu, de;q=0.9"}


class FetchRefused(RuntimeError):
    pass


def robots_allows(client: httpx.Client, url: str, cache: dict[str, RobotFileParser | bool]) -> bool:
    """RFC 9309: 200 -> obey the rules; 401/403 -> refused; other 4xx -> allowed; 5xx -> stop."""
    parts = urlsplit(url)
    host = f"{parts.scheme}://{parts.netloc}"
    if host not in cache:
        response = client.get(f"{host}/robots.txt")
        if response.status_code == 200:
            parser = RobotFileParser()
            parser.parse(response.text.splitlines())
            cache[host] = parser
        elif response.status_code in (401, 403):
            cache[host] = False
        elif response.status_code < 500:
            cache[host] = True
        else:
            raise FetchRefused(
                f"{host}/robots.txt answered {response.status_code}; try again later"
            )
    rule = cache[host]
    return rule if isinstance(rule, bool) else rule.can_fetch(USER_AGENT, url)


def check_content(source: Source, body: bytes) -> None:
    if not body:
        raise FetchRefused("the server returned an empty body")
    if source.format == "pdf" and not body.startswith(b"%PDF"):
        raise FetchRefused("expected a PDF, got something else")
    if source.format == "gii_xml" and not body.startswith(b"PK"):
        raise FetchRefused("expected a zip file, got something else")
    if source.format in ("html", "web_html") and b"<" not in body[:2000]:
        raise FetchRefused("expected HTML, got something else")


def download(client: httpx.Client, source: Source, robots_cache: dict) -> tuple[bytes, dict]:
    """Downloads a Source and returns its content and meta record without writing anything."""
    if not robots_allows(client, source.url, robots_cache):
        raise FetchRefused("robots.txt disallows automated access to this address")
    response = client.get(
        source.url,
        headers={
            "Accept": ACCEPT[source.format],
            "Accept-Language": ACCEPT_LANGUAGE[source.language],
        },
    )
    if response.status_code != 200:
        raise FetchRefused(f"the server answered {response.status_code}")
    check_content(source, response.content)
    meta = {
        "id": source.id,
        "url": source.url,
        "final_url": str(response.url),
        "content_type": response.headers.get("content-type", ""),
        "bytes": len(response.content),
        "sha256": hashlib.sha256(response.content).hexdigest(),
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    return response.content, meta


def fetch_one(client: httpx.Client, source: Source, refresh: bool, robots_cache: dict) -> str:
    target_dir = get_settings().raw_dir / source.id
    target = target_dir / FILE_NAMES[source.format]
    if target.exists() and not refresh:
        return f"skipped, already there ({target.stat().st_size:,} bytes); use --refresh to download again"
    content, meta = download(client, source, robots_cache)
    target_dir.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    save_meta(target_dir, meta)
    return f"saved {target.relative_to(get_settings().data_dir.parent)} ({len(content):,} bytes)"


def save_meta(target_dir: Path, meta: dict, text_sha256: str | None = None) -> None:
    """Writes meta.json, keeping the text fingerprint an earlier ingest or Update Run recorded
    unless a new one is given: a fresh download must not make a Source look changed."""
    path = target_dir / "meta.json"
    if text_sha256 is None:
        try:
            text_sha256 = json.loads(path.read_text()).get("text_sha256")
        except (OSError, ValueError):
            text_sha256 = None
    if text_sha256:
        meta = {**meta, "text_sha256": text_sha256}
    target_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Sources into data/raw/<id>/.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--source", action="append", metavar="ID", help="a Source id; repeatable")
    group.add_argument("--all", action="store_true", help="every Source in the registry")
    parser.add_argument("--refresh", action="store_true", help="download again even if present")
    args = parser.parse_args()

    settings = get_settings()
    sources = select(load_sources(settings.sources_file), None if args.all else args.source)
    failures = 0
    robots_cache: dict = {}
    with httpx.Client(
        headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=180.0
    ) as client:
        for source in sources:
            try:
                print(f"{source.id}: {fetch_one(client, source, args.refresh, robots_cache)}")
            except (FetchRefused, httpx.HTTPError) as e:
                failures += 1
                print(f"{source.id}: NOT downloaded: {e}")
    raise SystemExit(1 if failures else 0)
