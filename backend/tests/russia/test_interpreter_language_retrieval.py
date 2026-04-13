"""
Interpreter / language-of-proceedings retrieval tests — Step 10.

Verifies the legal support around the foreign-party / interpreter /
language-of-proceedings issue, combining:
  - ГПК РФ — primary source (статьи 9 and 162)
  - ФЗ-115 — supporting source (legal status of foreign citizens)
  - ЕКПЧ  — supporting source (fair trial, right to interpreter)

Tests are skipped if Qdrant is unreachable or collection is absent.
GPK, FL115 and ECHR must all be present for the integration tests to run.

Tests verify:
  - GPK exact lookup for ст. 9 (язык судопроизводства) and ст. 162 (переводчик)
  - Procedural topic queries return GPK for interpreter/language queries
  - FL115 and ECHR are reachable via explicit law alias
  - Unconstrained hybrid search surfaces FL115 for foreign-citizen queries
  - ECHR is reachable via alias and exact article lookup
  - Query analyzer correctly identifies interpreter/language queries as procedural
  - GPK remains the primary source for all interpreter/language topic queries
  - No regressions in family law (SK) or existing GPK retrieval
"""
from __future__ import annotations

import os
import pytest

QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
COLLECTION_NAME = "russian_laws_v1"


def _all_laws_present() -> bool:
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        client = QdrantClient(url=QDRANT_URL, timeout=10)
        if not client.collection_exists(COLLECTION_NAME):
            return False
        for law_id in ["local:ru/gpk", "local:ru/echr", "local:ru/fl115"]:
            n = client.count(
                COLLECTION_NAME,
                count_filter=Filter(must=[FieldCondition(key="law_id", match=MatchValue(value=law_id))]),
                exact=True,
            ).count
            if n == 0:
                return False
        return True
    except Exception:
        return False


_READY = _all_laws_present()

