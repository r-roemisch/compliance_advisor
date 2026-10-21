"""compliance-advisor-ingest: load, chunk, embed and store downloaded Sources.

For every Source it runs, it first deletes that Source's Passages and then inserts the new
ones, so running it twice never creates duplicates. --dry-run stops after chunking and touches
neither OpenRouter nor the database.
"""

import argparse
import time

from .chunker import chunk
from .loaders import load
from .registry import load_sources, select
from .settings import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Index downloaded Sources into the vector store.")
    parser.add_argument("--source", action="append", metavar="ID", help="a Source id; repeatable")
    parser.add_argument("--dry-run", action="store_true", help="load and chunk only, show counts")
    parser.add_argument(
        "--rebuild", action="store_true", help="empty the whole collection first, then ingest"
    )
    args = parser.parse_args()

    settings = get_settings()
    sources = select(load_sources(settings.sources_file), args.source)

    store = None
    if not args.dry_run:
        from .embeddings import get_embeddings
        from .store import get_store

        store = get_store(settings, get_embeddings(settings))
        if args.rebuild:
            store.delete_collection()
            store.create_collection()
            print(f"Emptied collection {settings.embedding_model!r}.")

    failures = 0
    for source in sources:
        try:
            loaded = load(source, settings.raw_dir)
        except FileNotFoundError as e:
            failures += 1
            print(f"{source.id}: skipped: {e}")
            continue
        passages = chunk(loaded, settings.chunk_size, settings.chunk_overlap)
        if not passages:
            failures += 1
            print(f"{source.id}: the loader found no text; check the downloaded file")
            continue
        average = sum(len(p.page_content) for p in passages) // len(passages)
        summary = f"{len(loaded.text):,} characters -> {len(passages)} Passages (avg {average})"
        if args.dry_run:
            sample = passages[min(3, len(passages) - 1)].page_content[:300].replace("\n", " | ")
            print(f"{source.id}: {summary}\n    sample: {sample}")
            continue
        from .store import add_passages, delete_source

        started = time.monotonic()
        removed = delete_source(store, source.id)
        add_passages(store, passages)
        print(
            f"{source.id}: {summary}; removed {removed} old, stored {len(passages)} "
            f"in {time.monotonic() - started:.1f}s"
        )
    raise SystemExit(1 if failures else 0)
