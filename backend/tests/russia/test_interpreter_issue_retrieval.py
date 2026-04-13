"""
Tests for InterpreterIssueRetrieval — Step 11.

Verifies the issue-focused multi-source retrieval entrypoint for the
foreign-party / interpreter / language-of-proceedings problem.

Tests are skipped if Qdrant is unreachable or the collection is absent.

Tests verify:
  - Primary results are always from GPK
  - Support results, when present, are from ECHR or FL115 only
  - Combined = primary + supporting, sorted by score desc
  - source_role field is correct for each evidence item
  - GPK is primary for all issue-cluster queries
  - ECHR/FL115 appear as support for interpreter-specific queries
  - Exact article lookup (ст. 162 гпк рф) produces score=1.0 primary
  - Output types are correct (IssueEvidence, InterpreterIssueResult)
  - No LLM calls
  - Family/procedural retrieval not regressed
"""
from __future__ import annotations

import os
import pytest

QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
COLLECTION_NAME = "russian_laws_v1"


def _ready() -> bool:
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


_READY = _ready()

pytestmark = pytest.mark.skipif(
    not _READY,
    reason="Collection not ready — run Steps 9-10 ingest first",
)

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from app.core.config import get_settings
from app.modules.common.embeddings.provider import EmbeddingService
from app.modules.russia.retrieval.service import RussianRetrievalService
from app.modules.russia.retrieval.interpreter_issue import (
    InterpreterIssueRetrieval,
    InterpreterIssueResult,
    IssueEvidence,
)

_IDF_PATH_DEFAULT = "storage/idf_russian_laws_v1.json"
_PRIMARY_LAW = "local:ru/gpk"
_SUPPORT_LAWS = {"local:ru/echr", "local:ru/fl115"}


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


@pytest.fixture(scope="session")
def issue(service) -> InterpreterIssueRetrieval:
    return InterpreterIssueRetrieval(service)


# ---------------------------------------------------------------------------
# Output type verification
# ---------------------------------------------------------------------------

class TestOutputTypes:
    def test_returns_interpreter_issue_result(self, issue: InterpreterIssueRetrieval) -> None:
        result = issue.retrieve("переводчик в гражданском процессе")
        assert isinstance(result, InterpreterIssueResult)

    def test_primary_contains_issue_evidence(self, issue: InterpreterIssueRetrieval) -> None:
        result = issue.retrieve("переводчик в гражданском процессе")
        for e in result.primary:
            assert isinstance(e, IssueEvidence)

    def test_supporting_contains_issue_evidence(self, issue: InterpreterIssueRetrieval) -> None:
        result = issue.retrieve("иностранец без переводчика в гражданском процессе")
        for e in result.supporting:
            assert isinstance(e, IssueEvidence)

    def test_combined_contains_issue_evidence(self, issue: InterpreterIssueRetrieval) -> None:
        result = issue.retrieve("переводчик в гражданском процессе")
        for e in result.combined:
            assert isinstance(e, IssueEvidence)

    def test_query_preserved(self, issue: InterpreterIssueRetrieval) -> None:
        q = "суд не предоставил переводчика"
        result = issue.retrieve(q)
        assert result.query == q

    def test_evidence_fields_populated(self, issue: InterpreterIssueRetrieval) -> None:
        result = issue.retrieve("переводчик в гражданском процессе")
        assert result.primary
        e = result.primary[0]
        assert e.chunk_id
        assert e.law_id
        assert e.law_short
        assert len(e.text.strip()) > 0
        assert isinstance(e.is_tombstone, bool)
        assert e.source_role in {"primary", "supporting"}
        assert isinstance(e.score, float)


# ---------------------------------------------------------------------------
# Primary results — always GPK
# ---------------------------------------------------------------------------

