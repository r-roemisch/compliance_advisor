"""Update Runs: the Provision diff, the schedule, and which answers used an older Source."""

import json
from datetime import UTC, datetime

from compliance_advisor.update import (
    changed_since,
    diff_provisions,
    is_running,
    same_text,
    seconds_until,
    try_start,
)


def test_diff_counts_added_removed_and_changed_provisions():
    before = {"Art. 1": {"a1"}, "Art. 2": {"a2"}, "Art. 3": {"a3", "a3b"}}
    after = {"Art. 1": {"a1"}, "Art. 2": {"a2-new"}, "Art. 4": {"a4"}}
    assert diff_provisions(before, after) == (
        1,
        1,
        1,
    )  # Art. 4 added, Art. 3 removed, Art. 2 changed


def test_scheduler_waits_until_the_next_run_hour():
    now = datetime(2026, 10, 28, 14, 30, tzinfo=UTC)
    assert seconds_until(3, now) == (24 - 14.5 + 3) * 3600
    assert seconds_until(15, now) == 1800


def test_answers_stored_with_an_older_checksum_are_flagged(tmp_path):
    (tmp_path / "eu-dora").mkdir()
    (tmp_path / "eu-dora" / "meta.json").write_text(
        json.dumps({"sha256": "new", "fetched_at": "x"})
    )
    (tmp_path / "de-gwg").mkdir()
    (tmp_path / "de-gwg" / "meta.json").write_text(
        json.dumps({"sha256": "same", "fetched_at": "x"})
    )
    versions = {"eu-dora": {"sha256": "old"}, "de-gwg": {"sha256": "same"}, "de-kwg": {}}
    assert changed_since(tmp_path, versions) == ["eu-dora"]


def test_text_fingerprint_decides_when_both_sides_have_one():
    current = {"sha256": "file-b", "text_sha256": "text-a"}
    assert same_text({"sha256": "file-a", "text_sha256": "text-a"}, current)  # markup differs only
    assert not same_text({"sha256": "file-a", "text_sha256": "text-z"}, current)
    assert not same_text({"sha256": "file-a"}, current)  # stored before fingerprints: by file


def test_only_one_update_run_starts_at_a_time():
    import threading

    gate = threading.Event()
    assert try_start(gate.wait) is True
    assert is_running() and try_start(gate.wait) is False
    gate.set()
    for _ in range(50):
        if not is_running():
            break
        threading.Event().wait(0.01)
    assert not is_running()


# --- The staged Update Run (review fix A3) --------------------------------------------------

import types

from langchain_core.documents import Document

from compliance_advisor import update
from compliance_advisor.registry import load_sources
from compliance_advisor.settings import Settings


def _staging(tmp_path, monkeypatch, new_ids, stored_ids, replace):
    """A Source with a live file and meta, a fake download of changed bytes, and fakes for the
    store: `stored_ids` are the Passage ids in the store, `new_ids` those the new file yields."""
    settings = Settings(data_dir=tmp_path)
    source = load_sources(settings.config_dir / "sources.yaml")[0]
    live = settings.raw_dir / source.id
    live.mkdir(parents=True)
    (live / update.FILE_NAMES[source.format]).write_bytes(b"old")
    update.save_meta(live, {"sha256": "old-file"}, text_sha256="old-text")
    monkeypatch.setattr(update, "download", lambda c, s, r: (b"new", {"sha256": "new-file"}))
    monkeypatch.setattr(
        update, "provisions_in_store", lambda store, sid: {"Art. 1": set(stored_ids)}
    )
    monkeypatch.setattr(
        update, "load", lambda source, root: root
    )  # the staging root, checked below
    monkeypatch.setattr(
        update,
        "chunk",
        lambda loaded, source, settings: [
            Document(page_content="t", metadata={"passage_id": i}) for i in new_ids
        ],
    )
    monkeypatch.setattr(update, "replace_source", replace)
    store = types.SimpleNamespace(
        embeddings=types.SimpleNamespace(embed_documents=lambda texts: [[0.1]] * len(texts))
    )
    return settings, source, live, store


def test_failed_reload_leaves_the_live_copy_and_meta_untouched(tmp_path, monkeypatch):
    def explode(*args):
        raise RuntimeError("embedding store down")

    settings, source, live, store = _staging(tmp_path, monkeypatch, ["p2"], ["p1"], explode)
    try:
        update.check_source(settings, store, None, source, {})
    except update.ReloadFailed as e:
        assert "embedding store down" in str(e)
    else:
        raise AssertionError("expected ReloadFailed")
    assert (live / update.FILE_NAMES[source.format]).read_bytes() == b"old"
    assert update.current_version(settings.raw_dir, source.id) == {
        "sha256": "old-file",
        "text_sha256": "old-text",
        "fetched_at": "",
    }
    assert not (settings.raw_dir / ".incoming" / source.id).exists()


def test_changed_text_is_replaced_then_promoted(tmp_path, monkeypatch):
    calls = []
    settings, source, live, store = _staging(
        tmp_path, monkeypatch, ["p2", "p3"], ["p1"], lambda store, sid, p, v: calls.append(len(p))
    )
    change = update.check_source(settings, store, None, source, {})
    assert calls == [2]
    assert change["old_sha256"] == "old-file" and change["new_sha256"] == "new-file"
    assert (live / update.FILE_NAMES[source.format]).read_bytes() == b"new"
    meta = update.current_version(settings.raw_dir, source.id)
    assert meta["sha256"] == "new-file" and meta["text_sha256"] == update.text_fingerprint(
        ["p2", "p3"]
    )


def test_markup_only_change_is_promoted_without_embedding(tmp_path, monkeypatch):
    def never(*args):
        raise AssertionError("must not embed or replace")

    settings, source, live, store = _staging(tmp_path, monkeypatch, ["p1"], ["p1"], never)
    store.embeddings.embed_documents = never
    assert update.check_source(settings, store, None, source, {}) is None
    assert (live / update.FILE_NAMES[source.format]).read_bytes() == b"new"
    assert update.current_version(settings.raw_dir, source.id)[
        "text_sha256"
    ] == update.text_fingerprint(["p1"])
