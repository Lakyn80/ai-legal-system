"""
Phase 1 relation index for Czech law ingestion.

Loads metadata, terms, and definitions from rag_legal_dataset.json into
memory-resident lookup maps that are attached to fragments during chunking.

Memory estimate (phase 1):
  metadata   :  46k records × ~150 B  ≈   7 MB
  terms      :  29k records × ~100 B  ≈   3 MB
  definitions:  27k records × ~300 B  ≈   8 MB  (+ fragment→def index)
  Total                               < 50 MB

Links (5.4 M records) are NOT loaded in phase 1 to avoid excessive memory
usage (~2–3 GB).  The architecture supports adding them in phase 2 via
build_link_index() (see Phase 2 extension points below).

Phase 2 extension points
────────────────────────
def build_link_index(filepath: Path) -> dict[str, list[str]]:
    '''Return {source_iri: [target_iris]} from the links section.
    Memory: ~2-3 GB depending on IRI lengths — use chunked processing
    or a persistent store (SQLite / Redis) rather than a plain dict.'''

def build_metadata_join(filepath: Path) -> dict[str, str]:
    '''Return {akt_iri_prefix: metadata_law_id} so that fragment IRIs
    of the form esel-esb:eli/cz/sb/YEAR/NUMBER/... can be joined to
    the matching metadata entry via prefix matching.'''

def attach_term_refs(index: RelationIndex, filepath: Path) -> None:
    '''Populate index.term_refs_by_fragment by joining terms → definitions
    → fragment IRIs once a term-to-definition mapping file is available.'''
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from app.modules.czechia.ingestion.loader import (
    stream_definitions,
    stream_metadata,
    stream_terms,
)


@dataclass
class MetadataEntry:
    law_id: str   # esel-esb:právní-akt-metadata/N
    citace: str   # e.g. "8/1918 Sb."
    name: str     # full law title


@dataclass
class TermEntry:
    id: str       # term IRI
    name: str     # Czech term label


@dataclass
class RelationIndex:
    """
    In-memory relation index built from non-fragment sections of the dataset.

    Used during chunking (build_chunks) to attach relation hooks to each
    CzechLawChunk before it is embedded and stored in Qdrant.
    """

    # metadata_law_id → MetadataEntry
    metadata_by_id: dict[str, MetadataEntry] = field(default_factory=dict)

    # term_iri → TermEntry
    terms_by_iri: dict[str, TermEntry] = field(default_factory=dict)

    # fragment_iri → list of definition IDs (as strings) that reference it
    definitions_by_fragment: dict[str, list[str]] = field(default_factory=dict)

    def get_definition_refs(self, fragment_id: str) -> list[str]:
        """Return definition IDs that reference the given fragment IRI."""
        return self.definitions_by_fragment.get(fragment_id, [])


def build_relation_index(filepath: Path) -> RelationIndex:
    """
    Read metadata, terms, and definitions sections from the dataset file
    and return a populated RelationIndex.

    Opens the file three times (one pass per section) — all sections fit
    well within 50 MB of RAM so this is safe for long-running ingestion.
    """
    index = RelationIndex()

    # ── metadata ──────────────────────────────────────────────────────────
    print("  [relation_index] Loading metadata...", end=" ", flush=True)
    for item in stream_metadata(filepath):
        law_id = item.get("law_id", "")
        if law_id:
            index.metadata_by_id[law_id] = MetadataEntry(
                law_id=law_id,
                citace=item.get("citace", ""),
                name=item.get("name", ""),
            )
    print(f"{len(index.metadata_by_id):,}")

    # ── terms ─────────────────────────────────────────────────────────────
    print("  [relation_index] Loading terms...", end=" ", flush=True)
    for item in stream_terms(filepath):
        iri = item.get("id", "")
        if iri:
            index.terms_by_iri[iri] = TermEntry(
                id=iri,
                name=item.get("name", ""),
            )
    print(f"{len(index.terms_by_iri):,}")

    # ── definitions → fragment reverse index ──────────────────────────────
    print("  [relation_index] Indexing definitions...", end=" ", flush=True)
    def_count = 0
    for item in stream_definitions(filepath):
        def_id = item.get("id")
        law_links: list[str] = item.get("law_links", []) or []
        if def_id is None:
            continue
        def_id_str = str(def_id)
        for frag_iri in law_links:
            index.definitions_by_fragment.setdefault(frag_iri, []).append(def_id_str)
        def_count += 1
    print(
        f"{def_count:,} definitions → "
        f"{len(index.definitions_by_fragment):,} fragment refs"
    )

    return index
