"""
Chunk builder tests for Russian law ingestion — Step 2 verification.

Tests run against the actual corpus files via session-scoped fixtures that
parse + chunk each law once. Each test has a single clear assertion.

Tests are skipped (not failed) if the corpus directory is not found.
"""
from __future__ import annotations

import re
import uuid
import pytest
from pathlib import Path

# ---------------------------------------------------------------------------
# Corpus availability guard (mirrors test_parser.py)
# ---------------------------------------------------------------------------

_CORPUS_ROOT = Path("/app/Ruske_zakony")
_SK_PATH  = _CORPUS_ROOT / "Семейный кодекс Российской Федерации  от 29.12.1995 N 223-ФЗ-u.txt"
_TK_PATH  = _CORPUS_ROOT / "rest_of_the_codex_russia" / "Трудовой кодекс Российской Федерации  от 30.12.2001 N 197-ФЗ-u.txt"
_GK1_PATH = _CORPUS_ROOT / "Гражданский кодекс Российской Федерации (часть первая)  от 3-u.txt"

_CORPUS_AVAILABLE = _SK_PATH.exists() and _TK_PATH.exists() and _GK1_PATH.exists()

pytestmark = pytest.mark.skipif(
    not _CORPUS_AVAILABLE,
    reason="Corpus files not available at /app/Ruske_zakony — skipping chunk builder tests",
)

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from app.modules.russia.ingestion.loader import load_law_file
from app.modules.russia.ingestion.parser import parse_law
from app.modules.russia.ingestion.chunk_builder import build_chunks
from app.modules.russia.ingestion.schemas import ParseResult, RussianChunk

# ---------------------------------------------------------------------------
# Fixtures — parse + chunk each law once per session
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def sk_chunks() -> list[RussianChunk]:
    meta, raw = load_law_file(_SK_PATH)
    result = parse_law(meta, raw)
    return build_chunks(result)


@pytest.fixture(scope="session")
def tk_chunks() -> list[RussianChunk]:
    meta, raw = load_law_file(_TK_PATH)
    result = parse_law(meta, raw)
    return build_chunks(result)


@pytest.fixture(scope="session")
def gk1_chunks() -> list[RussianChunk]:
    meta, raw = load_law_file(_GK1_PATH)
    result = parse_law(meta, raw)
    return build_chunks(result)


# ---------------------------------------------------------------------------
# UUID validity
# ---------------------------------------------------------------------------

def test_tk_chunk_ids_are_valid_uuids(tk_chunks: list[RussianChunk]) -> None:
    """Every chunk_id must be a valid UUID string."""
    for chunk in tk_chunks:
        try:
            val = uuid.UUID(chunk.chunk_id)
        except ValueError:
            pytest.fail(f"Invalid UUID: {chunk.chunk_id!r} (fragment_id={chunk.fragment_id!r})")
        assert str(val) == chunk.chunk_id, f"UUID not normalised: {chunk.chunk_id!r}"


def test_sk_chunk_ids_are_valid_uuids(sk_chunks: list[RussianChunk]) -> None:
    """Every chunk_id in СК РФ must be a valid UUID string."""
    for chunk in sk_chunks:
        uuid.UUID(chunk.chunk_id)  # raises ValueError on invalid


# ---------------------------------------------------------------------------
# Determinism — same law → same chunk IDs across independent reruns
# ---------------------------------------------------------------------------

def test_tk_chunk_ids_are_deterministic(tk_chunks: list[RussianChunk]) -> None:
    """Re-building chunks from the same ParseResult must produce identical chunk_ids."""
    meta, raw = load_law_file(_TK_PATH)
    result2 = parse_law(meta, raw)
    chunks2 = build_chunks(result2)

    assert len(tk_chunks) == len(chunks2), "Different chunk count on second run"
    for i, (c1, c2) in enumerate(zip(tk_chunks, chunks2)):
        assert c1.chunk_id == c2.chunk_id, (
            f"chunk_id mismatch at index {i}: {c1.chunk_id!r} vs {c2.chunk_id!r}"
        )


# ---------------------------------------------------------------------------
# Uniqueness — no duplicate chunk_ids within a law
# ---------------------------------------------------------------------------

def test_tk_no_duplicate_chunk_ids(tk_chunks: list[RussianChunk]) -> None:
    """chunk_id values must be unique within ТК РФ."""
    ids = [c.chunk_id for c in tk_chunks]
    assert len(ids) == len(set(ids)), (
        f"Duplicate chunk_ids found in ТК РФ — {len(ids) - len(set(ids))} duplicates"
    )


