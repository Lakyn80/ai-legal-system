"""
Ingest locally downloaded e-Sbírka ZIP packages into Qdrant.

Scans ``esbirka_data/`` for all ``*.zip`` files, converts each to
CzechLawChunk via the existing pipeline (load_local_sb_zip → build_chunks),
embeds in batches, and upserts to the ``czech_laws`` Qdrant collection.

Skip logic:
  Before opening a ZIP, the law_iri is derived from its filename
  (e.g. Sb_2009_40_... → local:sb/2009/40) and checked against Qdrant.
  If points for that law_iri already exist, the ZIP is skipped.
  This makes repeated runs safe and fast — only new ZIPs are processed.

Run in Docker:
    docker compose exec backend python -m app.modules.czechia.ingestion.run_local_ingest

Optional env overrides:
    ESBIRKA_DATA_DIR   path to ZIP directory  (default: /app/esbirka_data)
    QDRANT_URL         Qdrant base URL        (default: from settings)
    BATCH_SIZE         chunks per embed/upsert batch  (default: 64)
    FORCE_REINGEST     set to '1' to skip the already-ingested check
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

ESBIRKA_DATA_DIR = Path(os.environ.get("ESBIRKA_DATA_DIR", "esbirka_data"))
BATCH_SIZE       = int(os.environ.get("BATCH_SIZE", "64"))
FORCE_REINGEST   = os.environ.get("FORCE_REINGEST", "0") == "1"

# Filename pattern: Sb_{year}_{number}_{date}_IZ.zip
_ZIP_NAME_RE = re.compile(r"^Sb_(\d{4})_(\d+)_")


def _law_iri_from_zip_name(name: str) -> str | None:
    """
    Derive law_iri from ZIP filename without opening the archive.

    Sb_2009_40_2026-01-01_IZ.zip  →  local:sb/2009/40
    Returns None if the filename does not match the expected pattern.
    """
    m = _ZIP_NAME_RE.match(name)
    if not m:
        return None
    year, number = m.group(1), m.group(2)
    return f"local:sb/{year}/{number}"


# ── runner ─────────────────────────────────────────────────────────────────────

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

    # ── build embedding + qdrant services ─────────────────────────────────
    embedding_service = EmbeddingService(
        model_name=settings.embedding_model,
        provider_name=settings.embedding_provider,
        fallback_provider_name=settings.embedding_fallback_provider,
        hash_dimension=settings.embedding_hash_dimension,
    )
    embedder = CzechLawEmbedder(embedding_service)

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
        "Qdrant collection 'czech_laws' ready  |  embedding: %s/%s  dim=%d",
        settings.embedding_provider, settings.embedding_model, embedder.dimension,
    )

    # ── empty relation index (phase-2 will populate) ──────────────────────
    relation_index = RelationIndex()

    # ── ingest each ZIP ───────────────────────────────────────────────────
    t0 = time.time()
    total_fragments = 0
    total_chunks    = 0
    total_upserted  = 0
    total_ok        = 0
    total_skipped   = 0
    total_failed    = 0

    for zip_path in zip_files:

        # ── derive law_iri from filename and check Qdrant ─────────────────
        law_iri = _law_iri_from_zip_name(zip_path.name)

        if law_iri is None:
            log.warning("  ? SKIP %s — filename does not match Sb_YEAR_NUMBER_... pattern", zip_path.name)
            total_skipped += 1
            continue

        if not FORCE_REINGEST and qdrant_writer.is_law_ingested(law_iri):
            log.info("  → SKIP %s  (law_iri=%s already in Qdrant)", zip_path.name, law_iri)
            total_skipped += 1
            continue

        # ── process new ZIP ───────────────────────────────────────────────
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

            log.info(
                "    ✓ done  fragments=%d  chunks=%d",
                frag_count, chunk_count,
            )
            total_fragments += frag_count
            total_chunks    += chunk_count
            total_ok        += 1

        except Exception as exc:
            log.error("    ✗ FAILED %s — %s", zip_path.name, exc)
            total_failed += 1

    # ── summary ───────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    sep = "─" * 56
    print()
    print(sep)
    print("  LOCAL ZIP INGESTION COMPLETE")
    print(sep)
    print(f"  skipped (already ingested) : {total_skipped}")
    print(f"  ingested OK                : {total_ok}")
    if total_failed:
        print(f"  FAILED                     : {total_failed}")
    print(f"  TOTAL fragments            : {total_fragments:>8,}")
    print(f"  TOTAL chunks               : {total_chunks:>8,}")
    print(f"  upserted                   : {total_upserted:>8,}")
    print(f"  elapsed                    : {elapsed:>7.1f}s")
    print(sep)


if __name__ == "__main__":
    run()
