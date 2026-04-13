"""
GPK (Гражданский процессуальный кодекс) retrieval integration tests — Step 9.

Requires russian_laws_v1 to be populated with GPK chunks and BM25 sparse vectors.
Tests are skipped if Qdrant is unreachable, the collection is absent, or GPK
is not yet ingested.

Tests verify:
  - GPK is present in the collection (1279 chunks)
  - Exact article lookup: ст. 113 (судебные извещения), ст. 131 (форма иска),
    ст. 320 (апелляционное обжалование), ст. 56 (доказательства)
  - Procedural topic queries return GPK results prominently
  - 'гпк рф' alias constrains retrieval to GPK
  - Existing laws (SK, GK/1, TK) not regressed
  - Family law queries still return SK and not GPK
  - topic_search and analyze_query handle GPK correctly
"""
from __future__ import annotations

import os
import pytest

QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
COLLECTION_NAME = "russian_laws_v1"
_GPK_ID = "local:ru/gpk"
_GPK_EXPECTED_MIN_CHUNKS = 1000  # actual: 1279


def _collection_ready_with_gpk() -> bool:
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        client = QdrantClient(url=QDRANT_URL, timeout=10)
        if not client.collection_exists(COLLECTION_NAME):
            return False
        n = client.count(
            COLLECTION_NAME,
            count_filter=Filter(must=[
                FieldCondition(key="law_id", match=MatchValue(value=_GPK_ID))
            ]),
            exact=True,
        ).count
        return n >= _GPK_EXPECTED_MIN_CHUNKS
    except Exception:
        return False


_READY = _collection_ready_with_gpk()

pytestmark = pytest.mark.skipif(
    not _READY,
    reason=f"GPK not found in {COLLECTION_NAME} — run Step 9 ingest first",
)

# ---------------------------------------------------------------------------
# Imports (only after skip guard)
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
# Collection integrity
# ---------------------------------------------------------------------------

class TestGPKCollectionIntegrity:
    def test_gpk_chunk_count(self) -> None:
        """GPK must have at least 1000 chunks."""
        from qdrant_client import QdrantClient
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        client = QdrantClient(url=QDRANT_URL, timeout=10)
        n = client.count(
            COLLECTION_NAME,
            count_filter=Filter(must=[
                FieldCondition(key="law_id", match=MatchValue(value=_GPK_ID))
            ]),
            exact=True,
        ).count
        assert n >= _GPK_EXPECTED_MIN_CHUNKS, (
            f"GPK has only {n} chunks, expected >= {_GPK_EXPECTED_MIN_CHUNKS}"
        )

    def test_all_four_laws_present(self) -> None:
        """All four laws must be present after GPK ingest."""
        from qdrant_client import QdrantClient
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        client = QdrantClient(url=QDRANT_URL, timeout=10)
        for law_id in ["local:ru/gk/1", "local:ru/gpk", "local:ru/sk", "local:ru/tk"]:
            n = client.count(
                COLLECTION_NAME,
                count_filter=Filter(must=[
                    FieldCondition(key="law_id", match=MatchValue(value=law_id))
                ]),
                exact=True,
            ).count
            assert n > 0, f"Law {law_id!r} has 0 chunks after Step 9 ingest"

    def test_gpk_has_sparse_vectors(self) -> None:
        """GPK chunks must have non-empty BM25 sparse vectors."""
        from qdrant_client import QdrantClient
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        client = QdrantClient(url=QDRANT_URL, timeout=10)
        pts = client.query_points(
            COLLECTION_NAME,
            query_filter=Filter(must=[
                FieldCondition(key="law_id", match=MatchValue(value=_GPK_ID))
            ]),
            limit=1,
            with_vectors=["sparse"],
        ).points
        assert pts, "No GPK points returned"
        sv = pts[0].vector.get("sparse")
        assert sv is not None and len(sv.indices) > 0, (
            "GPK chunk has empty sparse vector — BM25 ingest may have failed"
        )

    def test_total_collection_size(self) -> None:
        """Collection must have >= 3500 chunks total (all four laws)."""
        from qdrant_client import QdrantClient
        client = QdrantClient(url=QDRANT_URL, timeout=10)
        n = client.count(COLLECTION_NAME, exact=True).count
        assert n >= 3500, f"Collection has only {n} chunks, expected >= 3500"


# ---------------------------------------------------------------------------
# Exact article lookup — GPK articles
# ---------------------------------------------------------------------------

