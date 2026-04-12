"""
Retrieval result schemas for Russian law retrieval.

Step 5: RussianChunkResult, ArticleLookupResult  (exact lookup)
Step 6: RussianSearchResult                       (dense search)

BM25 query-time schemas and topic-retrieval schemas are out of scope for M1.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RussianChunkResult:
    """
    A single chunk returned by exact lookup.

    Corresponds 1:1 to a Qdrant point stored by qdrant_writer.
    """

    chunk_id: str
    """UUID5 identifier of this chunk."""

    law_id: str
    """Canonical law IRI, e.g. 'local:ru/tk'."""

    law_short: str
    """Common abbreviation, e.g. 'ТК РФ'."""

    article_num: str
    """Article number as string, e.g. '81', '19.1'."""

    article_heading: str
    """Article heading text. Contains repeal declaration for tombstones."""

    part_num: int | None
    """Part number within the article, or None for single-part / intro chunks."""

    chunk_index: int
    """0-based position within the article's chunks."""

    razdel: str | None
    """Раздел label at parse time. None if law has no Раздел hierarchy."""

    glava: str
    """Глава label at parse time. Empty string if no Глава."""

    text: str
    """Clean chunk text."""

    fragment_id: str
    """Lexsortable source-order ID: '{law_id}/{article_position:06d}/{chunk_index:04d}'."""

    source_type: str
    """'article' or 'tombstone'."""

    is_tombstone: bool
    """True when the originating article was repealed."""

    source_file: str
    """Basename of the source file."""


@dataclass
class ArticleLookupResult:
    """
    Result of an exact article lookup.

    A successful lookup returns all chunks for the requested article in
    ascending chunk_index order. A failed lookup (article not found) returns
    an empty chunks list and hit=False.
    """

    hit: bool
    """True when at least one chunk was found for the requested article."""

    law_id: str
    """Canonical law IRI that was queried."""

    article_num: str
    """Article number that was queried."""

    chunks: list[RussianChunkResult]
    """
    All chunks for this article in chunk_index order.
    Empty when hit=False.
    """

    is_tombstone: bool
    """
    True when the article exists but has been repealed.
    False when the article is active or when hit=False.
    """

    article_heading: str
    """
    Article heading extracted from the first chunk.
    Empty string when hit=False.
    """

    @property
    def full_text(self) -> str:
        """Concatenate all chunk texts in order, separated by newlines."""
        return "\n\n".join(c.text for c in self.chunks)

    @property
    def part_count(self) -> int:
        """Number of chunks (parts) in this article."""
        return len(self.chunks)


@dataclass
class RussianSearchResult:
    """
    A single chunk returned by dense vector search, with a similarity score.

    Produced by RussianDenseRetriever and returned in score-descending order.
    All fields mirror the Qdrant payload; score is the cosine similarity from
    the vector query.
    """

    score: float
    """Cosine similarity score from Qdrant, range [0, 1] for normalised vectors."""

    chunk_id: str
    law_id: str
    law_short: str
    article_num: str
    article_heading: str
    part_num: int | None
    chunk_index: int
    razdel: str | None
    glava: str
    text: str
    fragment_id: str
    source_type: str
    is_tombstone: bool
    source_file: str