def test_gk1_no_duplicate_chunk_ids(gk1_chunks: list[RussianChunk]) -> None:
    """chunk_id values must be unique within ГК РФ ч.1."""
    ids = [c.chunk_id for c in gk1_chunks]
    assert len(ids) == len(set(ids)), (
        f"Duplicate chunk_ids found in ГК РФ ч.1 — {len(ids) - len(set(ids))} duplicates"
    )


def test_no_duplicate_fragment_ids_in_tk(tk_chunks: list[RussianChunk]) -> None:
    """fragment_id values must be unique within ТК РФ."""
    fids = [c.fragment_id for c in tk_chunks]
    assert len(fids) == len(set(fids)), "Duplicate fragment_ids in ТК РФ"


# ---------------------------------------------------------------------------
# Ordering stability
# ---------------------------------------------------------------------------

def test_tk_chunks_ordered_by_fragment_id(tk_chunks: list[RussianChunk]) -> None:
    """Chunks must be in lexicographic fragment_id order (article order preserved)."""
    fids = [c.fragment_id for c in tk_chunks]
    assert fids == sorted(fids), (
        f"Chunks are not in fragment_id order: first violation near {fids[:5]}"
    )


def test_sk_chunks_ordered_by_fragment_id(sk_chunks: list[RussianChunk]) -> None:
    """Chunks in СК РФ must be in lexicographic fragment_id order."""
    fids = [c.fragment_id for c in sk_chunks]
    assert fids == sorted(fids)


# ---------------------------------------------------------------------------
# fragment_id format
# ---------------------------------------------------------------------------

# law_id can contain slashes (e.g. 'local:ru/gk/1'), so match greedily up to
# the last two fixed-width numeric segments
_FRAGMENT_ID_RE = re.compile(r'^.+/\d{6}/\d{4}$')


def test_tk_fragment_id_format(tk_chunks: list[RussianChunk]) -> None:
    """fragment_id must match '{law_id}/{article_position:06d}/{chunk_index:04d}'."""
    for chunk in tk_chunks[:50]:  # sample first 50 for speed
        assert _FRAGMENT_ID_RE.match(chunk.fragment_id), (
            f"Bad fragment_id format: {chunk.fragment_id!r}"
        )


def test_tk_fragment_id_law_id_prefix(tk_chunks: list[RussianChunk]) -> None:
    """All ТК РФ fragment_ids must start with 'local:ru/tk/'."""
    for chunk in tk_chunks:
        assert chunk.fragment_id.startswith("local:ru/tk/"), (
            f"Wrong law_id prefix in fragment_id: {chunk.fragment_id!r}"
        )


# ---------------------------------------------------------------------------
# Tombstone chunks
# ---------------------------------------------------------------------------

def test_tk_tombstone_articles_produce_tombstone_chunks(tk_chunks: list[RussianChunk]) -> None:
    """Tombstone articles must produce chunks with source_type='tombstone' and is_tombstone=True."""
    tombstone_chunks = [c for c in tk_chunks if c.is_tombstone]
    assert len(tombstone_chunks) >= 3, (
        f"Expected at least 3 tombstone chunks in ТК РФ, got {len(tombstone_chunks)}"
    )
    for chunk in tombstone_chunks:
        assert chunk.source_type == "tombstone", (
            f"Tombstone chunk has wrong source_type: {chunk.source_type!r}"
        )
        assert chunk.is_tombstone is True


def test_tk_article_7_is_tombstone_chunk(tk_chunks: list[RussianChunk]) -> None:
    """Ст.7 ТК РФ is repealed — its chunk must be tombstone with non-empty text."""
    art7 = [c for c in tk_chunks if c.article_num == "7"]
    assert len(art7) >= 1, "No chunks for ст.7 ТК РФ"
    for chunk in art7:
        assert chunk.is_tombstone is True
        assert chunk.source_type == "tombstone"
        assert len(chunk.text.strip()) > 0, "Tombstone chunk for ст.7 has empty text"


# ---------------------------------------------------------------------------
# Non-empty text
# ---------------------------------------------------------------------------

def test_tk_no_empty_chunk_text(tk_chunks: list[RussianChunk]) -> None:
    """Every chunk in ТК РФ must have non-empty text."""
    for chunk in tk_chunks:
        assert len(chunk.text.strip()) > 0, (
            f"Empty text in chunk fragment_id={chunk.fragment_id!r} "
            f"article={chunk.article_num} part_num={chunk.part_num}"
        )


def test_sk_no_empty_chunk_text(sk_chunks: list[RussianChunk]) -> None:
    """Every chunk in СК РФ must have non-empty text."""
    for chunk in sk_chunks:
        assert len(chunk.text.strip()) > 0, (
            f"Empty text in chunk fragment_id={chunk.fragment_id!r} article={chunk.article_num}"
        )


