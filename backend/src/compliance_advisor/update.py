"""Update Runs (CONTEXT.md): check every Source in the Source Registry for a new version, load
again only the Sources whose text changed, and keep a Change Record for each change.

A run downloads each Source again and compares the file's checksum with the one in
data/raw/<id>/meta.json. A changed file is chunked and its Passage ids compared with the stored
ones (BaFin web pages differ on every download without a word of the text changing); only a
Source whose text changed is embedded again, so a night with no changes costs nothing. Runs start on a schedule inside the backend (UPDATE_RUNS=true, at
UPDATE_HOUR UTC) or when an Operator presses "check now". Changes to the Source Registry itself
stay manual.
"""

import hashlib
import json
import logging
import os
import shutil
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy import Column, DateTime, Integer, String, Table, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

from .audit import metadata
from .chunker import chunk
from .fetch import FILE_NAMES, USER_AGENT, FetchRefused, download, save_meta
from .loaders import load
from .registry import Source, load_sources
from .settings import Settings
from .store import replace_source

log = logging.getLogger("compliance_advisor.update")

update_runs = Table(
    "update_runs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("started_at", DateTime(timezone=True), nullable=False, index=True),
    Column("finished_at", DateTime(timezone=True)),
    Column("trigger", String(20), nullable=False),  # scheduled | manual
    Column("checked", Integer, nullable=False, default=0),
    Column("changed", Integer, nullable=False, default=0),
    Column("failed", Integer, nullable=False, default=0),
    Column("notes", JSONB, nullable=False, default=list),  # [{source_id, error}]
)

change_records = Table(
    "change_records",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("run_id", String(36), nullable=False, index=True),
    Column("source_id", String(80), nullable=False, index=True),
    Column("at", DateTime(timezone=True), nullable=False, index=True),
    Column("old_sha256", String(64)),
    Column("new_sha256", String(64), nullable=False),
    Column("old_fetched_at", String(40)),
    Column("passages_before", Integer, nullable=False),
    Column("passages_after", Integer, nullable=False),
    Column("added", Integer, nullable=False),  # Provisions new in the text
    Column("removed", Integer, nullable=False),  # Provisions no longer in the text
    Column("changed", Integer, nullable=False),  # Provisions whose text changed
)


def current_version(raw_dir: Path, source_id: str) -> dict:
    """Checksum, text fingerprint and download date of the app's copy of a Source, from
    meta.json. The text fingerprint (over the Passage ids) is what "changed" means; the file
    checksum alone also changes when a web page's markup differs but its text does not."""
    try:
        meta = json.loads((raw_dir / source_id / "meta.json").read_text())
        return {
            "sha256": meta.get("sha256", ""),
            "text_sha256": meta.get("text_sha256", ""),
            "fetched_at": meta.get("fetched_at", ""),
        }
    except (OSError, ValueError):
        return {"sha256": "", "text_sha256": "", "fetched_at": ""}


def text_fingerprint(passage_ids) -> str:
    return hashlib.sha256("\n".join(sorted(passage_ids)).encode()).hexdigest()


def record_text_fingerprint(raw_dir: Path, source_id: str, passage_ids) -> str:
    """Writes the text fingerprint into meta.json (ingest and Update Runs both do this)."""
    fingerprint = text_fingerprint(passage_ids)
    path = raw_dir / source_id / "meta.json"
    try:
        meta = json.loads(path.read_text())
    except (OSError, ValueError):
        return fingerprint
    meta["text_sha256"] = fingerprint
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return fingerprint


def same_text(used: dict, current: dict) -> bool:
    """Whether an answer's stored version and the current copy hold the same text: by text
    fingerprint when both have one, else by file checksum (answers stored before E8)."""
    if used.get("text_sha256") and current.get("text_sha256"):
        return used["text_sha256"] == current["text_sha256"]
    return bool(used.get("sha256")) and used["sha256"] == current.get("sha256")


def provisions_in_store(store, source_id: str) -> dict[str, set[str]]:
    """Every Provision of a Source in the vector store, with the ids of its Passages."""
    query = text(
        "select e.cmetadata->>'provision', e.cmetadata->>'passage_id' from langchain_pg_embedding e "
        "join langchain_pg_collection c on c.uuid = e.collection_id "
        "where c.name = :collection and e.cmetadata->>'source_id' = :source_id"
    )
    result: dict[str, set[str]] = {}
    with store.session_maker() as session:
        rows = session.execute(
            query, {"collection": store.collection_name, "source_id": source_id}
        ).all()
    for provision, passage_id in rows:
        result.setdefault(provision or "", set()).add(passage_id)
    return result