class TestGPKExactLookup:
    def test_article_113_found(self, service: RussianRetrievalService) -> None:
        """ст. 113 ГПК — судебные извещения."""
        result = service.get_article("local:ru/gpk", "113")
        assert result.hit, "Article 113 not found in GPK"
        assert result.law_id == "local:ru/gpk"
        assert result.article_num == "113"
        assert len(result.chunks) > 0

    def test_article_113_heading(self, service: RussianRetrievalService) -> None:
        """Article 113 heading should reference notifications/summons."""
        result = service.get_article("local:ru/gpk", "113")
        assert result.hit
        heading = (result.chunks[0].article_heading or "").lower()
        assert any(w in heading for w in ["извещени", "вызов", "повестк"]), (
            f"Unexpected heading for ст.113: {heading!r}"
        )

    def test_article_131_found(self, service: RussianRetrievalService) -> None:
        """ст. 131 ГПК — форма и содержание искового заявления."""
        result = service.get_article("local:ru/gpk", "131")
        assert result.hit, "Article 131 not found in GPK"

    def test_article_320_found(self, service: RussianRetrievalService) -> None:
        """ст. 320 ГПК — апелляционное обжалование."""
        result = service.get_article("local:ru/gpk", "320")
        assert result.hit, "Article 320 not found in GPK"

    def test_article_56_found(self, service: RussianRetrievalService) -> None:
        """ст. 56 ГПК — обязанность доказывания."""
        result = service.get_article("local:ru/gpk", "56")
        assert result.hit, "Article 56 not found in GPK"

    def test_article_chunks_have_text(self, service: RussianRetrievalService) -> None:
        """All chunks returned for ст. 113 must have non-empty text."""
        result = service.get_article("local:ru/gpk", "113")
        assert result.hit
        for chunk in result.chunks:
            assert len(chunk.text.strip()) > 0, f"Empty chunk in ст.113: {chunk.chunk_id}"

    def test_nonexistent_article_returns_no_hit(self, service: RussianRetrievalService) -> None:
        """Article 9999 should return hit=False."""
        result = service.get_article("local:ru/gpk", "9999")
        assert not result.hit


# ---------------------------------------------------------------------------
# Exact article lookup via topic_search
# ---------------------------------------------------------------------------

class TestGPKExactViaTopicSearch:
    def test_article_113_via_topic_search(self, service: RussianRetrievalService) -> None:
        """ст. 113 гпк рф via topic_search → exact hit, score=1.0."""
        results = service.topic_search("ст. 113 гпк рф", top_k=5)
        assert len(results) > 0, "No results for ст. 113 гпк рф"
        for r in results:
            assert r.law_id == "local:ru/gpk"

    def test_article_113_score_one(self, service: RussianRetrievalService) -> None:
        """Exact lookup score must be 1.0."""
        results = service.topic_search("ст. 113 гпк рф", top_k=5)
        for r in results:
            assert r.score == 1.0, f"Expected score=1.0, got {r.score}"

    def test_article_131_via_topic_search(self, service: RussianRetrievalService) -> None:
        """ст. 131 гпк рф via topic_search → exact hit."""
        results = service.topic_search("ст. 131 гпк рф", top_k=5)
        assert len(results) > 0, "No results for ст. 131 гпк рф"
        for r in results:
            assert r.law_id == "local:ru/gpk"

    def test_article_320_via_topic_search(self, service: RussianRetrievalService) -> None:
        """ст. 320 гпк рф — апелляция."""
        results = service.topic_search("ст. 320 гпк рф", top_k=5)
        assert len(results) > 0
        for r in results:
            assert r.law_id == "local:ru/gpk"


# ---------------------------------------------------------------------------
# Procedural topic queries — GPK must appear prominently
# ---------------------------------------------------------------------------

