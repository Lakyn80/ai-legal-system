from __future__ import annotations

from pydantic import BaseModel, Field


class CzechLawChunk(BaseModel):
    """
    Internal record for a single retrievable Czech law chunk.

    Designed for phase 1 vector ingestion with relation hooks
    that enable future graph-aware retrieval in phase 2 without
    requiring a schema migration.
    """

    chunk_id: str       # deterministic: uuid5(fragment_id:chunk_index)
    fragment_id: str    # original IRI from law_fragments, e.g. esel-esb:eli/cz/sb/...
    law_iri: str        # právní-akt-fragment IRI
    text: str           # text content used for embedding
    chunk_index: int    # position within the parent fragment (0-based)
    source_type: str = "law_fragment"

    # ── Phase 1 relation hooks (populated where derivable) ─────────────────
    metadata_ref: str | None = None
    # ^ metadata law_id (e.g. esel-esb:právní-akt-metadata/N) if linkable via
    #   IRI prefix join — None in phase 1, populated in phase 2.

    definition_refs: list[str] = Field(default_factory=list)
    # ^ definition IDs (as strings) whose law_links reference this fragment_id.
    #   Populated in phase 1 from the definitions section of the dataset.

    # ── Phase 2 relation hooks (empty in phase 1, schema-ready) ───────────
    outgoing_link_ids: list[str] = Field(default_factory=list)
    # ^ target fragment IRIs from the links section (source → target).

    incoming_link_ids: list[str] = Field(default_factory=list)
    # ^ source fragment IRIs that point to this fragment (reverse links).

    term_refs: list[str] = Field(default_factory=list)
    # ^ term IRIs (from cvs-termín) related to this fragment.

    relation_keys: list[str] = Field(default_factory=list)
    # ^ arbitrary graph edge keys for phase 2 graph traversal.


class EmbeddedLawChunk(BaseModel):
    """A CzechLawChunk paired with its embedding vector, ready for Qdrant upsert."""

    chunk: CzechLawChunk
    vector: list[float]
