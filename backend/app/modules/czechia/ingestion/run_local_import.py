"""
Batch runner for locally downloaded e-Sbírka ZIP packages.

Scans ``esbirka_data/`` for all ``*.zip`` files, reads each one directly
(no extraction to disk), converts fragments to CzechLawChunk via build_chunks(),
and prints a per-law and grand-total summary.  Nothing is written to Qdrant.

Run on host (from project root ai-legal-system/):
    python -m backend.app.modules.czechia.ingestion.run_local_import

Run in Docker:
    docker compose exec backend python -m app.modules.czechia.ingestion.run_local_import
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from app.modules.czechia.ingestion.chunk_builder import build_chunks
from app.modules.czechia.ingestion.local_loader import load_local_sb_zip
from app.modules.czechia.ingestion.relation_index import RelationIndex

# ── configuration ─────────────────────────────────────────────────────────────

# In Docker: /app/esbirka_data  (mounted via docker-compose volumes)
# On host:   esbirka_data/       (relative to project root)
_DEFAULT_DATA_DIR = os.environ.get("ESBIRKA_DATA_DIR", "esbirka_data")
ESBIRKA_DATA_DIR = Path(_DEFAULT_DATA_DIR)

# ── logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ── runner ────────────────────────────────────────────────────────────────────

def run(data_dir: Path = ESBIRKA_DATA_DIR) -> None:
    if not data_dir.exists():
        log.error("Data directory not found: %s", data_dir.resolve())
        sys.exit(1)

    zip_files = sorted(data_dir.glob("*.zip"))
    if not zip_files:
        log.warning("No *.zip files found in %s", data_dir.resolve())
        return

    log.info("Found %d ZIP package(s) in %s", len(zip_files), data_dir.resolve())
    print()

    relation_index = RelationIndex()   # empty — phase-2 graph pass will populate

    total_fragments = 0
    total_chunks    = 0
    total_ok        = 0
    total_failed    = 0

    for zip_path in zip_files:
        fragment_count = 0
        chunk_count    = 0
        law_iri        = ""

        try:
            for frag_dict in load_local_sb_zip(zip_path):
                fragment_count += 1
                if not law_iri:
                    law_iri = frag_dict.get("law_iri", "")
                chunk_count += len(build_chunks(frag_dict, relation_index))

            print(f"  file      : {zip_path.name}")
            print(f"  law_iri   : {law_iri}")
            print(f"  fragments : {fragment_count}")
            print(f"  chunks    : {chunk_count}")
            print()

            total_fragments += fragment_count
            total_chunks    += chunk_count
            total_ok        += 1

        except Exception as exc:
            log.error("FAILED %s — %s", zip_path.name, exc)
            total_failed += 1
            print()

    # ── summary ───────────────────────────────────────────────────────────────
    separator = "─" * 50
    print(separator)
    print(f"  packages processed : {total_ok}")
    if total_failed:
        print(f"  packages FAILED    : {total_failed}")
    print(f"  TOTAL fragments    : {total_fragments:,}")
    print(f"  TOTAL chunks       : {total_chunks:,}")
    print(separator)


if __name__ == "__main__":
    run()
