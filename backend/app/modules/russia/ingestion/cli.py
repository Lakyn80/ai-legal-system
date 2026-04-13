"""
CLI entrypoint for Russian law ingestion.

Usage
─────
    # Ingest a single file
    python -m app.modules.russia.ingestion.cli \\
        --file /app/Ruske_zakony/Семейный\\ кодекс\\ ....txt

    # Ingest the entire Milestone 1 corpus
    python -m app.modules.russia.ingestion.cli \\
        --corpus /app/Ruske_zakony

    # Custom checkpoint location
    python -m app.modules.russia.ingestion.cli \\
        --corpus /app/Ruske_zakony \\
        --checkpoint /app/checkpoints/russia.json

    # Custom Qdrant endpoint and batch size
    python -m app.modules.russia.ingestion.cli \\
        --corpus /app/Ruske_zakony \\
        --qdrant-url http://localhost:6333 \\
        --batch-size 32

Arguments
─────────
    --file PATH         Ingest a single .txt file
    --corpus DIR        Ingest all recognized .txt files in a directory tree
    (one of --file or --corpus is required)

    --qdrant-url URL    Qdrant base URL  (default: from settings)
    --qdrant-api-key KEY  Qdrant API key (default: from settings)
    --batch-size INT    Chunks per embed+upsert batch  (default: 64)
    --checkpoint PATH   Checkpoint file path  (default: russian_laws_checkpoint.json)
    --no-checkpoint     Ignore and overwrite checkpoint (force re-ingest)
    --quiet             Suppress progress output

Settings are read from the project .env via get_settings() — running from
the backend/ directory picks up the correct environment automatically.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def main() -> None:
    # Import inside main() so the module can be imported in tests without
    # triggering pydantic settings validation at import time.
    from app.core.config import get_settings
    from app.modules.common.embeddings.provider import EmbeddingService
    from app.modules.russia.ingestion.service import (
        DEFAULT_CHECKPOINT_FILE,
        DEFAULT_BATCH_SIZE,
        ingest_law_file,
        ingest_corpus,
        IngestReport,
        FileIngestResult,
    )
    from app.modules.russia.ingestion.embedder import RussianLawEmbedder
    from app.modules.russia.ingestion.qdrant_writer import RussianLawQdrantWriter

    settings = get_settings()

    parser = argparse.ArgumentParser(
        prog="russian_law_ingest",
        description="Ingest Russian law files into Qdrant collection russian_laws_v1.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # ── Input mode (mutually exclusive) ──────────────────────────────────────
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--file",
        type=Path,
        metavar="PATH",
        help="Ingest a single .txt file",
    )
    input_group.add_argument(
        "--corpus",
        type=Path,
        metavar="DIR",
        help="Ingest all recognized .txt files in a directory tree",
    )

    # ── Qdrant ────────────────────────────────────────────────────────────────
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
        help="Qdrant API key (omit if not required)",
    )

    # ── Processing ────────────────────────────────────────────────────────────
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        metavar="N",
        help="Chunks per embed+upsert batch",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=DEFAULT_CHECKPOINT_FILE,
        metavar="PATH",
        help="Checkpoint JSON file (records completed files)",
    )
    parser.add_argument(
        "--no-checkpoint",
        action="store_true",
        help="Ignore existing checkpoint and re-ingest all files",
    )
    parser.add_argument(
        "--idf-checkpoint",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "Path to IDFTable JSON for BM25 sparse encoding. "
            "If the file does not exist, it is built from the corpus and saved here. "
            "When omitted, sparse vectors are left empty (Milestone 1 mode)."
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )

    args = parser.parse_args()
    verbose = not args.quiet

    # ── Print run parameters ──────────────────────────────────────────────────
    if verbose:
        print("Russian Law Ingestion Pipeline")
        print(f"  qdrant       : {args.qdrant_url}")
        print(f"  embedding    : {settings.embedding_provider} / {settings.embedding_model}")
        print(f"  batch_size   : {args.batch_size}")
        if args.file:
            print(f"  mode         : single file")
            print(f"  file         : {args.file}")
        else:
            print(f"  mode         : corpus directory")
            print(f"  corpus       : {args.corpus}")
            print(f"  checkpoint   : {args.checkpoint}")
            print(f"  no-checkpoint: {args.no_checkpoint}")
        print()

    # ── Build embedding service ───────────────────────────────────────────────
    embedding_service = EmbeddingService(
        model_name=settings.embedding_model,
        provider_name=settings.embedding_provider,
        fallback_provider_name=settings.embedding_fallback_provider,
        hash_dimension=settings.embedding_hash_dimension,
    )

    t0 = time.time()

    # ── Single file mode ──────────────────────────────────────────────────────
    if args.file:
        if not args.file.exists():
            print(f"[ERROR] File not found: {args.file}", file=sys.stderr)
            sys.exit(1)

        embedder = RussianLawEmbedder(embedding_service)
        writer = RussianLawQdrantWriter(url=args.qdrant_url, api_key=args.qdrant_api_key)
        writer.ensure_collection(dimension=embedder.dimension)

        result: FileIngestResult = ingest_law_file(
            path=args.file,
            embedder=embedder,
            writer=writer,
            batch_size=args.batch_size,
        )
        elapsed = time.time() - t0

        print()
        print("=" * 56)
        if result.error:
            print("  INGESTION FAILED")
            print("=" * 56)
            print(f"  file         : {result.path.name}")
            print(f"  error        : {result.error}")
            sys.exit(1)
        else:
            print("  INGESTION COMPLETE")
            print("=" * 56)
            print(f"  law          : {result.law_short} ({result.law_id})")
            print(f"  articles     : {result.article_count:>12,}")
            print(f"  tombstones   : {result.tombstone_count:>12,}")
            print(f"  chunks       : {result.chunks_written:>12,}")
            print(f"  elapsed      : {elapsed:>11.1f}s")
            print("=" * 56)

    # ── Corpus mode ───────────────────────────────────────────────────────────
    else:
        if not args.corpus.exists() or not args.corpus.is_dir():
            print(f"[ERROR] Corpus directory not found: {args.corpus}", file=sys.stderr)
            sys.exit(1)

        checkpoint_path = None if args.no_checkpoint else args.checkpoint
        # When --no-checkpoint is set, pass a temp path that won't exist
        if args.no_checkpoint:
            import tempfile
            checkpoint_path = Path(tempfile.mktemp(suffix=".json"))

        report: IngestReport = ingest_corpus(
            directory=args.corpus,
            embedding_service=embedding_service,
            qdrant_url=args.qdrant_url,
            qdrant_api_key=args.qdrant_api_key,
            batch_size=args.batch_size,
            checkpoint_path=checkpoint_path or args.checkpoint,
            idf_checkpoint_path=args.idf_checkpoint,
            verbose=verbose,
        )

        print()
        print("=" * 56)
        print("  CORPUS INGESTION COMPLETE")
        print("=" * 56)
        print(f"  files found        : {report.files_found:>10,}")
        print(f"  files ingested     : {report.files_ingested:>10,}")
        print(f"  files skipped (ckpt): {report.files_skipped_checkpoint:>9,}")
        print(f"  files unrecognized : {report.files_unrecognized:>10,}")
        print(f"  files failed       : {report.files_failed:>10,}")
        print(f"  total chunks       : {report.total_chunks:>10,}")
        print(f"  elapsed            : {report.elapsed_seconds:>10.1f}s")
        print("=" * 56)

        # Exit with non-zero if any files failed
        if report.files_failed > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()
