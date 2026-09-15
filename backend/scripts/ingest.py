#!/usr/bin/env python3
"""
Transcript ingestion CLI.

Usage:
    python scripts/ingest.py                         # Ingest all transcripts
    python scripts/ingest.py --dir data/transcripts/user/  # Custom directory
    python scripts/ingest.py --refresh               # Re-embed everything
    python scripts/ingest.py --stats                 # Show index stats

The ingester loads .txt and .md files, cleans them, chunks them,
embeds them with a local sentence-transformer, and stores them in ChromaDB.

Nothing is fabricated. Only files that exist on disk are processed.
"""
from __future__ import annotations

import argparse
import sys
import os

# Allow running from backend/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Lenny transcript files into the vector store."
    )
    parser.add_argument(
        "--dir",
        default="data/transcripts",
        help="Directory containing transcript files (default: data/transcripts)",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Delete and rebuild the entire index (default: incremental upsert)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print index statistics and exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and chunk files without embedding (for testing)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Load .env if present
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    from app.core.logging import configure_logging, get_logger
    configure_logging()
    log = get_logger("ingest")

    from app.rag.embedder import get_index_stats, _get_chroma_client, _get_collection
    from app.core.config import settings

    if args.stats:
        stats = get_index_stats()
        print(f"\n{'='*50}")
        print(f"  Vector Store Stats")
        print(f"{'='*50}")
        print(f"  Collection:  {stats.get('collection', settings.CHROMA_COLLECTION)}")
        print(f"  Status:      {stats.get('status')}")
        print(f"  Chunks:      {stats.get('chunk_count', 0):,}")
        if stats.get("error"):
            print(f"  Error:       {stats['error']}")
        print(f"{'='*50}\n")
        return

    if args.refresh:
        log.warning("ingest.refresh_mode", note="Deleting existing index...")
        try:
            client = _get_chroma_client()
            client.delete_collection(settings.CHROMA_COLLECTION)
            log.info("ingest.index_deleted")
            # Reset the global collection reference
            import app.rag.embedder as emb_module
            emb_module._collection = None
        except Exception as exc:
            log.error("ingest.refresh_error", error=str(exc))

    from app.rag.ingester import load_transcripts
    from app.rag.chunker import chunk_documents
    from app.rag.embedder import embed_chunks

    transcript_dir = args.dir
    log.info("ingest.start", dir=transcript_dir)

    docs = load_transcripts(transcript_dir)
    if not docs:
        print(f"\n⚠️  No transcript files found in {transcript_dir}")
        print("   Add .txt or .md files following the naming convention:")
        print("   YYYY-MM-DD_guest-name_episode-title.txt")
        print("   Or with YAML frontmatter (title, guest, date, url fields).")
        sys.exit(0)

    print(f"\n✅ Loaded {len(docs)} transcript documents")

    chunks = chunk_documents(docs)
    print(f"✅ Created {len(chunks):,} chunks")

    if args.dry_run:
        print("\n🔍 Dry run — skipping embedding.")
        print("Sample chunks:")
        for chunk in chunks[:3]:
            print(f"\n  [{chunk.chunk_id}] {chunk.citation}")
            print(f"  {chunk.content[:150]}...")
        return

    print("⏳ Embedding chunks (this may take a minute on first run)...")
    embed_chunks(chunks)

    stats = get_index_stats()
    print(f"\n✅ Ingestion complete!")
    print(f"   Total chunks indexed: {stats.get('chunk_count', 0):,}")
    print(f"   Collection: {stats.get('collection')}")
    print(f"\nRun your app and start asking questions about Lenny's content!\n")


if __name__ == "__main__":
    main()