def diff_provisions(
    before: dict[str, set[str]], after: dict[str, set[str]]
) -> tuple[int, int, int]:
    """(added, removed, changed) Provisions. Passage ids depend on position and text, so a
    Provision whose Passage ids differ has a changed text (or moved)."""
    added = len(set(after) - set(before))
    removed = len(set(before) - set(after))
    changed = sum(1 for p in set(before) & set(after) if before[p] != after[p])
    return added, removed, changed


class UpdateStore:
    def __init__(self, engine: Engine):
        self.engine = engine
        metadata.create_all(engine, checkfirst=True)

    def start_run(self, trigger: str) -> str:
        run_id = str(uuid.uuid4())
        with self.engine.begin() as connection:
            connection.execute(
                update_runs.insert().values(
                    id=run_id, started_at=datetime.now(UTC), trigger=trigger, notes=[]
                )
            )
        return run_id

    def finish_run(self, run_id: str, checked: int, changed: int, notes: list[dict]) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                update_runs.update()
                .where(update_runs.c.id == run_id)
                .values(
                    finished_at=datetime.now(UTC),
                    checked=checked,
                    changed=changed,
                    failed=len(notes),
                    notes=notes,
                )
            )

    def record_change(self, run_id: str, source_id: str, **fields) -> str:
        record_id = str(uuid.uuid4())
        with self.engine.begin() as connection:
            connection.execute(
                change_records.insert().values(
                    id=record_id, run_id=run_id, source_id=source_id, at=datetime.now(UTC), **fields
                )
            )
        return record_id

    def runs(self, limit: int = 20) -> list[dict]:
        query = select(update_runs).order_by(update_runs.c.started_at.desc()).limit(limit)
        with self.engine.connect() as connection:
            return [dict(r._mapping) for r in connection.execute(query)]

    def running(self) -> bool:
        query = select(update_runs.c.id).where(update_runs.c.finished_at.is_(None))
        with self.engine.connect() as connection:
            return connection.execute(query).first() is not None

    def changes(self, source_ids: set[str] | None = None, limit: int = 50) -> list[dict]:
        query = select(change_records).order_by(change_records.c.at.desc()).limit(limit)
        if source_ids is not None:
            query = query.where(change_records.c.source_id.in_(sorted(source_ids)))
        with self.engine.connect() as connection:
            return [dict(r._mapping) for r in connection.execute(query)]


def changed_since(raw_dir: Path, versions: dict[str, dict]) -> list[str]:
    """The Sources whose text differs from the version an answer was stored with."""
    return [
        source_id
        for source_id, used in versions.items()
        if used.get("sha256") and not same_text(used, current_version(raw_dir, source_id))
    ]


_run_lock = threading.Lock()


def try_start(run) -> bool:
    """Runs `run()` in a background thread unless a run is already going; one at a time."""
    if not _run_lock.acquire(blocking=False):
        return False

    def guarded() -> None:
        try:
            run()
        except BaseException:
            log.exception("update run failed")
        finally:
            _run_lock.release()

    threading.Thread(target=guarded, name="update-run", daemon=True).start()
    return True


def is_running() -> bool:
    return _run_lock.locked()


class ReloadFailed(RuntimeError):
    """The new text could not be chunked, embedded or stored; the old copy stays in place."""