class TestPrimaryAlwaysGPK:
    def test_court_no_interpreter_primary_gpk(self, issue: InterpreterIssueRetrieval) -> None:
        """суд не предоставил переводчика → primary from GPK."""
        result = issue.retrieve("суд не предоставил переводчика")
        assert result.primary, "No primary results"
        for e in result.primary:
            assert e.law_id == _PRIMARY_LAW, (
                f"Non-GPK in primary: {e.law_id!r} article={e.article_num}"
            )

    def test_did_not_understand_language_primary_gpk(self, issue: InterpreterIssueRetrieval) -> None:
        """я не понимал язык заседания → primary from GPK."""
        result = issue.retrieve("я не понимал язык заседания")
        assert result.primary
        for e in result.primary:
            assert e.law_id == _PRIMARY_LAW, (
                f"Non-GPK in primary: {e.law_id!r}"
            )

    def test_foreigner_no_interpreter_primary_gpk(self, issue: InterpreterIssueRetrieval) -> None:
        """иностранец без переводчика → primary from GPK."""
        result = issue.retrieve("иностранец без переводчика в гражданском процессе")
        assert result.primary
        for e in result.primary:
            assert e.law_id == _PRIMARY_LAW

    def test_right_to_interpreter_primary_gpk(self, issue: InterpreterIssueRetrieval) -> None:
        """право на переводчика → primary from GPK."""
        result = issue.retrieve("право на переводчика в российском суде")
        assert result.primary
        for e in result.primary:
            assert e.law_id == _PRIMARY_LAW

    def test_language_proceedings_primary_gpk(self, issue: InterpreterIssueRetrieval) -> None:
        """язык судопроизводства → primary from GPK."""
        result = issue.retrieve("язык судопроизводства")
        assert result.primary
        for e in result.primary:
            assert e.law_id == _PRIMARY_LAW

    def test_primary_source_role(self, issue: InterpreterIssueRetrieval) -> None:
        """All primary evidence must have source_role='primary'."""
        result = issue.retrieve("переводчик в гражданском процессе")
        for e in result.primary:
            assert e.source_role == "primary", (
                f"Primary evidence has wrong role: {e.source_role!r}"
            )

    def test_primary_has_nonempty_text(self, issue: InterpreterIssueRetrieval) -> None:
        result = issue.retrieve("переводчик в гражданском процессе")
        for e in result.primary:
            assert len(e.text.strip()) > 0


# ---------------------------------------------------------------------------
# Supporting results — ECHR/FL115 when relevant
# ---------------------------------------------------------------------------

class TestSupportingResults:
    def test_foreigner_query_has_support(self, issue: InterpreterIssueRetrieval) -> None:
        """иностранец без переводчика — support results from ECHR or FL115."""
        result = issue.retrieve(
            "иностранец без переводчика в гражданском процессе",
            top_k_primary=5,
            top_k_support=3,
        )
        assert result.supporting, (
            "No support results for foreigner/interpreter query — "
            "expected ECHR or FL115 to appear"
        )

    def test_support_only_from_valid_laws(self, issue: InterpreterIssueRetrieval) -> None:
        """Supporting results must come only from ECHR or FL115."""
        result = issue.retrieve(
            "иностранец без переводчика в гражданском процессе",
            top_k_primary=5,
            top_k_support=5,
        )
        for e in result.supporting:
            assert e.law_id in _SUPPORT_LAWS, (
                f"Unexpected law in supporting results: {e.law_id!r}"
            )

    def test_fair_trial_query_has_echr_support(self, issue: InterpreterIssueRetrieval) -> None:
        """'право на справедливое судебное разбирательство' → ECHR Art.6 in support."""
        result = issue.retrieve(
            "право на справедливое судебное разбирательство",
            top_k_primary=5,
            top_k_support=3,
        )
        support_law_ids = {e.law_id for e in result.supporting}
        assert "local:ru/echr" in support_law_ids, (
            f"ECHR not in support for fair trial query: {support_law_ids}"
        )

    def test_foreigner_query_has_fl115_support(self, issue: InterpreterIssueRetrieval) -> None:
        """иностранец без переводчика — FL115 must appear in support."""
        result = issue.retrieve(
            "иностранец без переводчика в гражданском процессе",
            top_k_primary=5,
            top_k_support=5,
        )
        support_law_ids = {e.law_id for e in result.supporting}
        assert "local:ru/fl115" in support_law_ids, (
            f"FL115 not in support for foreigner/interpreter query: {support_law_ids}"
        )

    def test_support_source_role(self, issue: InterpreterIssueRetrieval) -> None:
        """All supporting evidence must have source_role='supporting'."""
        result = issue.retrieve(
            "иностранец без переводчика в гражданском процессе",
            top_k_primary=5,
            top_k_support=3,
        )
        for e in result.supporting:
            assert e.source_role == "supporting", (
                f"Support evidence has wrong role: {e.source_role!r}"
            )

    def test_support_no_gpk(self, issue: InterpreterIssueRetrieval) -> None:
        """Supporting results must not contain GPK (GPK is in primary only)."""
        result = issue.retrieve(
            "иностранец без переводчика в гражданском процессе",
            top_k_primary=5,
            top_k_support=5,
        )
        for e in result.supporting:
            assert e.law_id != _PRIMARY_LAW, (
                f"GPK appeared in supporting results: article={e.article_num}"
            )

    def test_support_empty_is_valid(self, issue: InterpreterIssueRetrieval) -> None:
        """Support can be empty for narrow procedural queries — that is not an error."""
        result = issue.retrieve("язык судопроизводства")
        # This query may return 0 support — that is valid behaviour
        assert isinstance(result.supporting, list)
        for e in result.supporting:
            assert e.law_id in _SUPPORT_LAWS