pytestmark = pytest.mark.skipif(
    not _READY,
    reason="GPK / FL115 / ECHR not all present — run Step 10 ingest first",
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
# Collection integrity
# ---------------------------------------------------------------------------

class TestSupportCorpusIntegrity:
    def test_fl115_present(self) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        client = QdrantClient(url=QDRANT_URL, timeout=10)
        n = client.count(
            COLLECTION_NAME,
            count_filter=Filter(must=[FieldCondition(key="law_id", match=MatchValue(value="local:ru/fl115"))]),
            exact=True,
        ).count
        assert n >= 100, f"FL115 has only {n} chunks, expected >= 100"

    def test_echr_present(self) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        client = QdrantClient(url=QDRANT_URL, timeout=10)
        n = client.count(
            COLLECTION_NAME,
            count_filter=Filter(must=[FieldCondition(key="law_id", match=MatchValue(value="local:ru/echr"))]),
            exact=True,
        ).count
        assert n >= 50, f"ECHR has only {n} chunks, expected >= 50"

    def test_six_laws_present(self) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        client = QdrantClient(url=QDRANT_URL, timeout=10)
        for law_id in ["local:ru/gk/1", "local:ru/gpk", "local:ru/sk", "local:ru/tk",
                       "local:ru/fl115", "local:ru/echr"]:
            n = client.count(
                COLLECTION_NAME,
                count_filter=Filter(must=[FieldCondition(key="law_id", match=MatchValue(value=law_id))]),
                exact=True,
            ).count
            assert n > 0, f"Law {law_id!r} is absent after Step 10 ingest"


# ---------------------------------------------------------------------------
# GPK exact article lookup — interpreter / language articles
# ---------------------------------------------------------------------------

class TestGPKExactInterpreterArticles:
    def test_article_9_found(self, service: RussianRetrievalService) -> None:
        """ст. 9 ГПК — Язык гражданского судопроизводства."""
        result = service.get_article("local:ru/gpk", "9")
        assert result.hit, "GPK ст.9 not found"
        assert result.law_id == "local:ru/gpk"

    def test_article_9_heading_language(self, service: RussianRetrievalService) -> None:
        """ст. 9 heading should reference language of proceedings."""
        result = service.get_article("local:ru/gpk", "9")
        assert result.hit
        heading = (result.chunks[0].article_heading or "").lower()
        assert any(w in heading for w in ["язык", "судопроизводств"]), (
            f"Unexpected heading for ст.9: {heading!r}"
        )

    def test_article_9_text_contains_language(self, service: RussianRetrievalService) -> None:
        """ст. 9 text must mention 'язык' or 'русском'."""
        result = service.get_article("local:ru/gpk", "9")
        assert result.hit
        full_text = " ".join(c.text for c in result.chunks).lower()
        assert any(w in full_text for w in ["язык", "русском", "судопроизводств"]), (
            "GPK ст.9 text does not mention language of proceedings"
        )

    def test_article_162_found(self, service: RussianRetrievalService) -> None:
        """ст. 162 ГПК — Переводчик."""
        result = service.get_article("local:ru/gpk", "162")
        assert result.hit, "GPK ст.162 not found"

    def test_article_162_heading_interpreter(self, service: RussianRetrievalService) -> None:
        """ст. 162 heading should reference interpreter."""
        result = service.get_article("local:ru/gpk", "162")
        assert result.hit
        heading = (result.chunks[0].article_heading or "").lower()
        assert any(w in heading for w in ["переводчик", "перевод"]), (
            f"Unexpected heading for ст.162: {heading!r}"
        )

    def test_article_162_via_topic_search(self, service: RussianRetrievalService) -> None:
        """ст. 162 гпк рф via topic_search → exact, score=1.0."""
        results = service.topic_search("ст. 162 гпк рф", top_k=5)
        assert len(results) > 0, "No results for ст. 162 гпк рф"
        for r in results:
            assert r.law_id == "local:ru/gpk"
            assert r.score == 1.0

    def test_article_9_via_topic_search(self, service: RussianRetrievalService) -> None:
        """ст. 9 гпк рф via topic_search → exact, score=1.0."""
        results = service.topic_search("гпк рф статья 9", top_k=5)
        assert len(results) > 0, "No results for гпк рф статья 9"
        for r in results:
            assert r.law_id == "local:ru/gpk"
            assert r.score == 1.0


# ---------------------------------------------------------------------------
# Procedural topic queries — GPK is primary source
# ---------------------------------------------------------------------------

class TestInterpreterTopicReturnsGPK:
    def test_interpreter_in_civil_proceedings(self, service: RussianRetrievalService) -> None:
        """'переводчик в гражданском процессе' → GPK results exclusively."""
        results = service.topic_search("переводчик в гражданском процессе", top_k=10)
        assert len(results) > 0
        for r in results:
            assert r.law_id == "local:ru/gpk", (
                f"Non-GPK result for interpreter query: {r.law_id!r}"
            )

    def test_language_of_proceedings(self, service: RussianRetrievalService) -> None:
        """'язык судопроизводства' → GPK results exclusively."""
        results = service.topic_search("язык судопроизводства", top_k=10)
        assert len(results) > 0
        for r in results:
            assert r.law_id == "local:ru/gpk", (
                f"Non-GPK result for язык судопроизводства: {r.law_id!r}"
            )

    def test_right_to_interpreter(self, service: RussianRetrievalService) -> None:
        """'право на переводчика' → GPK results exclusively."""
        results = service.topic_search("право на переводчика", top_k=10)
        assert len(results) > 0
        for r in results:
            assert r.law_id == "local:ru/gpk", (
                f"Non-GPK result for право на переводчика: {r.law_id!r}"
            )

    def test_not_understanding_court_language(self, service: RussianRetrievalService) -> None:
        """'лицо не владеющее языком судопроизводства' → GPK results."""
        results = service.topic_search("лицо не владеющее языком судопроизводства", top_k=10)
        assert len(results) > 0
        for r in results:
            assert r.law_id == "local:ru/gpk", (
                f"Non-GPK result for language understanding query: {r.law_id!r}"
            )

    def test_foreigner_in_court_has_gpk(self, service: RussianRetrievalService) -> None:
        """'иностранец в российском суде' → GPK prominent in results."""
        results = service.topic_search("иностранец в российском суде", top_k=10)
        assert len(results) > 0, "No results for иностранец в суде"
        gpk_count = sum(1 for r in results if r.law_id == "local:ru/gpk")
        assert gpk_count >= len(results) // 2, (
            f"GPK not majority in иностранец в суде results: gpk={gpk_count}/{len(results)}"
        )

    def test_foreigner_national_has_gpk(self, service: RussianRetrievalService) -> None:
        """'иностранный гражданин в суде' → GPK results exclusively (topic_search)."""
        results = service.topic_search("иностранный гражданин в суде", top_k=10)
        assert len(results) > 0
        for r in results:
            assert r.law_id == "local:ru/gpk", (
                f"Non-GPK result for иностранный гражданин в суде: {r.law_id!r}"
            )


# ---------------------------------------------------------------------------
# FL115 — accessible via explicit alias
# ---------------------------------------------------------------------------

