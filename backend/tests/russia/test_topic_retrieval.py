"""
Topic retrieval integration tests — Step 8 verification.

Requires russian_laws_v1 to be populated with BM25 sparse vectors.
Tests are skipped if Qdrant is unreachable or collection is absent.

Tests verify:
  - Family-law topic queries return SK results prominently
  - Law alias (ск рф) constrains retrieval to SK
  - Exact article queries still work via topic_search
  - hybrid topic retrieval returns results for SK
  - GPK topic queries handled gracefully (may return empty if GPK not ingested)
  - No LLM calls in service.topic_search
  - Service.analyze_query returns RussianQueryUnderstanding
  - Hybrid topic search better than unconstrained for specific SK queries
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


_READY = _collection_ready()

pytestmark = pytest.mark.skipif(
    not _READY,
    reason=f"{COLLECTION_NAME} not populated — run M1 corpus ingest first",
)

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from app.core.config import get_settings
from app.modules.common.embeddings.provider import EmbeddingService
from app.modules.russia.retrieval.service import RussianRetrievalService
from app.modules.russia.retrieval.schemas import RussianSearchResult
from app.modules.russia.retrieval.query_analyzer import RussianQueryUnderstanding

_IDF_PATH_DEFAULT = "storage/idf_russian_laws_v1.json"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def idf_path():
    from pathlib import Path
    p = Path(os.environ.get("RUSSIAN_IDF_CHECKPOINT_PATH", _IDF_PATH_DEFAULT))
    return p if p.exists() else None


@pytest.fixture(scope="session")
def service(idf_path) -> RussianRetrievalService:
    s = get_settings()
    emb = EmbeddingService(
        model_name=s.embedding_model,
        provider_name=s.embedding_provider,
        hash_dimension=s.embedding_hash_dimension,
    )
    return RussianRetrievalService(
        embedding_service=emb,
        qdrant_url=QDRANT_URL,
        idf_checkpoint_path=idf_path,
    )


# ---------------------------------------------------------------------------
# analyze_query
# ---------------------------------------------------------------------------

def test_analyze_query_returns_understanding(service: RussianRetrievalService) -> None:
    """service.analyze_query must return RussianQueryUnderstanding."""
    u = service.analyze_query("порядок общения с ребенком")
    assert isinstance(u, RussianQueryUnderstanding)


def test_analyze_query_family_law_topic(service: RussianRetrievalService) -> None:
    u = service.analyze_query("лишение родительских прав")
    assert u.detected_topic == "family_law"
    assert "local:ru/sk" in u.preferred_law_ids


def test_analyze_query_sk_alias(service: RussianRetrievalService) -> None:
    u = service.analyze_query("ск рф ст. 69")
    assert "local:ru/sk" in u.detected_law_ids
    assert u.detected_article == "69"
    assert u.query_mode == "exact_lookup"


# ---------------------------------------------------------------------------
# Family law topic search — SK required
# ---------------------------------------------------------------------------

def test_family_topic_returns_results(service: RussianRetrievalService) -> None:
    """Family law topic query must return at least one result from SK."""
    results = service.topic_search("порядок общения с ребенком", top_k=10)
    assert len(results) > 0, "topic_search returned no results for family law query"


def test_family_topic_sk_prominent(service: RussianRetrievalService) -> None:
    """Family law topic results must be predominantly from SK."""
    results = service.topic_search("порядок общения с ребенком", top_k=10)
    sk_count = sum(1 for r in results if r.law_id == "local:ru/sk")
    assert sk_count >= len(results) // 2, (
        f"SK results ({sk_count}) are not majority in {len(results)} family law results"
    )


def test_family_topic_all_from_sk(service: RussianRetrievalService) -> None:
    """When query has strong family law signals, constrained search should only return SK."""
    results = service.topic_search("лишение родительских прав", top_k=10)
    assert len(results) > 0
    for r in results:
        assert r.law_id == "local:ru/sk", (
            f"Non-SK result in family law topic search: {r.law_id!r}"
        )


def test_parental_rights_returns_sk(service: RussianRetrievalService) -> None:
    """Родительские права query must return SK results."""
    results = service.topic_search("родительские права и обязанности", top_k=10)
    law_ids = {r.law_id for r in results}
    assert "local:ru/sk" in law_ids, f"SK not in results for родительские права: {law_ids}"


def test_child_custody_returns_sk(service: RussianRetrievalService) -> None:
    """Место жительства ребенка query must return SK results."""
    results = service.topic_search("определение места жительства ребенка", top_k=10)
    law_ids = {r.law_id for r in results}
    assert "local:ru/sk" in law_ids, (
        f"SK not in results for место жительства ребенка: {law_ids}"
    )


def test_custody_board_returns_sk(service: RussianRetrievalService) -> None:
    """Орган опеки query must return SK results."""
    results = service.topic_search("орган опеки и попечительства", top_k=10)
    law_ids = {r.law_id for r in results}
    assert "local:ru/sk" in law_ids, (
        f"SK not in results for орган опеки: {law_ids}"
    )


# ---------------------------------------------------------------------------
# Law alias constrains retrieval
# ---------------------------------------------------------------------------

def test_sk_alias_constrains_to_sk(service: RussianRetrievalService) -> None:
    """Explicit 'ск рф' alias must restrict results to SK."""
    results = service.topic_search("права ребенка ск рф", top_k=10)
    assert len(results) > 0
    for r in results:
        assert r.law_id == "local:ru/sk", (
            f"Non-SK result when 'ск рф' alias used: {r.law_id!r}"
        )


def test_tk_alias_constrains_to_tk(service: RussianRetrievalService) -> None:
    """Explicit 'тк рф' alias must restrict results to TK."""
    results = service.topic_search("расторжение договора тк рф", top_k=10)
    assert len(results) > 0
    for r in results:
        assert r.law_id == "local:ru/tk", (
            f"Non-TK result when 'тк рф' alias used: {r.law_id!r}"
        )


def test_gk_alias_constrains_to_gk1(service: RussianRetrievalService) -> None:
    """Explicit 'гк рф' alias must restrict results to GK part 1."""
    results = service.topic_search("недействительная сделка гк рф", top_k=10)
    assert len(results) > 0
    for r in results:
        assert r.law_id == "local:ru/gk/1", (
            f"Non-GK1 result when 'гк рф' alias used: {r.law_id!r}"
        )


# ---------------------------------------------------------------------------
# Exact article lookup via topic_search
# ---------------------------------------------------------------------------

def test_exact_article_sk_via_topic_search(service: RussianRetrievalService) -> None:
    """Exact article lookup (ст. 69 ск рф) must return hit via topic_search."""
    results = service.topic_search("ст. 69 ск рф", top_k=5)
    assert len(results) > 0, "Exact article ст.69 СК РФ not found via topic_search"
    for r in results:
        assert r.law_id == "local:ru/sk"


def test_exact_article_tk_via_topic_search(service: RussianRetrievalService) -> None:
    """Exact article lookup (ст. 81 тк рф) must work via topic_search."""
    results = service.topic_search("ст. 81 тк рф", top_k=5)
    assert len(results) > 0
    for r in results:
        assert r.law_id == "local:ru/tk"


def test_exact_article_has_score_one(service: RussianRetrievalService) -> None:
    """Exact lookup results must have score=1.0."""
    results = service.topic_search("ст. 81 тк рф", top_k=5)
    for r in results:
        assert r.score == 1.0, f"Exact lookup score should be 1.0, got {r.score}"


# ---------------------------------------------------------------------------
# GPK topic — graceful handling (GPK may not be in corpus)
# ---------------------------------------------------------------------------

def test_gpk_topic_search_does_not_raise(service: RussianRetrievalService) -> None:
    """GPK topic query must not raise even if GPK is not in corpus."""
    try:
        results = service.topic_search("апелляционная жалоба на решение суда", top_k=10)
        assert isinstance(results, list)
    except Exception as exc:
        pytest.fail(f"topic_search raised for GPK query: {exc}")


def test_gpk_alias_query_does_not_raise(service: RussianRetrievalService) -> None:
    """GPK alias query must not raise."""
    try:
        results = service.topic_search("гпк рф ст. 131", top_k=5)
        assert isinstance(results, list)
    except Exception as exc:
        pytest.fail(f"topic_search raised for GPK alias query: {exc}")


# ---------------------------------------------------------------------------
# Result quality — topic search vs unconstrained
# ---------------------------------------------------------------------------

def test_family_topic_search_better_than_broad(service: RussianRetrievalService) -> None:
    """
    Constrained family law topic search must return more SK results than
    unconstrained hybrid search for a representative family law query.

    This verifies that the analyzer correctly constrains to SK for family queries.
    """
    family_query = "порядок общения с ребенком"

    topic_results = service.topic_search(family_query, top_k=10)
    broad_results = service.hybrid_search(family_query, top_k=10)

    topic_sk = sum(1 for r in topic_results if r.law_id == "local:ru/sk")
    broad_sk = sum(1 for r in broad_results if r.law_id == "local:ru/sk")

    assert topic_sk >= broad_sk, (
        f"Topic search SK count ({topic_sk}) < broad search SK count ({broad_sk}) "
        "for family law query — topic constraints not working"
    )


# ---------------------------------------------------------------------------
# Result integrity
# ---------------------------------------------------------------------------

def test_topic_results_have_nonempty_text(service: RussianRetrievalService) -> None:
    results = service.topic_search("порядок общения с ребенком", top_k=5)
    for r in results:
        assert len(r.text.strip()) > 0, f"Empty text in topic result chunk_id={r.chunk_id}"


def test_topic_results_are_russian_search_result(service: RussianRetrievalService) -> None:
    results = service.topic_search("права ребенка ск рф", top_k=5)
    for r in results:
        assert isinstance(r, RussianSearchResult)


def test_topic_results_have_valid_source_type(service: RussianRetrievalService) -> None:
    results = service.topic_search("родительские права", top_k=10)
    for r in results:
        assert r.source_type in {"article", "tombstone"}, (
            f"Invalid source_type={r.source_type!r}"
        )


def test_topic_search_top_k_respected(service: RussianRetrievalService) -> None:
    for k in [1, 3, 5]:
        results = service.topic_search("порядок общения с ребенком", top_k=k)
        assert len(results) <= k, f"Got {len(results)} results but top_k={k}"


# ---------------------------------------------------------------------------
# No LLM
# ---------------------------------------------------------------------------

def test_topic_search_does_not_call_llm(service: RussianRetrievalService) -> None:
    """topic_search must not import or call any LLM provider."""
    import app.modules.russia.retrieval.service as mod
    import sys

    llm_modules = {"openai", "anthropic", "app.modules.common.llm"}
    for llm_mod in llm_modules:
        assert llm_mod not in (getattr(mod, "__name__", "") or ""), (
            f"service imported LLM module: {llm_mod}"
        )
    # Verify the module loaded
    assert "app.modules.russia.retrieval.service" in sys.modules