def check_source(
    settings: Settings,
    store,
    client: httpx.Client,
    source: Source,
    robots_cache: dict,
    baseline_store=None,
) -> dict | None:
    """Downloads one Source; when its text changed, replaces its Passages in one transaction and
    returns the Change Record fields, else None. Nothing on disk changes until the store holds
    the new Passages, so a failed reload is simply retried on the next run."""
    live_dir = settings.raw_dir / source.id
    old = current_version(settings.raw_dir, source.id)
    content, meta = download(client, source, robots_cache)
    if meta["sha256"] == old["sha256"]:
        save_meta(live_dir, meta)  # same file: note the check, keep the fingerprint
        if not old["text_sha256"]:  # fingerprint missing from an older ingest
            stored = provisions_in_store(store, source.id)
            record_text_fingerprint(
                settings.raw_dir, source.id, [p for ids in stored.values() for p in ids]
            )
        return None
    staging_root = settings.raw_dir / ".incoming"
    staging_dir = staging_root / source.id
    try:
        staging_dir.mkdir(parents=True, exist_ok=True)
        (staging_dir / FILE_NAMES[source.format]).write_bytes(content)
        before = provisions_in_store(store, source.id)
        loaded = load(source, staging_root)
        passages = chunk(loaded, source, settings)
        new_ids = [p.metadata["passage_id"] for p in passages]
        fingerprint = text_fingerprint(new_ids)
        if set(new_ids) == {p for ids in before.values() for p in ids}:
            _promote(staging_dir, live_dir, source, meta, fingerprint)
            log.info("update run: %s file differs, text unchanged", source.id)
            return None
        vectors = store.embeddings.embed_documents([p.page_content for p in passages])
        replace_source(store, source.id, passages, vectors)
        after = provisions_in_store(store, source.id)
        if baseline_store is not None and provisions_in_store(baseline_store, source.id):
            # the naive baseline collection holds this Source too: keep the comparison fair
            fixed = chunk(loaded, source, settings.model_copy(update={"chunker": "fixed"}))
            fixed_vectors = baseline_store.embeddings.embed_documents(
                [p.page_content for p in fixed]
            )
            replace_source(baseline_store, source.id, fixed, fixed_vectors)
        _promote(staging_dir, live_dir, source, meta, fingerprint)
    except Exception as e:
        raise ReloadFailed(f"{type(e).__name__}: {e}") from e
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)
    added, removed, altered = diff_provisions(before, after)
    return {
        "old_sha256": old["sha256"] or None,
        "new_sha256": meta["sha256"],
        "old_fetched_at": old["fetched_at"] or None,
        "passages_before": sum(len(v) for v in before.values()),
        "passages_after": sum(len(v) for v in after.values()),
        "added": added,
        "removed": removed,
        "changed": altered,
    }


def _promote(
    staging_dir: Path, live_dir: Path, source: Source, meta: dict, fingerprint: str
) -> None:
    """The new file replaces the live copy only now, together with its meta record."""
    name = FILE_NAMES[source.format]
    live_dir.mkdir(parents=True, exist_ok=True)
    os.replace(staging_dir / name, live_dir / name)
    save_meta(live_dir, meta, text_sha256=fingerprint)


def run_update(
    settings: Settings,
    updates: UpdateStore,
    store,
    trigger: str,
    sources: list[Source] | None = None,
    baseline_store=None,
) -> dict:
    """One Update Run over every Source (or the ones given). Returns the run's figures. The run
    row is always finished, even when the loop itself fails. With `baseline_store`, the naive
    fixed-size collection is refreshed as well for a Source whose text changed."""
    run_id = updates.start_run(trigger)
    checked = changed = 0
    notes: list[dict] = []
    robots_cache: dict = {}
    try:
        sources = sources or load_sources(settings.sources_file)
        with httpx.Client(
            headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=180.0
        ) as client:
            for source in sources:
                try:
                    change = check_source(
                        settings, store, client, source, robots_cache, baseline_store
                    )
                except (FetchRefused, httpx.HTTPError, ValueError) as e:
                    notes.append({"source_id": source.id, "error": str(e)[:200]})
                    log.warning("update run %s: %s not checked: %s", run_id, source.id, e)
                    continue
                except ReloadFailed as e:
                    checked += 1
                    notes.append({"source_id": source.id, "error": f"reload failed: {e}"[:200]})
                    log.exception(
                        "update run %s: %s reload failed, old copy kept", run_id, source.id
                    )
                    continue
                checked += 1
                if change is None:
                    continue
                updates.record_change(run_id, source.id, **change)
                changed += 1
                log.info(
                    "update run %s: %s changed (+%d -%d ~%d provisions)",
                    run_id,
                    source.id,
                    change["added"],
                    change["removed"],
                    change["changed"],
                )
    except BaseException as e:
        notes.append({"source_id": "", "error": f"run stopped: {e}"[:200]})
        log.exception("update run %s stopped", run_id)
    finally:
        updates.finish_run(run_id, checked, changed, notes)
        staging_root = settings.raw_dir / ".incoming"
        if staging_root.is_dir() and not any(staging_root.iterdir()):
            staging_root.rmdir()
    return {"id": run_id, "checked": checked, "changed": changed, "failed": len(notes)}


def seconds_until(hour: int, now: datetime | None = None) -> float:
    now = now or datetime.now(UTC)
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def start_scheduler(hour: int, run) -> threading.Thread:
    """A daemon thread that calls `run()` once a day at `hour` UTC."""

    def loop() -> None:
        while True:
            time.sleep(seconds_until(hour))
            try:
                run()
            except Exception:
                log.exception("scheduled update run failed")

    thread = threading.Thread(target=loop, name="update-runs", daemon=True)
    thread.start()
    return thread
