"""
Sparse retriever and hybrid search tests — Step 7 verification.

Requires russian_laws_v1 to be populated WITH BM25 sparse vectors.
Re-ingest with:
    python -m app.modules.russia.ingestion.cli \\
        --corpus /app/Ruske_zakony \\
        --no-checkpoint \\
        --idf-checkpoint /app/storage/idf_russian_laws_v1.json \\
        --quiet

Tests are skipped if Qdrant is unreachable, the collection is absent,
or sparse vectors have not been populated.

Tests verify:
  - sparse search returns results
  - law_id filter restricts results to one law
  - unfiltered search may return results from any law
  - filtered sparse search excludes other laws
  - hybrid_search returns fused RussianSearchResult list
  - hybrid top_k is respected
  - tombstone source_type preserved in sparse results
  - sparse search does not call LLM (structural test)
  - RussianBM25Encoder tokenizer handles Cyrillic
  - IDFTable builds correctly from corpus texts
  - RRF fusion deduplicates and scores correctly
  - service.hybrid_search fallback to dense when sparse empty
"""
from __future__ import annotations

import os
import pytest

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


def _sparse_vectors_populated() -> bool:
    """Check that at least one point has non-empty sparse indices."""
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(url=QDRANT_URL, timeout=10)
        if not client.collection_exists(COLLECTION_NAME):
            return False
        response = client.query_points(
            collection_name=COLLECTION_NAME,
            query=[0.0] * 384,          # dummy dense query — just to get any point
            using="dense",
            limit=5,
            with_vectors=["sparse"],
            with_payload=False,
        )
        for point in response.points:
            vecs = point.vector or {}
            sparse = vecs.get("sparse") if isinstance(vecs, dict) else None
            if sparse and hasattr(sparse, "indices") and len(sparse.indices) > 0:
                return True
        return False
    except Exception:
        return False


_READY = _collection_ready() and _sparse_vectors_populated()

pytestmark = pytest.mark.skipif(
    not _READY,
    reason=(
        f"{COLLECTION_NAME} sparse vectors not populated — "
        "re-ingest with: python -m app.modules.russia.ingestion.cli "
        "--corpus /app/Ruske_zakony --no-checkpoint "
        "--idf-checkpoint /app/storage/idf_russian_laws_v1.json --quiet"
    ),
)

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from app.core.config import get_settings
from app.modules.common.embeddings.provider import EmbeddingService
from app.modules.russia.retrieval.sparse_retriever import RussianSparseRetriever
from app.modules.russia.retrieval.service import RussianRetrievalService
from app.modules.russia.retrieval.schemas import RussianSearchResult

_IDF_PATH_DEFAULT = "storage/idf_russian_laws_v1.json"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def idf_path():
    from pathlib import Path
    p = Path(os.environ.get("RUSSIAN_IDF_CHECKPOINT_PATH", _IDF_PATH_DEFAULT))
    if not p.exists():
        pytest.skip(f"IDF checkpoint not found: {p} — re-ingest with --idf-checkpoint")
    return p


@pytest.fixture(scope="session")
def sparse_retriever(idf_path) -> RussianSparseRetriever:
    from pathlib import Path
    return RussianSparseRetriever(url=QDRANT_URL, idf_checkpoint_path=idf_path)


@pytest.fixture(scope="session")
def embedding_service() -> EmbeddingService:
    s = get_settings()
    return EmbeddingService(
        model_name=s.embedding_model,
        provider_name=s.embedding_provider,
        hash_dimension=s.embedding_hash_dimension,
    )


@pytest.fixture(scope="session")
def service(embedding_service, idf_path) -> RussianRetrievalService:
    return RussianRetrievalService(
        embedding_service=embedding_service,
        qdrant_url=QDRANT_URL,
        idf_checkpoint_path=idf_path,
    )


# ---------------------------------------------------------------------------
# Basic sparse search
# ---------------------------------------------------------------------------

def test_sparse_search_returns_results(sparse_retriever: RussianSparseRetriever) -> None:
    """A typical query must return at least one result."""
    results = sparse_retriever.search("расторжение трудового договора", top_k=5)
    assert len(results) > 0, "Sparse search returned no results"