class TestProceduralTopicReturnsGPK:
    def test_notice_parties_returns_gpk(self, service: RussianRetrievalService) -> None:
        """'извещение лиц о судебном заседании' → GPK results."""
        results = service.topic_search("извещение лиц о судебном заседании", top_k=10)
        assert len(results) > 0, "No results for извещение лиц"
        law_ids = {r.law_id for r in results}
        assert "local:ru/gpk" in law_ids, (
            f"GPK not in results for извещение запроса: {law_ids}"
        )

    def test_appeal_returns_gpk(self, service: RussianRetrievalService) -> None:
        """'апелляционная жалоба на решение суда' → GPK results."""
        results = service.topic_search("апелляционная жалоба на решение суда", top_k=10)
        assert len(results) > 0
        law_ids = {r.law_id for r in results}
        assert "local:ru/gpk" in law_ids, (
            f"GPK not in appeal results: {law_ids}"
        )

    def test_evidence_returns_gpk(self, service: RussianRetrievalService) -> None:
        """'доказательства в суде' → GPK results."""
        results = service.topic_search("доказательства в суде", top_k=10)
        assert len(results) > 0
        law_ids = {r.law_id for r in results}
        assert "local:ru/gpk" in law_ids, (
            f"GPK not in evidence results: {law_ids}"
        )

    def test_procedural_violations_returns_gpk(self, service: RussianRetrievalService) -> None:
        """'процессуальные нарушения при рассмотрении дела' → GPK."""
        results = service.topic_search("процессуальные нарушения при рассмотрении дела", top_k=10)
        assert len(results) > 0
        law_ids = {r.law_id for r in results}
        assert "local:ru/gpk" in law_ids, (
            f"GPK not in procedural violation results: {law_ids}"
        )

    def test_cancel_decision_returns_gpk(self, service: RussianRetrievalService) -> None:
        """'отмена решения суда апелляционной инстанцией' → GPK."""
        results = service.topic_search("отмена решения суда апелляционной инстанцией", top_k=10)
        assert len(results) > 0
        law_ids = {r.law_id for r in results}
        assert "local:ru/gpk" in law_ids, (
            f"GPK not in отмена решения results: {law_ids}"
        )

    def test_jurisdiction_returns_gpk(self, service: RussianRetrievalService) -> None:
        """'подсудность дел' → GPK results."""
        results = service.topic_search("подсудность дел районному суду", top_k=10)
        assert len(results) > 0
        law_ids = {r.law_id for r in results}
        assert "local:ru/gpk" in law_ids, (
            f"GPK not in подсудность results: {law_ids}"
        )

    def test_gpk_alias_constrains_to_gpk(self, service: RussianRetrievalService) -> None:
        """'апелляция гпк рф' alias must constrain all results to GPK."""
        results = service.topic_search("апелляционная жалоба гпк рф", top_k=10)
        assert len(results) > 0, "No results when 'гпк рф' alias present"
        for r in results:
            assert r.law_id == "local:ru/gpk", (
                f"Non-GPK result when 'гпк рф' alias used: {r.law_id!r}"
            )

    def test_gpk_alias_for_notice(self, service: RussianRetrievalService) -> None:
        """'извещение гпк рф' must only return GPK."""
        results = service.topic_search("извещение сторон гпк рф", top_k=10)
        assert len(results) > 0
        for r in results:
            assert r.law_id == "local:ru/gpk", (
                f"Non-GPK result for 'гпк рф' notice query: {r.law_id!r}"
            )


# ---------------------------------------------------------------------------
# analyze_query — GPK alias detection
# ---------------------------------------------------------------------------

class TestAnalyzeQueryGPK:
    def test_gpk_alias_detected(self, service: RussianRetrievalService) -> None:
        u = service.analyze_query("апелляционная жалоба гпк рф")
        assert "local:ru/gpk" in u.detected_law_ids

    def test_gpk_full_alias_detected(self, service: RussianRetrievalService) -> None:
        u = service.analyze_query("гражданский процессуальный кодекс ст. 131")
        assert "local:ru/gpk" in u.detected_law_ids
        assert u.detected_article == "131"

    def test_gpk_not_confused_with_gk(self, service: RussianRetrievalService) -> None:
        u = service.analyze_query("гпк рф ст. 320")
        assert "local:ru/gpk" in u.detected_law_ids
        assert "local:ru/gk/1" not in u.detected_law_ids

    def test_gpk_exact_lookup_mode(self, service: RussianRetrievalService) -> None:
        u = service.analyze_query("ст. 113 гпк рф")
        assert u.query_mode == "exact_lookup"
        assert u.detected_article == "113"
        assert "local:ru/gpk" in u.detected_law_ids

    def test_gpk_constrained_search_mode(self, service: RussianRetrievalService) -> None:
        u = service.analyze_query("гпк рф апелляционная жалоба")
        assert u.query_mode == "law_constrained_search"

    def test_procedural_topic_preferred_law(self, service: RussianRetrievalService) -> None:
        u = service.analyze_query("апелляционная жалоба на решение суда")
        assert u.detected_topic == "procedural_law"
        assert "local:ru/gpk" in u.preferred_law_ids