class TestFL115Retrieval:
    def test_fl115_alias_constrains(self, service: RussianRetrievalService) -> None:
        """'115-фз' alias must constrain to FL115 only."""
        results = service.topic_search("правовое положение иностранных граждан 115-фз", top_k=10)
        assert len(results) > 0, "No FL115 results with 115-фз alias"
        for r in results:
            assert r.law_id == "local:ru/fl115", (
                f"Non-FL115 result when '115-фз' alias used: {r.law_id!r}"
            )

    def test_fl115_fz115_alias(self, service: RussianRetrievalService) -> None:
        """'фз-115' alias constrains to FL115."""
        results = service.topic_search("права иностранных граждан фз-115", top_k=10)
        assert len(results) > 0
        for r in results:
            assert r.law_id == "local:ru/fl115", (
                f"Non-FL115 result for фз-115: {r.law_id!r}"
            )

    def test_fl115_exact_article_lookup(self, service: RussianRetrievalService) -> None:
        """Exact article lookup in FL115 should work."""
        result = service.get_article("local:ru/fl115", "2")
        assert result.hit, "FL115 ст.2 not found"
        assert result.law_id == "local:ru/fl115"

    def test_fl115_reachable_via_hybrid(self, service: RussianRetrievalService) -> None:
        """Unconstrained hybrid search should surface FL115 for foreign citizen queries."""
        results = service.hybrid_search("правовое положение иностранных граждан", top_k=15)
        law_ids = {r.law_id for r in results}
        assert "local:ru/fl115" in law_ids, (
            f"FL115 not in unconstrained hybrid results for foreign citizen query: {law_ids}"
        )

    def test_fl115_results_have_text(self, service: RussianRetrievalService) -> None:
        results = service.topic_search("иностранный гражданин 115-фз", top_k=5)
        for r in results:
            assert len(r.text.strip()) > 0, f"Empty text in FL115 result chunk_id={r.chunk_id}"


# ---------------------------------------------------------------------------
# ECHR — accessible via explicit alias and exact lookup
# ---------------------------------------------------------------------------

class TestECHRRetrieval:
    def test_echr_alias_constrains(self, service: RussianRetrievalService) -> None:
        """'екпч' alias must constrain to ECHR only."""
        results = service.topic_search("право на переводчика екпч", top_k=10)
        assert len(results) > 0, "No ECHR results with екпч alias"
        for r in results:
            assert r.law_id == "local:ru/echr", (
                f"Non-ECHR result when 'екпч' alias used: {r.law_id!r}"
            )

    def test_echr_full_alias_constrains(self, service: RussianRetrievalService) -> None:
        """'конвенция о защите прав человека' alias constrains to ECHR."""
        results = service.topic_search(
            "право на справедливое судебное разбирательство конвенция о защите прав человека",
            top_k=10,
        )
        assert len(results) > 0
        for r in results:
            assert r.law_id == "local:ru/echr", (
                f"Non-ECHR result for konventsiya alias: {r.law_id!r}"
            )

    def test_echr_article_6_exact_lookup(self, service: RussianRetrievalService) -> None:
        """ECHR ст. 6 (fair trial / право на справедливое разбирательство)."""
        result = service.get_article("local:ru/echr", "6")
        assert result.hit, "ECHR ст.6 not found"
        assert result.law_id == "local:ru/echr"
        assert len(result.chunks) > 0

    def test_echr_article_5_exact_lookup(self, service: RussianRetrievalService) -> None:
        """ECHR ст. 5 (right to liberty, including right to be informed)."""
        result = service.get_article("local:ru/echr", "5")
        assert result.hit, "ECHR ст.5 not found"

    def test_echr_article_6_via_topic_search(self, service: RussianRetrievalService) -> None:
        """ECHR ст. 6 конвенция via topic_search → exact, score=1.0."""
        results = service.topic_search("конвенция о защите прав человека ст. 6", top_k=5)
        assert len(results) > 0
        for r in results:
            assert r.law_id == "local:ru/echr"
            assert r.score == 1.0

    def test_echr_reachable_via_hybrid(self, service: RussianRetrievalService) -> None:
        """Unconstrained hybrid search should find ECHR for fair trial queries."""
        results = service.hybrid_search(
            "право на справедливое судебное разбирательство переводчик", top_k=15
        )
        law_ids = {r.law_id for r in results}
        assert "local:ru/echr" in law_ids, (
            f"ECHR not in hybrid results for fair trial query: {law_ids}"
        )

    def test_echr_results_have_text(self, service: RussianRetrievalService) -> None:
        results = service.topic_search("право на переводчика екпч", top_k=5)
        for r in results:
            assert len(r.text.strip()) > 0, f"Empty text in ECHR result chunk_id={r.chunk_id}"