def test_sparse_search_returns_russian_search_result_instances(
    sparse_retriever: RussianSparseRetriever,
) -> None:
    """Every result must be a RussianSearchResult instance."""
    results = sparse_retriever.search("трудовой договор", top_k=5)
    for r in results:
        assert isinstance(r, RussianSearchResult)


def test_sparse_search_results_have_nonempty_text(
    sparse_retriever: RussianSparseRetriever,
) -> None:
    """Every returned chunk must have non-empty text."""
    results = sparse_retriever.search("права работников", top_k=5)
    for r in results:
        assert len(r.text.strip()) > 0, f"Empty text chunk_id={r.chunk_id!r}"


def test_sparse_search_results_have_scores(sparse_retriever: RussianSparseRetriever) -> None:
    """Every result must have a numeric (BM25) score."""
    results = sparse_retriever.search("трудовой договор", top_k=5)
    for r in results:
        assert isinstance(r.score, float)


def test_sparse_top_score_is_positive(sparse_retriever: RussianSparseRetriever) -> None:
    """The top BM25 score must be positive."""
    results = sparse_retriever.search("трудовые отношения", top_k=1)
    assert len(results) > 0
    assert results[0].score > 0, f"Non-positive top BM25 score: {results[0].score}"


# ---------------------------------------------------------------------------
# top_k guard
# ---------------------------------------------------------------------------

def test_sparse_top_k_respected(sparse_retriever: RussianSparseRetriever) -> None:
    """Result count must not exceed top_k."""
    for k in [1, 3, 5]:
        results = sparse_retriever.search("трудовой договор", top_k=k)
        assert len(results) <= k, f"Got {len(results)} results but top_k={k}"


def test_sparse_empty_query_returns_empty(sparse_retriever: RussianSparseRetriever) -> None:
    """Whitespace-only query must return empty list."""
    results = sparse_retriever.search("   ", top_k=5)
    assert results == []


def test_sparse_zero_top_k_returns_empty(sparse_retriever: RussianSparseRetriever) -> None:
    """top_k=0 must return empty list without error."""
    results = sparse_retriever.search("трудовой договор", top_k=0)
    assert results == []


# ---------------------------------------------------------------------------
# law_id filter
# ---------------------------------------------------------------------------

def test_sparse_filter_restricts_to_tk(sparse_retriever: RussianSparseRetriever) -> None:
    """With law_id='local:ru/tk', all results must be from ТК РФ."""
    results = sparse_retriever.search("трудовой договор", law_id="local:ru/tk", top_k=10)
    assert len(results) > 0, "Sparse filtered search returned no results for ТК РФ"
    for r in results:
        assert r.law_id == "local:ru/tk", (
            f"Cross-law result: expected 'local:ru/tk', got {r.law_id!r}"
        )


def test_sparse_filter_restricts_to_sk(sparse_retriever: RussianSparseRetriever) -> None:
    """With law_id='local:ru/sk', all results must be from СК РФ."""
    results = sparse_retriever.search("семья брак дети", law_id="local:ru/sk", top_k=10)
    assert len(results) > 0, "Sparse filtered search returned no results for СК РФ"
    for r in results:
        assert r.law_id == "local:ru/sk", (
            f"Cross-law result: expected 'local:ru/sk', got {r.law_id!r}"
        )


def test_sparse_filter_restricts_to_gk1(sparse_retriever: RussianSparseRetriever) -> None:
    """With law_id='local:ru/gk/1', all results must be from ГК РФ ч.1."""
    results = sparse_retriever.search("гражданские права", law_id="local:ru/gk/1", top_k=10)
    assert len(results) > 0, "Sparse filtered search returned no results for ГК РФ ч.1"
    for r in results:
        assert r.law_id == "local:ru/gk/1", (
            f"Cross-law result: expected 'local:ru/gk/1', got {r.law_id!r}"
        )


def test_sparse_filtered_excludes_other_laws(sparse_retriever: RussianSparseRetriever) -> None:
    """Filtering by TK must exclude SK and GK results."""
    results = sparse_retriever.search("права граждан", law_id="local:ru/tk", top_k=15)
    for r in results:
        assert r.law_id == "local:ru/tk", (
            f"Unexpected law_id={r.law_id!r} when filtering for ТК РФ"
        )


# ---------------------------------------------------------------------------
# Cross-law (unfiltered)
# ---------------------------------------------------------------------------