# ---------------------------------------------------------------------------
# Combined results
# ---------------------------------------------------------------------------

class TestCombinedResults:
    def test_combined_is_primary_plus_supporting(self, issue: InterpreterIssueRetrieval) -> None:
        result = issue.retrieve("иностранец без переводчика в гражданском процессе")
        assert len(result.combined) == len(result.primary) + len(result.supporting)

    def test_combined_sorted_by_score_desc(self, issue: InterpreterIssueRetrieval) -> None:
        result = issue.retrieve("иностранец без переводчика в гражданском процессе")
        scores = [e.score for e in result.combined]
        assert scores == sorted(scores, reverse=True), (
            f"Combined results not sorted by score: {scores}"
        )

    def test_combined_contains_gpk(self, issue: InterpreterIssueRetrieval) -> None:
        result = issue.retrieve("переводчик в гражданском процессе")
        law_ids = {e.law_id for e in result.combined}
        assert _PRIMARY_LAW in law_ids

    def test_combined_roles_correct(self, issue: InterpreterIssueRetrieval) -> None:
        """Combined evidence must preserve source_role from primary/supporting."""
        result = issue.retrieve("иностранец без переводчика в гражданском процессе")
        for e in result.combined:
            if e.law_id == _PRIMARY_LAW:
                assert e.source_role == "primary"
            elif e.law_id in _SUPPORT_LAWS:
                assert e.source_role == "supporting"

    def test_combined_nonempty_for_all_queries(self, issue: InterpreterIssueRetrieval) -> None:
        for q in [
            "суд не предоставил переводчика",
            "я не понимал язык заседания",
            "иностранец без переводчика в гражданском процессе",
            "право на переводчика в российском суде",
        ]:
            result = issue.retrieve(q)
            assert result.combined, f"No combined results for query: {q!r}"


# ---------------------------------------------------------------------------
# Top-k constraints
# ---------------------------------------------------------------------------

class TestTopKConstraints:
    def test_primary_top_k_respected(self, issue: InterpreterIssueRetrieval) -> None:
        for k in [1, 3, 5]:
            result = issue.retrieve("переводчик в гражданском процессе", top_k_primary=k)
            assert len(result.primary) <= k, (
                f"primary has {len(result.primary)} results but top_k_primary={k}"
            )

    def test_support_top_k_respected(self, issue: InterpreterIssueRetrieval) -> None:
        result = issue.retrieve(
            "иностранец без переводчика в гражданском процессе",
            top_k_primary=5,
            top_k_support=2,
        )
        assert len(result.supporting) <= 2, (
            f"supporting has {len(result.supporting)} but top_k_support=2"
        )


