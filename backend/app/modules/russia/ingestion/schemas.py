"""
Parsing data models for Russian law ingestion pipeline.

These dataclasses represent the output of the loader + parser stages only.
They carry no Qdrant, embedding, or retrieval concerns.

Downstream stages (chunk_builder, embedder, qdrant_writer) will import these
and produce their own output types (RussianChunk, EmbeddedChunk, IngestReport).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LawMetadata:
    """Header-level metadata extracted from the KonsultantPlus file header."""

    law_id: str
    """Canonical IRI, e.g. 'local:ru/tk'. Derived from filename by loader."""

    law_title: str
    """Full official title, e.g. 'Трудовой кодекс Российской Федерации'."""

    law_short: str
    """Common abbreviation, e.g. 'ТК РФ'. Derived from law_id alias map."""

    law_number: str | None
    """Federal law number, e.g. '197-ФЗ'. None if not found in header."""

    law_date: str | None
    """Adoption date string, e.g. '30.12.2001'. None if not found in header."""

    source_file: str
    """Basename of the source file."""

    ingest_timestamp: str
    """ISO-8601 UTC timestamp set at load time."""


@dataclass
class RussianArticlePart:
    """
    A single numbered part (часть) of an article, or the unnumbered intro text.

    Part splitting is applied only when the article text is long enough to warrant it
    (> 700 chars clean) AND the article contains explicit numbered parts ('1. 2. 3.').

    Short articles and tombstones are always stored as a single part with part_num=None.
    """

    part_num: int | None
    """Numeric label from the source ('1.' → 1, '2.' → 2). None for intro/unnumbered."""

    text: str
    """Clean text of this part. Editor noise already removed."""

    is_intro: bool
    """
    True when part_num is None and this part precedes the first numbered part.
    False for all numbered parts and for single-part articles.
    """


@dataclass
class RussianArticle:
    """
    A single parsed article (статья) from a Russian law.

    The `parts` list contains the logical sub-units. For short articles or tombstones,
    `parts` always has exactly one entry. For long articles with numbered parts,
    `parts` corresponds to each detected numbered part plus an optional intro.

    The `raw_text` field holds the full article text after noise removal but before
    part splitting. Useful for diagnostics and full-text indexing.
    """

    law_id: str
    """Canonical IRI inherited from LawMetadata."""

    article_num: str
    """
    Article number as a string. Always string — never float — to handle
    decimal articles like '19.1', '22.2' without precision loss.
    """

    heading: str
    """
    Article heading extracted from the Статья line, e.g.
    'Расторжение трудового договора по инициативе работодателя'.
    Empty string if the article has no heading (rare).
    For tombstones this will contain 'Утратила силу...' text.
    """

    razdel: str | None
    """
    Current Раздел label at the time this article was parsed, e.g.
    'I. ОБЩИЕ ПОЛОЖЕНИЯ'. None if the law has no Раздел hierarchy.
    """

    glava: str
    """
    Current Глава label at the time this article was parsed, e.g.
    'Глава 3. УСЛОВИЯ И ПОРЯДОК ЗАКЛЮЧЕНИЯ БРАКА'.
    Empty string if no Глава has been seen yet (unusual but possible).
    """

    parts: list[RussianArticlePart]
    """Ordered list of article parts. Never empty — at minimum one part."""

    raw_text: str
    """Full article body text after noise removal, before part splitting."""

    is_tombstone: bool
    """
    True when the article has been repealed. Detected in Pass 2 (tombstone detector)
    which runs only on lines that survived Pass 1 (noise filter).

    Tombstone articles are still indexed in Qdrant with source_type='tombstone'.
    They must NOT be silently discarded — callers must be able to inform users
    that a queried article no longer has legal force.
    """

    article_position: int
    """
    0-based sequential position of this article in file order.
    Assigned by the parser's internal counter at flush time.
    Used to derive fragment_id in chunk_builder.
    """

    source_file: str
    """Basename of the source file, inherited from LawMetadata."""

    parse_errors: list[str] = field(default_factory=list)
    """Non-fatal warnings encountered while parsing this specific article."""


@dataclass
class ParseResult:
    """
    Full output of parsing one law file.

    Produced by parser.parse_file() and consumed by chunk_builder and diagnostics.
    """

    metadata: LawMetadata
    """Law-level metadata extracted from the file header."""

    articles: list[RussianArticle]
    """All articles in file order. Includes tombstones."""

    article_count: int
    """Total number of articles parsed (including tombstones)."""

    tombstone_count: int
    """Number of articles with is_tombstone=True."""

    parse_error_count: int
    """Total number of non-fatal parse warnings across all articles."""

    parse_errors: list[str]
    """Law-level parse warnings (not article-specific)."""


@dataclass
class RussianChunk:
    """
    A single retrieval-ready chunk produced by chunk_builder.

    One chunk = one RussianArticlePart. For short articles and tombstones this
    means one chunk per article. For long articles with numbered части this means
    one chunk per detected part plus an optional intro chunk.

    chunk_id is a deterministic UUID5 derived from fragment_id so that re-ingesting
    the same corpus produces byte-identical IDs. Qdrant uses chunk_id as the point ID.
    """

    chunk_id: str
    """UUID5 derived from fragment_id. Stable across reruns."""

    law_id: str
    """Canonical IRI, e.g. 'local:ru/tk'. Inherited from LawMetadata."""

    law_title: str
    """Full official title. Inherited from LawMetadata."""

    law_short: str
    """Common abbreviation, e.g. 'ТК РФ'. Inherited from LawMetadata."""

    article_num: str
    """Article number as string, e.g. '81', '19.1'."""

    article_heading: str
    """Article heading text. May contain repeal declaration for tombstones."""

    part_num: int | None
    """Numeric label of this part (1, 2, 3 ...). None for intro or single-part articles."""

    razdel: str | None
    """Раздел label at parse time. None if law has no Раздел hierarchy."""

    glava: str
    """Глава label at parse time. Empty string if no Глава has been seen."""

    text: str
    """Clean chunk text. Never empty."""

    chunk_index: int
    """0-based index of this chunk within its article. Used in fragment_id."""

    fragment_id: str
    """
    Lexsortable source-order ID: '{law_id}/{article_position:06d}/{chunk_index:04d}'.
    Determines chunk_id via UUID5 and preserves file order for pagination.
    """

    source_type: str
    """'article' or 'tombstone'. Tombstone chunks must remain retrievable."""

    source_file: str
    """Basename of the source file. Inherited from RussianArticle."""

    is_tombstone: bool
    """True when the originating article was repealed."""