def test_gk1_no_empty_chunk_text(gk1_chunks: list[RussianChunk]) -> None:
    """Every chunk in ГК РФ ч.1 must have non-empty text."""
    for chunk in gk1_chunks:
        assert len(chunk.text.strip()) > 0, (
            f"Empty text in chunk fragment_id={chunk.fragment_id!r} article={chunk.article_num}"
        )


# ---------------------------------------------------------------------------
# Multi-part article → multiple ordered chunks
# ---------------------------------------------------------------------------

def test_gk1_multipart_article_produces_ordered_chunks(gk1_chunks: list[RussianChunk]) -> None:
    """
    A ГК РФ ч.1 article with multiple части must produce multiple chunks
    in ascending chunk_index order.

    Groups by fragment_id prefix (law_id/article_position) — unique per article —
    rather than article_num which may repeat in GK1 (e.g. decimal articles like 123.7).
    """
    # article_prefix = everything up to and including the article_position segment
    # fragment_id format: '{law_id}/{article_position:06d}/{chunk_index:04d}'
    # rsplit on '/' once to strip chunk_index
    by_article: dict[str, list[RussianChunk]] = {}
    for chunk in gk1_chunks:
        article_key = chunk.fragment_id.rsplit("/", 1)[0]  # strip chunk_index
        by_article.setdefault(article_key, []).append(chunk)

    multi = {key: chunks for key, chunks in by_article.items() if len(chunks) > 1}
    assert len(multi) >= 10, (
        f"Expected many multi-chunk articles in ГК РФ ч.1, got {len(multi)}"
    )

    for article_key, chunks in multi.items():
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(indices))), (
            f"chunk_index not sequential for {article_key}: {indices}"
        )


def test_gk1_article_1_chunk_index_starts_at_zero(gk1_chunks: list[RussianChunk]) -> None:
    """First chunk of ст.1 ГК РФ ч.1 must have chunk_index=0."""
    art1 = [c for c in gk1_chunks if c.article_num == "1"]
    assert len(art1) >= 1, "No chunks for ст.1 ГК РФ ч.1"
    assert art1[0].chunk_index == 0


# ---------------------------------------------------------------------------
# Metadata propagation
# ---------------------------------------------------------------------------

def test_tk_chunks_have_correct_law_short(tk_chunks: list[RussianChunk]) -> None:
    """All ТК РФ chunks must carry law_short='ТК РФ'."""
    for chunk in tk_chunks:
        assert chunk.law_short == "ТК РФ", f"Wrong law_short: {chunk.law_short!r}"


def test_sk_chunks_have_correct_law_id(sk_chunks: list[RussianChunk]) -> None:
    """All СК РФ chunks must carry law_id='local:ru/sk'."""
    for chunk in sk_chunks:
        assert chunk.law_id == "local:ru/sk", f"Wrong law_id: {chunk.law_id!r}"


def test_gk1_chunks_have_correct_law_id(gk1_chunks: list[RussianChunk]) -> None:
    """All ГК РФ ч.1 chunks must carry law_id='local:ru/gk/1'."""
    for chunk in gk1_chunks:
        assert chunk.law_id == "local:ru/gk/1", f"Wrong law_id: {chunk.law_id!r}"


def test_tk_chunks_source_type_only_valid_values(tk_chunks: list[RussianChunk]) -> None:
    """source_type must be exactly 'article' or 'tombstone'."""
    valid = {"article", "tombstone"}
    for chunk in tk_chunks:
        assert chunk.source_type in valid, (
            f"Invalid source_type {chunk.source_type!r} on fragment_id={chunk.fragment_id!r}"
        )


# ---------------------------------------------------------------------------
# Chunk count sanity
# ---------------------------------------------------------------------------

def test_sk_chunk_count_at_least_article_count(sk_chunks: list[RussianChunk]) -> None:
    """СК РФ must have at least as many chunks as articles (1 chunk min per article)."""
    meta, raw = load_law_file(_SK_PATH)
    result = parse_law(meta, raw)
    assert len(sk_chunks) >= result.article_count, (
        f"Fewer chunks ({len(sk_chunks)}) than articles ({result.article_count}) in СК РФ"
    )


def test_gk1_chunk_count_exceeds_article_count(gk1_chunks: list[RussianChunk]) -> None:
    """ГК РФ ч.1 has many multi-part articles — chunk count must exceed article count."""
    meta, raw = load_law_file(_GK1_PATH)
    result = parse_law(meta, raw)
    assert len(gk1_chunks) > result.article_count, (
        f"Expected more chunks ({len(gk1_chunks)}) than articles ({result.article_count}) in ГК РФ ч.1"
    )
