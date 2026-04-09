"""
CzechLawIngestionService — orchestrates the full ingestion pipeline.

Pipeline
────────
  1. Build relation index  (metadata + terms + definitions → ~50 MB RAM)
  2. Ensure Qdrant collection exists
  3. Stream law_fragments → filter → chunk → batch embed → upsert

Resumability
────────────
  chunk_id is deterministic (uuid5 of fragment_id:chunk_index).
  Qdrant upsert is idempotent.  Restarting after a crash will re-process
  and overwrite already-stored chunks without data corruption.
  A future --skip-existing mode can scroll the collection to skip fragments
  whose chunk_id is already present.

Memory
──────
  Peak usage = relation_index (~50 MB) + current batch (batch_size chunks).
  The 3.7 GB dataset file is streamed and never fully loaded into RAM.

Progress reporting
──────────────────
  A status line is printed every 100 batches (≈ 6 400 fragments at batch_size=64).
  For silent mode, set verbose=False.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from app.modules.common.embeddings.provider import EmbeddingService
from app.modules.czechia.ingestion.chunk_builder import build_chunks
from app.modules.czechia.ingestion.embedder import CzechLawEmbedder
from app.modules.czechia.ingestion.fragment_filter import should_ingest
from app.modules.czechia.ingestion.loader import stream_law_fragments
from app.modules.czechia.ingestion.qdrant_writer import CzechLawQdrantWriter
from app.modules.czechia.ingestion.relation_index import build_relation_index
from app.modules.czechia.ingestion.schemas import CzechLawChunk


CHECKPOINT_FILE = Path("czech_laws_checkpoint.json")


def _load_checkpoint() -> int:
    """Return number of fragments already processed (0 if no checkpoint)."""
    if CHECKPOINT_FILE.exists():
        try:
            return int(json.loads(CHECKPOINT_FILE.read_text())["fragments_seen"])
        except Exception:
            pass
    return 0


def _save_checkpoint(fragments_seen: int) -> None:
    CHECKPOINT_FILE.write_text(json.dumps({"fragments_seen": fragments_seen}))


@dataclass
class IngestionStats:
    fragments_seen: int = 0
    fragments_filtered: int = 0
    chunks_total: int = 0
    chunks_upserted: int = 0
    batches: int = 0
    filter_reasons: dict[str, int] = field(default_factory=dict)


class CzechLawIngestionService:
    def __init__(
        self,
        embedding_service: EmbeddingService,
        qdrant_writer: CzechLawQdrantWriter,
        chunk_size: int = 1200,
        chunk_overlap: int = 180,
        batch_size: int = 64,
        verbose: bool = True,
    ) -> None:
        self._embedder = CzechLawEmbedder(embedding_service)
        self._writer = qdrant_writer
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._batch_size = batch_size
        self._verbose = verbose

    def run(
        self,
        dataset_path: Path,
        limit: int | None = None,
        resume: bool = True,
    ) -> IngestionStats:
        """
        Run the full ingestion pipeline and return statistics.

        Args:
            dataset_path: Path to rag_legal_dataset.json.
            limit:        Stop after processing this many fragments (for testing).
            resume:       If True, read checkpoint and skip already-processed fragments.
        """
        stats = IngestionStats()

        # ── resume: how many fragments to skip ───────────────────────────
        skip = _load_checkpoint() if resume else 0
        if skip > 0 and self._verbose:
            print(f"  [resume] Checkpoint found — skipping first {skip:,} fragments")

        # ── 1. relation index ─────────────────────────────────────────────
        if self._verbose:
            print("[1/3] Building relation index...")
        relation_index = build_relation_index(dataset_path)

        # ── 2. ensure collection ──────────────────────────────────────────
        if self._verbose:
            print("[2/3] Ensuring Qdrant collection 'czech_laws_v2'...")
        self._writer.ensure_collection(dimension=self._embedder.dimension)

        # ── 3. stream → skip → filter → chunk → embed → upsert ───────────
        if self._verbose:
            print("[3/3] Streaming law_fragments...")

        batch: list[CzechLawChunk] = []
        total_seen = 0  # total including skipped, for checkpoint alignment

        for fragment in stream_law_fragments(dataset_path):
            total_seen += 1

            # skip already-processed fragments
            if total_seen <= skip:
                continue

            if limit is not None and stats.fragments_seen >= limit:
                break

            stats.fragments_seen += 1

            result = should_ingest(fragment)
            if not result.accepted:
                stats.fragments_filtered += 1
                stats.filter_reasons[result.reason] = (
                    stats.filter_reasons.get(result.reason, 0) + 1
                )
                continue

            chunks = build_chunks(
                fragment,
                relation_index,
                chunk_size=self._chunk_size,
                chunk_overlap=self._chunk_overlap,
            )
            batch.extend(chunks)
            stats.chunks_total += len(chunks)

            if len(batch) >= self._batch_size:
                self._flush(batch, stats)
                batch = []
                _save_checkpoint(skip + stats.fragments_seen)
                if self._verbose and stats.batches % 100 == 0:
                    self._log_progress(stats)

        # flush remaining
        if batch:
            self._flush(batch, stats)
            _save_checkpoint(skip + stats.fragments_seen)

        return stats

    def _flush(self, batch: list[CzechLawChunk], stats: IngestionStats) -> None:
        embedded = self._embedder.embed_batch(batch)
        self._writer.upsert_batch(embedded)
        stats.chunks_upserted += len(batch)
        stats.batches += 1

    def _log_progress(self, stats: IngestionStats) -> None:
        print(
            f"  fragments={stats.fragments_seen:>10,}  "
            f"filtered={stats.fragments_filtered:>8,}  "
            f"chunks={stats.chunks_upserted:>10,}  "
            f"batches={stats.batches:>6,}",
            flush=True,
        )
