"""
Exact lookup tests for Russian law retrieval — Step 5 verification.

Requires russian_laws_v1 to be populated (run Step 4 ingestion first).
Tests are skipped if Qdrant is not reachable or collection is absent.

All three milestone laws are tested:
  - ст. 81 ТК РФ (active, single-chunk)
  - ст. 1 СК РФ  (active)
  - ст. 169 ГК РФ ч.1 (active)
  - ст. 7 ТК РФ  (tombstone)
  - ст. 999 ТК РФ (nonexistent → no-hit)
  - cross-law isolation: TK article not returned for SK law_id
"""
from __future__ import annotations

import os
import pytest
from pathlib import Path

# ---------------------------------------------------------------------------
# Availability guard
# ---------------------------------------------------------------------------

QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
COLLECTION_NAME = "russian_laws_v1"


def _collection_ready() -> bool:
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(url=QDRANT_URL, timeout=10)
        if not client.collection_exists(COLLECTION_NAME):
            return False
        return client.count(COLLECTION_NAME, exact=True).count > 0
    except Exception:
        return False


_READY = _collection_ready()

pytestmark = pytest.mark.skipif(
    not _READY,
    reason=f"{COLLECTION_NAME} not populated — run M1 corpus ingest first",
)

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from app.modules.russia.retrieval.exact_lookup import RussianExactLookup
from app.modules.russia.retrieval.service import RussianRetrievalService
from app.modules.russia.retrieval.schemas import ArticleLookupResult, RussianChunkResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def lookup() -> RussianExactLookup:
    return RussianExactLookup(url=QDRANT_URL)


@pytest.fixture(scope="session")
def service() -> RussianRetrievalService:
    from app.core.config import get_settings
    from app.modules.common.embeddings.provider import EmbeddingService
    s = get_settings()
    emb = EmbeddingService(
        model_name=s.embedding_model,
        provider_name=s.embedding_provider,
        hash_dimension=s.embedding_hash_dimension,
    )
    return RussianRetrievalService(embedding_service=emb, qdrant_url=QDRANT_URL)


# ---------------------------------------------------------------------------
# ст. 81 ТК РФ — active article
# ---------------------------------------------------------------------------

def test_tk_article_81_hit(lookup: RussianExactLookup) -> None:
    """ст. 81 ТК РФ must be found."""
    result = lookup.get_article(law_id="local:ru/tk", article_num="81")
    assert result.hit is True, "ст.81 ТК РФ not found in russian_laws_v1"


def test_tk_article_81_correct_law_id(lookup: RussianExactLookup) -> None:
    """Result for ст. 81 ТК РФ must carry law_id='local:ru/tk'."""
    result = lookup.get_article("local:ru/tk", "81")
    assert result.law_id == "local:ru/tk"


def test_tk_article_81_heading_contains_rastorzhenie(lookup: RussianExactLookup) -> None:
    """ст. 81 heading must contain 'Расторжение'."""
    result = lookup.get_article("local:ru/tk", "81")
    assert "Расторжение" in result.article_heading, (
        f"Unexpected heading: {result.article_heading!r}"
    )


def test_tk_article_81_not_tombstone(lookup: RussianExactLookup) -> None:
    """ст. 81 ТК РФ is active — must not be flagged as tombstone."""
    result = lookup.get_article("local:ru/tk", "81")
    assert result.is_tombstone is False


def test_tk_article_81_has_nonempty_text(lookup: RussianExactLookup) -> None:
    """ст. 81 ТК РФ must have non-empty full_text."""
    result = lookup.get_article("local:ru/tk", "81")
    assert len(result.full_text.strip()) > 0


def test_tk_article_81_chunks_are_russian_chunk_results(lookup: RussianExactLookup) -> None:
    """All chunks must be RussianChunkResult instances."""
    result = lookup.get_article("local:ru/tk", "81")
    for chunk in result.chunks:
        assert isinstance(chunk, RussianChunkResult)


# ---------------------------------------------------------------------------
# ст. 1 СК РФ — active article
# ---------------------------------------------------------------------------

def test_sk_article_1_hit(lookup: RussianExactLookup) -> None:
    """ст. 1 СК РФ must be found."""
    result = lookup.get_article("local:ru/sk", "1")
    assert result.hit is True, "ст.1 СК РФ not found"


