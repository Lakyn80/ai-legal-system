"""
Two-pass hybrid ingestion into the czech_laws_v2 Qdrant collection.

Pass 1 — IDF scan
  Iterates every ZIP to collect token document-frequencies.
  No embedding, no Qdrant writes.
  Result is saved to an IDF checkpoint JSON so the pass can be skipped
  on repeated runs.

Pass 2 — embed + upsert
  Re-iterates ZIPs, builds BM25 sparse vectors from the IDF table,
  embeds dense vectors, and upserts both into czech_laws_v2.
  Skip logic: law_iri checked against Qdrant before opening each ZIP.

Run in Docker:
    docker compose exec backend python -m app.modules.czechia.ingestion.run_local_ingest_v2

Optional env overrides:
    ESBIRKA_DATA_DIR        path to ZIP directory        (default: /app/esbirka_data)
    IDF_CHECKPOINT_PATH     path to IDF JSON checkpoint  (default: /app/storage/idf_czech_laws_v2.json)
    BATCH_SIZE              chunks per embed/upsert batch (default: 64)
    FORCE_REINGEST          set to '1' to re-ingest already-ingested laws
    FORCE_REBUILD_IDF       set to '1' to rebuild IDF even if checkpoint exists
    BM25_MIN_DF             minimum document-frequency for IDF vocab (default: 2)
"""

from __future__ import annotations

import logging
import os
import re
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ── configuration ──────────────────────────────────────────────────────────────

ESBIRKA_DATA_DIR     = Path(os.environ.get("ESBIRKA_DATA_DIR", "esbirka_data"))
IDF_CHECKPOINT_PATH  = Path(os.environ.get("IDF_CHECKPOINT_PATH", "storage/idf_czech_laws_v2.json"))
BATCH_SIZE           = int(os.environ.get("BATCH_SIZE", "64"))
FORCE_REINGEST       = os.environ.get("FORCE_REINGEST", "0") == "1"
FORCE_REBUILD_IDF    = os.environ.get("FORCE_REBUILD_IDF", "0") == "1"
BM25_MIN_DF          = int(os.environ.get("BM25_MIN_DF", "2"))

# Filename pattern: Sb_{year}_{number}_{date}_IZ.zip
_ZIP_NAME_RE = re.compile(r"^Sb_(\d{4})_(\d+)_")


def _law_iri_from_zip_name(name: str) -> str | None:
    m = _ZIP_NAME_RE.match(name)
    if not m:
        return None
    year, number = m.group(1), m.group(2)
    return f"local:sb/{year}/{number}"


# ── Pass 1: build IDF table ────────────────────────────────────────────────────

def _build_idf_table(zip_files: list[Path]):
    """
    Scan all ZIPs, register every chunk text with IDFTableBuilder.
    Returns a finalized IDFTable.
    """
    from app.modules.czechia.ingestion.chunk_builder import build_chunks
    from app.modules.czechia.ingestion.local_loader import load_local_sb_zip
    from app.modules.czechia.ingestion.relation_index import RelationIndex
    from app.modules.czechia.ingestion.sparse_encoder import IDFTableBuilder

    builder = IDFTableBuilder()
    relation_index = RelationIndex()
    t0 = time.time()

    for i, zip_path in enumerate(zip_files, 1):
        law_iri = _law_iri_from_zip_name(zip_path.name)
        if law_iri is None:
            log.warning("  SKIP (bad name) %s", zip_path.name)
            continue
        try:
            doc_count = 0
            for frag_dict in load_local_sb_zip(zip_path):
                for chunk in build_chunks(frag_dict, relation_index):
                    builder.add_document(chunk.text)
                    doc_count += 1
            log.info("  [%d/%d] IDF scan %s — %d chunks", i, len(zip_files), zip_path.name, doc_count)
        except Exception as exc:
            log.error("  IDF scan FAILED %s — %s", zip_path.name, exc)

    idf_table = builder.build(min_df=BM25_MIN_DF)
    log.info(
        "IDF scan complete: n_docs=%d vocab=%d avg_dl=%.1f elapsed=%.1fs",
        idf_table.n_docs, idf_table.vocab_size, idf_table.avg_dl,
        time.time() - t0,
    )
    return idf_table


def _load_or_build_idf(zip_files: list[Path]):
    """
    Load IDF table from checkpoint if it exists and FORCE_REBUILD_IDF is not set.
    Otherwise run Pass 1 and save the result.
    """
    from app.modules.czechia.ingestion.sparse_encoder import IDFTable

    if not FORCE_REBUILD_IDF and IDF_CHECKPOINT_PATH.exists():
        log.info("Loading IDF checkpoint: %s", IDF_CHECKPOINT_PATH)
        return IDFTable.load(IDF_CHECKPOINT_PATH)

    log.info(
        "Starting Pass 1 — IDF scan of %d ZIPs%s",
        len(zip_files),
        " (FORCE_REBUILD_IDF=1)" if FORCE_REBUILD_IDF else "",
    )
    idf_table = _build_idf_table(zip_files)
    IDF_CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    idf_table.save(IDF_CHECKPOINT_PATH)
    log.info("IDF checkpoint saved: %s", IDF_CHECKPOINT_PATH)
    return idf_table


# ── Pass 2: embed + upsert ────────────────────────────────────────────────────

