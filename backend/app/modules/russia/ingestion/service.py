"""
Russian law ingestion orchestrator — Milestone 1.

Pipeline
────────
  loader → parser → chunk_builder → embedder → qdrant_writer

Two public entry points:
  ingest_law_file(path, ...)   — ingest a single .txt file end-to-end
  ingest_corpus(directory, ...) — ingest all recognized .txt files in a directory tree

Checkpoint
──────────
  A JSON file records successfully ingested files by their basename.
  Re-running skips any file already in the checkpoint.
  Checkpoint entry: { filename: { law_id, chunks, ingested_at } }
  The checkpoint is written atomically after each file succeeds.
  A failed file is NOT added to the checkpoint — the next run will retry it.

Deterministic order
───────────────────
  Files are processed sorted by their derived law_id so that corpus ingestion
  is reproducible regardless of filesystem ordering.

Unrecognized files
──────────────────
  Any .txt file whose filename does not match the _LAW_ID_MAP produces a
  law_id starting with 'local:ru/unknown/'. These files are reported as
  unrecognized and skipped — they are not ingested and not checkpointed.

Does NOT:
  - Perform retrieval
  - Use Celery or async orchestration
  - Use retries beyond simple local error handling
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.modules.common.embeddings.provider import EmbeddingService
from app.modules.russia.ingestion.chunk_builder import build_chunks
from app.modules.russia.ingestion.embedder import RussianLawEmbedder
from app.modules.russia.ingestion.loader import load_law_file
from app.modules.russia.ingestion.parser import parse_law
from app.modules.russia.ingestion.qdrant_writer import RussianLawQdrantWriter
from app.modules.russia.ingestion.schemas import RussianChunk

log = logging.getLogger(__name__)

# Default checkpoint filename — relative to CWD unless overridden
DEFAULT_CHECKPOINT_FILE = Path("russian_laws_checkpoint.json")

# Default embedding batch size (chunks per embed+upsert call)
DEFAULT_BATCH_SIZE = 64


# ---------------------------------------------------------------------------
# Result / report dataclasses
# ---------------------------------------------------------------------------

@dataclass
class FileIngestResult:
    """Result of ingesting one law file."""

    path: Path
    """Absolute path to the source file."""

    law_id: str
    """Canonical law_id, e.g. 'local:ru/tk'."""

    law_short: str
    """Common abbreviation, e.g. 'ТК РФ'."""

    article_count: int
    """Number of articles parsed (including tombstones)."""

    tombstone_count: int
    """Number of tombstone articles."""

    chunks_written: int
    """Number of chunks upserted to Qdrant."""

    elapsed_seconds: float
    """Wall-clock seconds for this file."""

    was_skipped: bool
    """True if the file was skipped due to checkpoint or being unrecognized."""

    skip_reason: str | None
    """Human-readable skip reason, or None if not skipped."""

    error: str | None
    """Exception message if the file failed, or None on success."""


@dataclass
class IngestReport:
    """Aggregated result of a corpus ingestion run."""

    files_found: int
    """Total .txt files discovered in the directory tree."""

    files_ingested: int
    """Files successfully ingested this run."""

    files_skipped_checkpoint: int
    """Files skipped because they were already in the checkpoint."""

    files_unrecognized: int
    """Files skipped because their filename did not match any known law."""

    files_failed: int
    """Files that raised an exception during ingestion."""

    total_chunks: int
    """Total chunks upserted across all files this run."""

    elapsed_seconds: float
    """Total wall-clock seconds for the entire run."""

    results: list[FileIngestResult] = field(default_factory=list)
    """Per-file results in processing order."""


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def _load_checkpoint(path: Path) -> dict[str, dict]:
    """Return the checkpoint dict, or empty dict if the file doesn't exist."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "files" in data:
            return data["files"]
    except Exception as exc:
        log.warning("checkpoint.load_failed path=%r err=%s", str(path), exc)
    return {}


