"""
CLI entrypoint for Czech law ingestion.

Usage
─────
    # Full ingestion
    python -m app.modules.czechia.ingestion.cli --input /path/to/rag_legal_dataset.json

    # Test run (first 1000 fragments only)
    python -m app.modules.czechia.ingestion.cli \\
        --input /path/to/rag_legal_dataset.json \\
        --limit 1000

    # Custom Qdrant + embedding settings
    python -m app.modules.czechia.ingestion.cli \\
        --input /path/to/rag_legal_dataset.json \\
        --qdrant-url http://localhost:6333 \\
        --batch-size 32 \\
        --chunk-size 800 \\
        --chunk-overlap 120

Arguments
─────────
    --input PATH            Path to rag_legal_dataset.json  [required]
    --qdrant-url URL        Qdrant URL  (default: from QDRANT_URL / settings)
    --qdrant-api-key KEY    Qdrant API key  (default: from settings)
    --batch-size INT        Embedding batch size  (default: 64)
    --limit INT             Process only N fragments — for smoke-testing
    --chunk-size INT        Max characters per chunk  (default: from settings)
    --chunk-overlap INT     Chunk overlap in characters  (default: from settings)

The script reads QDRANT_URL and embedding settings from the project .env via
get_settings() so running it from the backend/ directory works out of the box.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def main() -> None:
    # Import inside main() so that the module can be imported for testing
    # without triggering pydantic settings validation at import time.
    from app.core.config import get_settings
    from app.modules.common.embeddings.provider import EmbeddingService
    from app.modules.czechia.ingestion.qdrant_writer import CzechLawQdrantWriter
    from app.modules.czechia.ingestion.service import CzechLawIngestionService

    settings = get_settings()

    parser = argparse.ArgumentParser(
        prog="czech_law_ingest",
        description="Ingest Czech laws from rag_legal_dataset.json into Qdrant.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        metavar="PATH",
        help="Path to rag_legal_dataset.json",
    )
    parser.add_argument(
        "--qdrant-url",
        default=settings.qdrant_url,
        metavar="URL",
        help="Qdrant base URL",
    )
    parser.add_argument(
        "--qdrant-api-key",
        default=settings.qdrant_api_key,
        metavar="KEY",
        help="Qdrant API key (leave empty if not set)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        metavar="N",
        help="Number of chunks per embedding + upsert batch",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Stop after N fragments (omit for full ingestion)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=settings.chunk_size,
        metavar="N",
        help="Maximum characters per chunk",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=settings.chunk_overlap,
        metavar="N",
        help="Overlap between consecutive chunks in characters",
    )

    args = parser.parse_args()

    # ── validate input ────────────────────────────────────────────────────
    if not args.input.exists():
        print(f"[ERROR] Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    # ── print run parameters ──────────────────────────────────────────────
    print("Czech Law Ingestion Pipeline")
    print(f"  input        : {args.input}")
    print(f"  qdrant       : {args.qdrant_url}")
    print(f"  embedding    : {settings.embedding_provider} / {settings.embedding_model}")
    print(f"  batch_size   : {args.batch_size}")
    print(f"  chunk_size   : {args.chunk_size}  overlap: {args.chunk_overlap}")
    print(f"  limit        : {args.limit if args.limit is not None else 'unlimited'}")
    print()

    # ── build service graph ───────────────────────────────────────────────
    embedding_service = EmbeddingService(
        model_name=settings.embedding_model,
        provider_name=settings.embedding_provider,
        fallback_provider_name=settings.embedding_fallback_provider,
        hash_dimension=settings.embedding_hash_dimension,
    )

    qdrant_writer = CzechLawQdrantWriter(
        url=args.qdrant_url,
        api_key=args.qdrant_api_key,
    )

    service = CzechLawIngestionService(
        embedding_service=embedding_service,
        qdrant_writer=qdrant_writer,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        batch_size=args.batch_size,
        verbose=True,
    )

    # ── run ───────────────────────────────────────────────────────────────
    t0 = time.time()
    stats = service.run(dataset_path=args.input, limit=args.limit)
    elapsed = time.time() - t0

    # ── summary ───────────────────────────────────────────────────────────
    print()
    print("=" * 56)
    print("  INGESTION COMPLETE")
    print("=" * 56)
    print(f"  fragments seen     : {stats.fragments_seen:>12,}")
    print(f"  fragments filtered : {stats.fragments_filtered:>12,}")
    for reason, count in sorted(stats.filter_reasons.items()):
        print(f"    └─ {reason:<18}: {count:>10,}")
    print(f"  chunks upserted    : {stats.chunks_upserted:>12,}")
    print(f"  batches            : {stats.batches:>12,}")
    print(f"  elapsed            : {elapsed:>11.1f}s")
    print("=" * 56)


if __name__ == "__main__":
    main()
