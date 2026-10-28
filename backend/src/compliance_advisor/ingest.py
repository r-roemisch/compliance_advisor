"""compliance-advisor-ingest: load, chunk, embed and store downloaded Sources.

For every Source it runs, it first deletes that Source's Passages and then inserts the new
ones, so running it twice never creates duplicates. --dry-run stops after chunking and touches
neither OpenRouter nor the database.
"""

import argparse
import time

import openai

from .chunker import chunk
from .loaders import load
from .registry import load_sources, select
from .settings import get_settings
from .update import record_text_fingerprint


def main() -> None:
    parser = argparse.ArgumentParser(description="Index downloaded Sources into the vector store.")
    parser.add_argument("--source", action="append", metavar="ID", help="a Source id; repeatable")
    parser.add_argument("--dry-run", action="store_true", help="load and chunk only, show counts")
    parser.add_argument(
        "--rebuild", action="store_true", help="empty the whole collection first, then ingest"
    )
    parser.add_argument("--chunker", choices=["provision", "fixed"], help="override CHUNKER")
    args = parser.parse_args()

    settings = get_settings()
    if args.chunker:
        settings = settings.model_copy(update={"chunker": args.chunker})
    print(f"Collection: {settings.collection}")
    sources = select(load_sources(settings.sources_file), args.source)

    store = None
    if not args.dry_run:
        from .embeddings import get_embeddings
        from .store import get_store

        store = get_store(settings, get_embeddings(settings))
        if args.rebuild:
            store.delete_collection()
            store.create_collection()
            print(f"Emptied collection {settings.collection!r}.")

    failures = 0
    for source in sources:
        try:
            loaded = load(source, settings.raw_dir)
        except FileNotFoundError as e:
            failures += 1
            print(f"{source.id}: skipped: {e}")
            continue
        passages = chunk(loaded, source, settings)
        if not passages:
            failures += 1
            print(f"{source.id}: the loader found no text; check the downloaded file")
            continue
        average = sum(len(p.page_content) for p in passages) // len(passages)
        summary = f"{len(loaded.text):,} characters -> {len(passages)} Passages (avg {average})"
        if args.dry_run:
            sample = passages[min(3, len(passages) - 1)]
            label = sample.metadata.get("provision", "")
            print(f"{source.id}: {summary}\n    sample {label}: {sample.page_content[:240]!r}")
            continue
        from .store import replace_source

        started = time.monotonic()
        try:
            # Embed first, so a failing API call leaves the Source's old Passages in place.
            vectors = store.embeddings.embed_documents([p.page_content for p in passages])
        except openai.AuthenticationError as e:
            reason = e.body.get("message", e.body) if isinstance(e.body, dict) else e.body
            raise SystemExit(
                f"OpenRouter rejected the API key ({reason}). Check OPENROUTER_API_KEY."
            )
        except openai.APIError as e:
            failures += 1
            print(f"{source.id}: embedding failed, old Passages kept: {e}")
            continue
        removed = replace_source(store, source.id, passages, vectors)  # one transaction
        if settings.chunker == "provision":  # the naive baseline must not pose as the Corpus
            record_text_fingerprint(
                settings.raw_dir, source.id, [p.metadata["passage_id"] for p in passages]
            )
        print(
            f"{source.id}: {summary}; removed {removed} old, stored {len(passages)} "
            f"in {time.monotonic() - started:.1f}s"
        )
    raise SystemExit(1 if failures else 0)