def run() -> None:
    # Deferred imports so settings validation fires only at runtime.
    from app.core.config import get_settings
    from app.modules.common.embeddings.provider import EmbeddingService
    from app.modules.czechia.ingestion.chunk_builder import build_chunks
    from app.modules.czechia.ingestion.embedder import CzechLawEmbedder
    from app.modules.czechia.ingestion.local_loader import load_local_sb_zip
    from app.modules.czechia.ingestion.qdrant_writer import CzechLawQdrantWriter
    from app.modules.czechia.ingestion.relation_index import RelationIndex
    from app.modules.czechia.ingestion.schemas import CzechLawChunk
    from app.modules.czechia.ingestion.sparse_encoder import CzechBM25Encoder

    settings = get_settings()

    # ── validate data dir ─────────────────────────────────────────────────
    if not ESBIRKA_DATA_DIR.exists():
        log.error("Data directory not found: %s", ESBIRKA_DATA_DIR.resolve())
        sys.exit(1)

    zip_files = sorted(ESBIRKA_DATA_DIR.glob("*.zip"))
    if not zip_files:
        log.warning("No *.zip files found in %s", ESBIRKA_DATA_DIR.resolve())
        return

    log.info("Found %d ZIP package(s) in %s", len(zip_files), ESBIRKA_DATA_DIR.resolve())
    if FORCE_REINGEST:
        log.warning("FORCE_REINGEST=1 — already-ingested check is disabled")

    # ── Pass 1: IDF table ─────────────────────────────────────────────────
    idf_table = _load_or_build_idf(zip_files)
    bm25_encoder = CzechBM25Encoder(idf_table)

    # ── services ──────────────────────────────────────────────────────────
    embedding_service = EmbeddingService(
        model_name=settings.embedding_model,
        provider_name=settings.embedding_provider,
        fallback_provider_name=settings.embedding_fallback_provider,
        hash_dimension=settings.embedding_hash_dimension,
    )
    embedder = CzechLawEmbedder(
        embedding_service=embedding_service,
        bm25_encoder=bm25_encoder,
    )

    qdrant_writer = CzechLawQdrantWriter(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
    )

    # ── health check ──────────────────────────────────────────────────────
    if not qdrant_writer.health_check():
        log.error("Qdrant unreachable at %s — aborting", settings.qdrant_url)
        sys.exit(1)

    qdrant_writer.ensure_collection(dimension=embedder.dimension)
    log.info(
        "Qdrant collection 'czech_laws_v2' ready  |  embedding: %s/%s  dim=%d  sparse=BM25(vocab=%d)",
        settings.embedding_provider, settings.embedding_model,
        embedder.dimension, idf_table.vocab_size,
    )

    relation_index = RelationIndex()

    # ── Pass 2: embed + upsert ────────────────────────────────────────────
    t0 = time.time()
    total_fragments = 0
    total_chunks    = 0
    total_upserted  = 0
    total_ok        = 0
    total_skipped   = 0
    total_failed    = 0

    for zip_path in zip_files:

        law_iri = _law_iri_from_zip_name(zip_path.name)
        if law_iri is None:
            log.warning("  ? SKIP %s — filename does not match Sb_YEAR_NUMBER_... pattern", zip_path.name)
            total_skipped += 1
            continue

        if not FORCE_REINGEST and qdrant_writer.is_law_ingested(law_iri):
            log.info("  → SKIP %s  (law_iri=%s already in czech_laws_v2)", zip_path.name, law_iri)
            total_skipped += 1
            continue

        log.info("  + INGEST %s  (law_iri=%s)", zip_path.name, law_iri)
        frag_count  = 0
        chunk_count = 0
        batch: list[CzechLawChunk] = []

        try:
            for frag_dict in load_local_sb_zip(zip_path):
                frag_count += 1
                chunks = build_chunks(frag_dict, relation_index)
                batch.extend(chunks)
                chunk_count += len(chunks)

                if len(batch) >= BATCH_SIZE:
                    embedded = embedder.embed_batch(batch)
                    qdrant_writer.upsert_batch(embedded)
                    total_upserted += len(batch)
                    batch = []

            # flush remainder
            if batch:
                embedded = embedder.embed_batch(batch)
                qdrant_writer.upsert_batch(embedded)
                total_upserted += len(batch)

            log.info("    ✓ done  fragments=%d  chunks=%d", frag_count, chunk_count)
            total_fragments += frag_count
            total_chunks    += chunk_count
            total_ok        += 1

        except Exception as exc:
            log.error("    ✗ FAILED %s — %s", zip_path.name, exc)
            total_failed += 1

    # ── summary ───────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    sep = "─" * 60
    print()
    print(sep)
    print("  HYBRID ZIP INGESTION (czech_laws_v2) COMPLETE")
    print(sep)
    print(f"  IDF checkpoint    : {IDF_CHECKPOINT_PATH}")
    print(f"  BM25 vocab size   : {idf_table.vocab_size:>8,}")
    print(f"  skipped           : {total_skipped}")
    print(f"  ingested OK       : {total_ok}")
    if total_failed:
        print(f"  FAILED            : {total_failed}")
    print(f"  TOTAL fragments   : {total_fragments:>8,}")
    print(f"  TOTAL chunks      : {total_chunks:>8,}")
    print(f"  upserted          : {total_upserted:>8,}")
    print(f"  elapsed (Pass 2)  : {elapsed:>7.1f}s")
    print(sep)


if __name__ == "__main__":
    run()