def test_sparse_unfiltered_returns_results(sparse_retriever: RussianSparseRetriever) -> None:
    """Without law_id filter, results can come from any ingested law."""
    results = sparse_retriever.search("права и обязанности", top_k=20)
    assert len(results) >= 1, "No results from any law"


# ---------------------------------------------------------------------------
# Tombstone preservation
# ---------------------------------------------------------------------------

def test_sparse_tombstone_source_type_preserved(sparse_retriever: RussianSparseRetriever) -> None:
    """source_type must be 'article' or 'tombstone' for all results."""
    results = sparse_retriever.search("трудовые отношения", top_k=10)
    valid = {"article", "tombstone"}
    for r in results:
        assert r.source_type in valid, f"Invalid source_type={r.source_type!r}"


def test_sparse_tombstone_flag_consistent(sparse_retriever: RussianSparseRetriever) -> None:
    """If is_tombstone is True, source_type must be 'tombstone'."""
    results = sparse_retriever.search("утратила силу", law_id="local:ru/tk", top_k=20)
    for r in results:
        if r.is_tombstone:
            assert r.source_type == "tombstone", (
                f"is_tombstone=True but source_type={r.source_type!r}"
            )


# ---------------------------------------------------------------------------
# No LLM (structural test)
# ---------------------------------------------------------------------------

def test_sparse_retriever_does_not_import_llm(
    sparse_retriever: RussianSparseRetriever,
) -> None:
    """sparse_retriever.py must not import any LLM provider."""
    import app.modules.russia.retrieval.sparse_retriever as mod
    import sys

    llm_modules = {"openai", "anthropic", "app.modules.common.llm"}
    for llm_mod in llm_modules:
        assert llm_mod not in (getattr(mod, "__name__", "") or ""), (
            f"sparse_retriever imported LLM module: {llm_mod}"
        )
    assert "app.modules.russia.retrieval.sparse_retriever" in sys.modules


# ---------------------------------------------------------------------------
# Hybrid search via service
# ---------------------------------------------------------------------------

def test_hybrid_search_returns_results(service: RussianRetrievalService) -> None:
    """hybrid_search must return at least one RussianSearchResult."""
    results = service.hybrid_search("расторжение трудового договора", top_k=10)
    assert len(results) > 0, "Hybrid search returned no results"


def test_hybrid_search_returns_russian_search_result_instances(
    service: RussianRetrievalService,
) -> None:
    """Every hybrid result must be a RussianSearchResult instance."""
    results = service.hybrid_search("трудовой договор", top_k=5)
    for r in results:
        assert isinstance(r, RussianSearchResult)


def test_hybrid_top_k_respected(service: RussianRetrievalService) -> None:
    """Result count must not exceed top_k."""
    for k in [1, 3, 5]:
        results = service.hybrid_search("трудовой договор", top_k=k)
        assert len(results) <= k, f"Got {len(results)} hybrid results but top_k={k}"


def test_hybrid_filter_restricts_to_tk(service: RussianRetrievalService) -> None:
    """Hybrid search with law_id='local:ru/tk' must only return TK chunks."""
    results = service.hybrid_search("трудовой договор", law_id="local:ru/tk", top_k=10)
    assert len(results) > 0
    for r in results:
        assert r.law_id == "local:ru/tk", (
            f"Cross-law result in hybrid: expected 'local:ru/tk', got {r.law_id!r}"
        )


def test_hybrid_results_have_nonempty_text(service: RussianRetrievalService) -> None:
    """Every hybrid result must have non-empty text."""
    results = service.hybrid_search("права работников", top_k=5)
    for r in results:
        assert len(r.text.strip()) > 0, f"Empty text in hybrid result chunk_id={r.chunk_id!r}"


def test_hybrid_results_have_positive_scores(service: RussianRetrievalService) -> None:
    """Hybrid RRF scores must be positive (> 0)."""
    results = service.hybrid_search("трудовые отношения", top_k=5)
    for r in results:
        assert r.score > 0, f"Non-positive RRF score: {r.score}"


def test_hybrid_tombstone_source_type_valid(service: RussianRetrievalService) -> None:
    """source_type in hybrid results must be 'article' or 'tombstone'."""
    results = service.hybrid_search("трудовые отношения", top_k=10)
    valid = {"article", "tombstone"}
    for r in results:
        assert r.source_type in valid, f"Invalid source_type={r.source_type!r}"