def test_sk_article_1_heading(lookup: RussianExactLookup) -> None:
    """ст. 1 СК РФ heading must mention 'семейного' or 'начала'."""
    result = lookup.get_article("local:ru/sk", "1")
    heading_lower = result.article_heading.lower()
    assert "семейного" in heading_lower or "начала" in heading_lower, (
        f"Unexpected heading: {result.article_heading!r}"
    )


def test_sk_article_1_not_tombstone(lookup: RussianExactLookup) -> None:
    result = lookup.get_article("local:ru/sk", "1")
    assert result.is_tombstone is False


# ---------------------------------------------------------------------------
# ст. 169 ГК РФ ч.1 — active article
# ---------------------------------------------------------------------------

def test_gk1_article_169_hit(lookup: RussianExactLookup) -> None:
    """ст. 169 ГК РФ ч.1 must be found."""
    result = lookup.get_article("local:ru/gk/1", "169")
    assert result.hit is True, "ст.169 ГК РФ ч.1 not found"


def test_gk1_article_169_not_tombstone(lookup: RussianExactLookup) -> None:
    result = lookup.get_article("local:ru/gk/1", "169")
    assert result.is_tombstone is False


def test_gk1_article_169_has_text(lookup: RussianExactLookup) -> None:
    result = lookup.get_article("local:ru/gk/1", "169")
    assert len(result.full_text.strip()) > 0


# ---------------------------------------------------------------------------
# Tombstone article — ст. 7 ТК РФ
# ---------------------------------------------------------------------------

def test_tk_article_7_is_tombstone(lookup: RussianExactLookup) -> None:
    """ст. 7 ТК РФ is repealed — must be returned with is_tombstone=True."""
    result = lookup.get_article("local:ru/tk", "7")
    assert result.hit is True, "ст.7 ТК РФ not found"
    assert result.is_tombstone is True, (
        f"Expected tombstone, got is_tombstone={result.is_tombstone}"
    )


def test_tk_article_7_tombstone_chunk_source_type(lookup: RussianExactLookup) -> None:
    """Tombstone chunks must have source_type='tombstone'."""
    result = lookup.get_article("local:ru/tk", "7")
    for chunk in result.chunks:
        assert chunk.source_type == "tombstone", (
            f"Chunk source_type={chunk.source_type!r} for tombstone article"
        )


def test_tk_article_7_tombstone_has_text(lookup: RussianExactLookup) -> None:
    """Tombstone article must still return non-empty text."""
    result = lookup.get_article("local:ru/tk", "7")
    assert len(result.full_text.strip()) > 0, "Tombstone article has empty text"


# ---------------------------------------------------------------------------
# Nonexistent article → structured no-hit
# ---------------------------------------------------------------------------

def test_nonexistent_article_returns_no_hit(lookup: RussianExactLookup) -> None:
    """Lookup of a nonexistent article must return hit=False, not raise."""
    result = lookup.get_article("local:ru/tk", "9999")
    assert result.hit is False
    assert result.chunks == []
    assert result.article_heading == ""
    assert result.is_tombstone is False


def test_nonexistent_law_returns_no_hit(lookup: RussianExactLookup) -> None:
    """Lookup against a law that was not ingested must return hit=False."""
    result = lookup.get_article("local:ru/uk", "1")  # УК РФ not in M1 corpus
    assert result.hit is False


def test_no_hit_law_id_preserved(lookup: RussianExactLookup) -> None:
    """No-hit result must echo back the queried law_id and article_num."""
    result = lookup.get_article("local:ru/tk", "9999")
    assert result.law_id == "local:ru/tk"
    assert result.article_num == "9999"


# ---------------------------------------------------------------------------
# Cross-law isolation
# ---------------------------------------------------------------------------

def test_tk_article_not_returned_for_sk_law(lookup: RussianExactLookup) -> None:
    """Querying ст.81 with SK law_id must return no hit."""
    result = lookup.get_article("local:ru/sk", "81")
    # ст.81 exists in ТК but must not appear when querying СК
    if result.hit:
        # If SK happens to also have article 81, verify it's actually from SK
        for chunk in result.chunks:
            assert chunk.law_id == "local:ru/sk", (
                f"Cross-law contamination: chunk from {chunk.law_id!r} returned for SK query"
            )