def _save_checkpoint(path: Path, checkpoint: dict[str, dict]) -> None:
    """Write checkpoint atomically (write to .tmp then rename)."""
    tmp = path.with_suffix(".tmp")
    try:
        payload = json.dumps({"version": 1, "files": checkpoint}, ensure_ascii=False, indent=2)
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:
        log.error("checkpoint.save_failed path=%r err=%s", str(path), exc)


# ---------------------------------------------------------------------------
# Single-file ingestion
# ---------------------------------------------------------------------------

def ingest_law_file(
    path: Path,
    embedder: RussianLawEmbedder,
    writer: RussianLawQdrantWriter,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> FileIngestResult:
    """
    Ingest a single Russian law file end-to-end.

    Flow: loader → parser → chunk_builder → embedder (batched) → qdrant_writer

    Args:
        path:       Path to the UTF-16 .txt file
        embedder:   Configured RussianLawEmbedder
        writer:     Configured RussianLawQdrantWriter (collection must already exist)
        batch_size: Number of chunks per embed+upsert call

    Returns:
        FileIngestResult with counts and timing. On exception, error is set and
        chunks_written reflects how many chunks were written before the failure.
    """
    t0 = time.time()
    log.info("service.ingest_file.start path=%r", str(path))

    try:
        # ── Load ────────────────────────────────────────────────────────────
        metadata, raw_text = load_law_file(path)

        # ── Parse ───────────────────────────────────────────────────────────
        parse_result = parse_law(metadata, raw_text)

        # ── Build chunks ────────────────────────────────────────────────────
        chunks: list[RussianChunk] = build_chunks(parse_result)

        # ── Embed + upsert in batches ────────────────────────────────────────
        chunks_written = 0
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            embedded = embedder.embed_batch(batch)
            writer.upsert_batch(embedded)
            chunks_written += len(batch)

        elapsed = time.time() - t0
        log.info(
            "service.ingest_file.done path=%r law_id=%r articles=%d chunks=%d elapsed=%.1fs",
            str(path), metadata.law_id, parse_result.article_count, chunks_written, elapsed,
        )
        return FileIngestResult(
            path=path,
            law_id=metadata.law_id,
            law_short=metadata.law_short,
            article_count=parse_result.article_count,
            tombstone_count=parse_result.tombstone_count,
            chunks_written=chunks_written,
            elapsed_seconds=elapsed,
            was_skipped=False,
            skip_reason=None,
            error=None,
        )

    except Exception as exc:
        elapsed = time.time() - t0
        log.error("service.ingest_file.failed path=%r err=%s", str(path), exc)
        # Return a partial result — law metadata might not be available
        return FileIngestResult(
            path=path,
            law_id="unknown",
            law_short="Unknown",
            article_count=0,
            tombstone_count=0,
            chunks_written=0,
            elapsed_seconds=elapsed,
            was_skipped=False,
            skip_reason=None,
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# Corpus ingestion
# ---------------------------------------------------------------------------

def ingest_corpus(
    directory: Path,
    embedding_service: EmbeddingService,
    qdrant_url: str,
    qdrant_api_key: str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    checkpoint_path: Path = DEFAULT_CHECKPOINT_FILE,
    verbose: bool = True,
) -> IngestReport:
    """
    Ingest all recognized Russian law files in a directory tree.

    Discovery:
        Finds all .txt files recursively, then sorts by derived law_id for
        deterministic ordering. Unrecognized files (law_id startswith
        'local:ru/unknown/') are skipped and counted in the report.

    Checkpoint:
        Files successfully ingested in a previous run are skipped.
        The checkpoint is updated after each successful file.

    Args:
        directory:        Root directory to scan for .txt files
        embedding_service: Configured EmbeddingService
        qdrant_url:       Qdrant base URL
        qdrant_api_key:   Optional Qdrant API key
        batch_size:       Chunks per embed+upsert batch
        checkpoint_path:  Path to checkpoint JSON file
        verbose:          Print progress to stdout

    Returns:
        IngestReport with per-file results and aggregate counts.
    """
    t0 = time.time()

    embedder = RussianLawEmbedder(embedding_service)
    writer = RussianLawQdrantWriter(url=qdrant_url, api_key=qdrant_api_key)

    # ── Ensure collection exists ─────────────────────────────────────────────
    writer.ensure_collection(dimension=embedder.dimension)

    # ── Load checkpoint ──────────────────────────────────────────────────────
    checkpoint = _load_checkpoint(checkpoint_path)
    if verbose and checkpoint:
        print(f"  [checkpoint] Loaded — {len(checkpoint)} file(s) already ingested")

    # ── Discover files ───────────────────────────────────────────────────────
    txt_files = sorted(directory.rglob("*.txt"))
    if verbose:
        print(f"  [discover] Found {len(txt_files)} .txt file(s) in {directory}")

    # Sort by law_id for deterministic processing order
    from app.modules.russia.ingestion.loader import _derive_law_id  # noqa: PLC0415
    def _sort_key(p: Path) -> str:
        law_id, _ = _derive_law_id(p.name)
        return law_id

    txt_files.sort(key=_sort_key)

    # ── Process each file ────────────────────────────────────────────────────
    report = IngestReport(
        files_found=len(txt_files),
        files_ingested=0,
        files_skipped_checkpoint=0,
        files_unrecognized=0,
        files_failed=0,
        total_chunks=0,
        elapsed_seconds=0.0,
    )

    for path in txt_files:
        law_id, law_short = _derive_law_id(path.name)

        # Skip unrecognized files
        if law_id.startswith("local:ru/unknown/"):
            if verbose:
                print(f"  [skip] Unrecognized: {path.name}")
            report.files_unrecognized += 1
            report.results.append(FileIngestResult(
                path=path,
                law_id=law_id,
                law_short=law_short,
                article_count=0,
                tombstone_count=0,
                chunks_written=0,
                elapsed_seconds=0.0,
                was_skipped=True,
                skip_reason="unrecognized",
                error=None,
            ))
            continue

        # Skip checkpointed files
        if path.name in checkpoint:
            if verbose:
                prev = checkpoint[path.name]
                print(
                    f"  [skip] Already ingested: {law_short} ({prev.get('chunks', '?')} chunks)"
                )
            report.files_skipped_checkpoint += 1
            report.results.append(FileIngestResult(
                path=path,
                law_id=law_id,
                law_short=law_short,
                article_count=0,
                tombstone_count=0,
                chunks_written=checkpoint[path.name].get("chunks", 0),
                elapsed_seconds=0.0,
                was_skipped=True,
                skip_reason="checkpoint",
                error=None,
            ))
            continue

        # Ingest
        if verbose:
            print(f"  [ingest] {law_short} ({path.name[:60]}...)" if len(path.name) > 60
                  else f"  [ingest] {law_short} ({path.name})")

        result = ingest_law_file(path, embedder, writer, batch_size=batch_size)
        report.results.append(result)

        if result.error:
            report.files_failed += 1
            if verbose:
                print(f"    ERROR: {result.error}")
        else:
            report.files_ingested += 1
            report.total_chunks += result.chunks_written
            # Update checkpoint
            checkpoint[path.name] = {
                "law_id": result.law_id,
                "law_short": result.law_short,
                "chunks": result.chunks_written,
                "ingested_at": datetime.now(timezone.utc).isoformat(),
            }
            _save_checkpoint(checkpoint_path, checkpoint)
            if verbose:
                print(
                    f"    articles={result.article_count}  "
                    f"tombstones={result.tombstone_count}  "
                    f"chunks={result.chunks_written}  "
                    f"elapsed={result.elapsed_seconds:.1f}s"
                )

    report.elapsed_seconds = time.time() - t0
    log.info(
        "service.corpus_done ingested=%d skipped=%d unrecognized=%d failed=%d "
        "total_chunks=%d elapsed=%.1fs",
        report.files_ingested, report.files_skipped_checkpoint,
        report.files_unrecognized, report.files_failed,
        report.total_chunks, report.elapsed_seconds,
    )
    return report