# ---------------------------------------------------------------------------
# analyze_query — interpreter / language detection
# ---------------------------------------------------------------------------

class TestAnalyzeQueryInterpreter:
    def test_interpreter_query_is_procedural(self, service: RussianRetrievalService) -> None:
        u = service.analyze_query("переводчик в гражданском процессе")
        assert u.detected_topic == "procedural_law"
        assert u.topic_confidence >= 2.5

    def test_language_query_is_procedural(self, service: RussianRetrievalService) -> None:
        u = service.analyze_query("язык судопроизводства")
        assert u.detected_topic == "procedural_law"
        assert u.topic_confidence >= 2.5

    def test_not_understanding_language_is_procedural(self, service: RussianRetrievalService) -> None:
        u = service.analyze_query("лицо не владеющее языком судопроизводства")
        assert u.detected_topic == "procedural_law"

    def test_procedural_preferred_gpk(self, service: RussianRetrievalService) -> None:
        u = service.analyze_query("переводчик в гражданском процессе")
        assert "local:ru/gpk" in u.preferred_law_ids

    def test_gpk_article_9_exact_lookup(self, service: RussianRetrievalService) -> None:
        u = service.analyze_query("гпк рф статья 9")
        assert u.query_mode == "exact_lookup"
        assert u.detected_article == "9"
        assert "local:ru/gpk" in u.detected_law_ids

    def test_gpk_article_162_exact_lookup(self, service: RussianRetrievalService) -> None:
        u = service.analyze_query("гпк рф ст. 162")
        assert u.query_mode == "exact_lookup"
        assert u.detected_article == "162"
        assert "local:ru/gpk" in u.detected_law_ids

    def test_fl115_alias_detected(self, service: RussianRetrievalService) -> None:
        u = service.analyze_query("правовое положение иностранца 115-фз")
        assert "local:ru/fl115" in u.detected_law_ids
        assert u.query_mode == "law_constrained_search"

    def test_echr_alias_detected(self, service: RussianRetrievalService) -> None:
        u = service.analyze_query("право на переводчика екпч")
        assert "local:ru/echr" in u.detected_law_ids
        assert u.query_mode == "law_constrained_search"

    def test_echr_full_alias_detected(self, service: RussianRetrievalService) -> None:
        u = service.analyze_query("конвенция о защите прав человека статья 6")
        assert "local:ru/echr" in u.detected_law_ids
        assert u.detected_article == "6"
        assert u.query_mode == "exact_lookup"


# ---------------------------------------------------------------------------
# Regression — existing retrieval not broken
# ---------------------------------------------------------------------------

class TestNoRegression:
    def test_sk_family_law_not_polluted(self, service: RussianRetrievalService) -> None:
        """Family law topic still returns SK, not FL115 or ECHR."""
        results = service.topic_search("лишение родительских прав", top_k=10)
        assert len(results) > 0
        for r in results:
            assert r.law_id == "local:ru/sk", (
                f"Non-SK result in family law topic search: {r.law_id!r}"
            )

    def test_gpk_procedural_appeal_still_works(self, service: RussianRetrievalService) -> None:
        """GPK procedural query still returns GPK."""
        results = service.topic_search("апелляционная жалоба на решение суда", top_k=10)
        law_ids = {r.law_id for r in results}
        assert "local:ru/gpk" in law_ids

    def test_gpk_article_113_still_exact(self, service: RussianRetrievalService) -> None:
        """GPK ст.113 still found exactly after FL115/ECHR ingest."""
        result = service.get_article("local:ru/gpk", "113")
        assert result.hit, "GPK ст.113 not found after Step 10"

    def test_sk_article_69_still_exact(self, service: RussianRetrievalService) -> None:
        """SK ст.69 still found exactly after FL115/ECHR ingest."""
        result = service.get_article("local:ru/sk", "69")
        assert result.hit, "SK ст.69 not found after Step 10"

    def test_sk_alias_not_confused_with_echr(self, service: RussianRetrievalService) -> None:
        """'права ребенка ск рф' must return SK only, not ECHR or FL115."""
        results = service.topic_search("права ребенка ск рф", top_k=10)
        for r in results:
            assert r.law_id == "local:ru/sk", (
                f"Non-SK result when 'ск рф' alias used: {r.law_id!r}"
            )

    def test_gpk_alias_not_confused(self, service: RussianRetrievalService) -> None:
        """'гпк рф' alias must return GPK only, not ECHR or FL115."""
        results = service.topic_search("процессуальные нарушения гпк рф", top_k=10)
        for r in results:
            assert r.law_id == "local:ru/gpk", (
                f"Non-GPK result when 'гпк рф' alias used: {r.law_id!r}"
            )