def test_gk1_article_not_returned_for_tk_law(lookup: RussianExactLookup) -> None:
    """Querying ГК ст.1 with TK law_id must not return GK chunks."""
    result_gk1 = lookup.get_article("local:ru/gk/1", "1")
    result_tk = lookup.get_article("local:ru/tk", "1")

    # If both exist, their chunks must not overlap
    if result_gk1.hit and result_tk.hit:
        gk1_ids = {c.chunk_id for c in result_gk1.chunks}
        tk_ids = {c.chunk_id for c in result_tk.chunks}
        assert gk1_ids.isdisjoint(tk_ids), (
            f"Cross-law chunk overlap between GK1 and TK for ст.1"
        )


def test_all_returned_chunks_have_correct_law_id(lookup: RussianExactLookup) -> None:
    """Every chunk in a TK lookup must have law_id='local:ru/tk'."""
    result = lookup.get_article("local:ru/tk", "81")
    for chunk in result.chunks:
        assert chunk.law_id == "local:ru/tk", (
            f"Chunk {chunk.chunk_id} has wrong law_id={chunk.law_id!r}"
        )


# ---------------------------------------------------------------------------
# Result ordering — deterministic
# ---------------------------------------------------------------------------

def test_chunk_ordering_is_deterministic(lookup: RussianExactLookup) -> None:
    """Two identical lookups must return chunks in the same order."""
    r1 = lookup.get_article("local:ru/gk/1", "1")
    r2 = lookup.get_article("local:ru/gk/1", "1")
    assert [c.chunk_id for c in r1.chunks] == [c.chunk_id for c in r2.chunks]


def test_chunk_index_is_ascending(lookup: RussianExactLookup) -> None:
    """chunk_index values in result must be 0, 1, 2, ... (ascending, no gaps)."""
    result = lookup.get_article("local:ru/gk/1", "1")
    indices = [c.chunk_index for c in result.chunks]
    assert indices == list(range(len(indices))), (
        f"Non-sequential chunk_index: {indices}"
    )


# ---------------------------------------------------------------------------
# optional part_num filtering
# ---------------------------------------------------------------------------

def test_part_num_filter_returns_single_chunk(lookup: RussianExactLookup) -> None:
    """Requesting a specific part_num must return only that chunk (or no-hit)."""
    # Find a GK1 article with multiple chunks to test part filtering
    result_all = lookup.get_article("local:ru/gk/1", "1")
    if result_all.part_count < 2:
        pytest.skip("ст.1 ГК РФ ч.1 has only one chunk — cannot test part_num filter")

    # Get the part_num of the second chunk
    second_chunk = result_all.chunks[1]
    if second_chunk.part_num is None:
        pytest.skip("Second chunk has no part_num — cannot test part_num filter")

    result_filtered = lookup.get_article("local:ru/gk/1", "1", part_num=second_chunk.part_num)
    assert result_filtered.hit is True
    assert all(c.part_num == second_chunk.part_num for c in result_filtered.chunks)


# ---------------------------------------------------------------------------
# Service wrapper
# ---------------------------------------------------------------------------

def test_service_get_article_matches_direct_lookup(
    service: RussianRetrievalService,
    lookup: RussianExactLookup,
) -> None:
    """RussianRetrievalService.get_article must return same result as direct lookup."""
    direct = lookup.get_article("local:ru/tk", "81")
    via_service = service.get_article("local:ru/tk", "81")

    assert via_service.hit == direct.hit
    assert via_service.article_heading == direct.article_heading
    assert via_service.is_tombstone == direct.is_tombstone
    assert [c.chunk_id for c in via_service.chunks] == [c.chunk_id for c in direct.chunks]


def test_service_no_hit_for_nonexistent(service: RussianRetrievalService) -> None:
    """Service must return hit=False for nonexistent article."""
    result = service.get_article("local:ru/tk", "9999")
    assert result.hit is False


# ---------------------------------------------------------------------------
# Decimal article numbers
# ---------------------------------------------------------------------------

def test_decimal_article_lookup_19_1(lookup: RussianExactLookup) -> None:
    """ст. 19.1 ТК РФ (decimal article) must be found."""
    result = lookup.get_article("local:ru/tk", "19.1")
    assert result.hit is True, "ст.19.1 ТК РФ not found — decimal article lookup broken"
    assert result.is_tombstone is False