# ---------------------------------------------------------------------------
# Exact article lookup via interpreter issue retrieval
# ---------------------------------------------------------------------------

class TestExactLookup:
    def test_article_162_primary_score_one(self, issue: InterpreterIssueRetrieval) -> None:
        """'ст. 162 гпк рф переводчик' → primary has score=1.0."""
        result = issue.retrieve("ст. 162 гпк рф переводчик", top_k_primary=5)
        assert result.primary, "No primary results for exact article lookup"
        for e in result.primary:
            assert e.score == 1.0, f"Exact lookup score should be 1.0, got {e.score}"
            assert e.law_id == _PRIMARY_LAW

    def test_article_9_primary_exact(self, issue: InterpreterIssueRetrieval) -> None:
        """'гпк рф статья 9' → primary has exact lookup results."""
        result = issue.retrieve("гпк рф статья 9", top_k_primary=5)
        assert result.primary
        for e in result.primary:
            assert e.score == 1.0
            assert e.law_id == _PRIMARY_LAW
            assert e.article_num == "9"

    def test_exact_lookup_still_produces_support(self, issue: InterpreterIssueRetrieval) -> None:
        """Even in exact-lookup mode, support pass runs independently."""
        result = issue.retrieve(
            "ст. 162 гпк рф переводчик",
            top_k_primary=5,
            top_k_support=5,
        )
        # Support pass should still run — result may or may not find ECHR/FL115
        assert isinstance(result.supporting, list)


# ---------------------------------------------------------------------------
# No LLM (structural test)
# ---------------------------------------------------------------------------

def test_interpreter_issue_does_not_import_llm() -> None:
    """interpreter_issue.py must not import any LLM provider."""
    import app.modules.russia.retrieval.interpreter_issue as mod
    import sys

    llm_modules = {"openai", "anthropic", "app.modules.common.llm"}
    for llm_mod in llm_modules:
        assert llm_mod not in sys.modules or llm_mod not in mod.__dict__, (
            f"interpreter_issue imported LLM module: {llm_mod}"
        )
    assert "app.modules.russia.retrieval.interpreter_issue" in sys.modules


# ---------------------------------------------------------------------------
# Regression — existing retrieval not broken
# ---------------------------------------------------------------------------

class TestNoRegression:
    def test_family_law_not_affected(self, service: RussianRetrievalService) -> None:
        """Family law topic search still returns SK."""
        results = service.topic_search("лишение родительских прав", top_k=10)
        for r in results:
            assert r.law_id == "local:ru/sk"

    def test_gpk_appeal_retrieval_not_affected(self, service: RussianRetrievalService) -> None:
        """Procedural topic search still returns GPK for non-interpreter queries."""
        results = service.topic_search("апелляционная жалоба гпк рф", top_k=10)
        for r in results:
            assert r.law_id == "local:ru/gpk"

    def test_exact_lookup_gpk_not_affected(self, service: RussianRetrievalService) -> None:
        result = service.get_article("local:ru/gpk", "113")
        assert result.hit

    def test_exact_lookup_sk_not_affected(self, service: RussianRetrievalService) -> None:
        result = service.get_article("local:ru/sk", "69")
        assert result.hit

    def test_interpreter_issue_does_not_pollute_service(
        self, issue: InterpreterIssueRetrieval, service: RussianRetrievalService
    ) -> None:
        """Running InterpreterIssueRetrieval does not alter service state."""
        _ = issue.retrieve("переводчик в гражданском процессе")
        # SK family law still works after interpreter issue retrieval
        results = service.topic_search("порядок общения с ребенком", top_k=5)
        assert results
        for r in results:
            assert r.law_id == "local:ru/sk"
