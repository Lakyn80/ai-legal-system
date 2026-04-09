"""
Legal-aware chunker for Czech law fragments.

Strategy
────────
- If a fragment's text fits within chunk_size, it becomes a single chunk
  (chunk_index=0).  Legal boundaries are preserved exactly.
- If the text exceeds chunk_size, it is split with RecursiveCharacterTextSplitter
  using legal-appropriate separators.  Each child chunk retains the parent
  fragment_id so that graph traversal can reconstruct:

      chunk_id → fragment_id → outgoing_link_ids → linked fragment_ids

chunk_id is deterministic:
    uuid5(NAMESPACE_URL, f"{fragment_id}:{chunk_index}")

This makes ingestion idempotent — re-running produces identical IDs so
Qdrant upsert simply overwrites existing points without duplication.

Relation hooks populated in phase 1:
    definition_refs  — definition IDs whose law_links reference this fragment

Relation hooks left empty (populated in phase 2 graph pass):
    outgoing_link_ids, incoming_link_ids, term_refs, metadata_ref, relation_keys
"""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.modules.czechia.ingestion.relation_index import RelationIndex
from app.modules.czechia.ingestion.schemas import CzechLawChunk

# Separators ordered from most- to least-preferred split point for legal text.
_LEGAL_SEPARATORS: list[str] = ["\n\n", "\n", ". ", "; ", " ", ""]


def _make_chunk_id(fragment_id: str, chunk_index: int) -> str:
    """Deterministic chunk ID — consistent across restarts and re-ingestion."""
    return str(uuid5(NAMESPACE_URL, f"{fragment_id}:{chunk_index}"))


def build_chunks(
    fragment: dict,
    relation_index: RelationIndex,
    chunk_size: int = 1200,
    chunk_overlap: int = 180,
) -> list[CzechLawChunk]:
    """
    Convert a single law_fragment dict into one or more CzechLawChunk records.

    Returns an empty list only if the fragment text is empty (caller should
    have filtered via should_ingest() before calling this).
    """
    fragment_id: str = fragment.get("id", "")
    law_iri: str = fragment.get("law_iri", "")
    text: str = (fragment.get("text") or "").strip()
    paragraph: str | None = fragment.get("paragraph")

    if not text:
        return []

    definition_refs = relation_index.get_definition_refs(fragment_id)

    # ── single chunk (most common case for short legal citations) ─────────
    if len(text) <= chunk_size:
        return [
            CzechLawChunk(
                chunk_id=_make_chunk_id(fragment_id, 0),
                fragment_id=fragment_id,
                law_iri=law_iri,
                text=text,
                chunk_index=0,
                paragraph=paragraph,
                definition_refs=definition_refs,
            )
        ]

    # ── split long fragments ──────────────────────────────────────────────
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=_LEGAL_SEPARATORS,
    )
    parts = splitter.split_text(text)

    return [
        CzechLawChunk(
            chunk_id=_make_chunk_id(fragment_id, i),
            fragment_id=fragment_id,
            law_iri=law_iri,
            text=part,
            chunk_index=i,
            paragraph=paragraph,
            definition_refs=definition_refs,
        )
        for i, part in enumerate(parts)
    ]