# ---------------------------------------------------------------------------
# Regression — existing laws not broken by GPK ingest
# ---------------------------------------------------------------------------

class TestExistingLawsNotRegressed:
    def test_sk_family_law_not_regressed(self, service: RussianRetrievalService) -> None:
        """Family law queries must still return SK after GPK ingest."""
        results = service.topic_search("порядок общения с ребенком", top_k=10)
        law_ids = {r.law_id for r in results}
        assert "local:ru/sk" in law_ids, (
            f"SK not in family law results after GPK ingest: {law_ids}"
        )

    def test_sk_exact_article_not_regressed(self, service: RussianRetrievalService) -> None:
        """ст. 69 ск рф must still be findable after GPK ingest."""
        result = service.get_article("local:ru/sk", "69")
        assert result.hit, "SK ст.69 not found after GPK ingest"

    def test_tk_exact_article_not_regressed(self, service: RussianRetrievalService) -> None:
        """ст. 81 тк рф must still be findable after GPK ingest."""
        result = service.get_article("local:ru/tk", "81")
        assert result.hit, "TK ст.81 not found after GPK ingest"

    def test_gk_exact_article_not_regressed(self, service: RussianRetrievalService) -> None:
        """GK/1 article must still be findable after GPK ingest."""
        result = service.get_article("local:ru/gk/1", "169")
        assert result.hit, "GK/1 ст.169 not found after GPK ingest"

    def test_sk_alias_still_constrains(self, service: RussianRetrievalService) -> None:
        """'ск рф' alias must still constrain to SK only (not GPK)."""
        results = service.topic_search("права ребенка ск рф", top_k=10)
        assert len(results) > 0
        for r in results:
            assert r.law_id == "local:ru/sk", (
                f"Non-SK result when 'ск рф' alias used: {r.law_id!r}"
            )

    def test_family_law_not_polluted_by_gpk(self, service: RussianRetrievalService) -> None:
        """'лишение родительских прав' must not return GPK results."""
        results = service.topic_search("лишение родительских прав", top_k=10)
        assert len(results) > 0
        for r in results:
            assert r.law_id == "local:ru/sk", (
                f"Non-SK result in family law topic search: {r.law_id!r}"
            )

    def test_tk_alias_still_constrains(self, service: RussianRetrievalService) -> None:
        """'тк рф' alias must still constrain to TK only."""
        results = service.topic_search("расторжение договора тк рф", top_k=10)
        assert len(results) > 0
        for r in results:
            assert r.law_id == "local:ru/tk", (
                f"Non-TK result when 'тк рф' alias used: {r.law_id!r}"
            )


# ---------------------------------------------------------------------------
# Result integrity — GPK results
# ---------------------------------------------------------------------------

class TestGPKResultIntegrity:
    def test_results_are_russian_search_result(self, service: RussianRetrievalService) -> None:
        results = service.topic_search("апелляционная жалоба гпк рф", top_k=5)
        for r in results:
            assert isinstance(r, RussianSearchResult)

    def test_results_have_nonempty_text(self, service: RussianRetrievalService) -> None:
        results = service.topic_search("апелляционная жалоба гпк рф", top_k=5)
        for r in results:
            assert len(r.text.strip()) > 0, f"Empty text in GPK result chunk_id={r.chunk_id}"

    def test_results_have_valid_source_type(self, service: RussianRetrievalService) -> None:
        results = service.topic_search("доказательства в суде", top_k=10)
        for r in results:
            assert r.source_type in {"article", "tombstone"}, (
                f"Invalid source_type={r.source_type!r}"
            )

    def test_topic_search_top_k_respected(self, service: RussianRetrievalService) -> None:
        for k in [1, 3, 5]:
            results = service.topic_search("апелляционная жалоба гпк рф", top_k=k)
            assert len(results) <= k, f"Got {len(results)} results but top_k={k}"

    def test_gpk_results_have_law_short(self, service: RussianRetrievalService) -> None:
        """GPK results must have a non-empty law_short field."""
        results = service.topic_search("апелляционная жалоба гпк рф", top_k=5)
        for r in results:
            assert r.law_short, f"Empty law_short for GPK result chunk_id={r.chunk_id}"
