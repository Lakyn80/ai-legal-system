"""
Chunk builder for Russian law ingestion pipeline.

Pipeline position: parser → **chunk_builder** → embedder → qdrant_writer

Responsibilities:
- Convert ParseResult (articles + parts) into a flat list of RussianChunk objects
- Assign deterministic chunk_id via UUID5(NAMESPACE_URL, fragment_id)
- Assign deterministic fragment_id: '{law_id}/{article_position:06d}/{chunk_index:04d}'
- Set source_type to 'tombstone' for repealed articles, 'article' otherwise
- Guarantee chunk text is never empty (enforced by assertion)

Does NOT:
- Produce embeddings
- Write to Qdrant
- Apply any BM25 / sparse encoding
- Import any retrieval modules
"""
from __future__ import annotations

import logging
import uuid

from app.modules.russia.ingestion.schemas import (
    ParseResult,
    RussianChunk,
)

log = logging.getLogger(__name__)

# Stable UUID namespace for all Russian law chunks.
# Using NAMESPACE_URL so that fragment_id strings (which look like paths/IRIs)
# map cleanly to the intended semantic of a URL namespace.
_UUID_NAMESPACE = uuid.NAMESPACE_URL

_SOURCE_TYPE_ARTICLE   = "article"
_SOURCE_TYPE_TOMBSTONE = "tombstone"


def build_chunks(result: ParseResult) -> list[RussianChunk]:
    """
    Build a flat, ordered list of RussianChunk objects from a ParseResult.

    Mapping:
        ParseResult → [RussianChunk, ...]
        one RussianArticlePart → one RussianChunk

    Args:
        result: ParseResult produced by parser.parse_law()

    Returns:
        List of RussianChunk in strict article-then-part order.
        The list is stable and deterministic — re-running on the same corpus
        produces identical chunk_id values.

    Raises:
        AssertionError: if any chunk would have empty text (programming error in parser).
    """
    meta = result.metadata
    chunks: list[RussianChunk] = []

    for article in result.articles:
        source_type = _SOURCE_TYPE_TOMBSTONE if article.is_tombstone else _SOURCE_TYPE_ARTICLE

        for chunk_index, part in enumerate(article.parts):
            # fragment_id encodes source order lexicographically
            fragment_id = (
                f"{article.law_id}"
                f"/{article.article_position:06d}"
                f"/{chunk_index:04d}"
            )

            # chunk_id is fully determined by fragment_id — reruns produce same UUID
            chunk_id = str(uuid.uuid5(_UUID_NAMESPACE, fragment_id))

            # Text must never be empty — catch any parser regression early
            assert part.text.strip(), (
                f"Empty chunk text for {fragment_id} — "
                f"article {article.article_num} part_num={part.part_num}"
            )

            chunk = RussianChunk(
                chunk_id=chunk_id,
                law_id=article.law_id,
                law_title=meta.law_title,
                law_short=meta.law_short,
                article_num=article.article_num,
                article_heading=article.heading,
                part_num=part.part_num,
                razdel=article.razdel,
                glava=article.glava,
                text=part.text,
                chunk_index=chunk_index,
                fragment_id=fragment_id,
                source_type=source_type,
                source_file=article.source_file,
                is_tombstone=article.is_tombstone,
            )
            chunks.append(chunk)

    log.info(
        "chunk_builder.done law_id=%r chunks=%d tombstone_chunks=%d",
        meta.law_id,
        len(chunks),
        sum(1 for c in chunks if c.is_tombstone),
    )

    return chunks
