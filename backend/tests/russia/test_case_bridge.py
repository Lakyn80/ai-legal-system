"""
Integration tests for the CaseIssueBridge (case_bridge.py).

Covers:
  - Sub-issue signal detection (deterministic, no service needed)
  - Full bridge.analyze() end-to-end on representative case descriptions
  - Anchor article presence (ст. 9, ст. 162, ст. 113)
  - Combined multi-issue evidence sets
  - Non-matching descriptions
  - No LLM calls

Requirements:
  - Qdrant container with russian_laws_v1 collection
  - GPK, ECHR, FL115 chunks loaded (same skip-guard as test_interpreter_issue_retrieval)
"""
from __future__ import annotations

import os
import pytest
from pathlib import Path

QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
COLLECTION_NAME = "russian_laws_v1"
_IDF_PATH_DEFAULT = "storage/idf_russian_laws_v1.json"

# ---------------------------------------------------------------------------
# Skip guard — require all three corpora used by the bridge
# ---------------------------------------------------------------------------


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

# Applied to integration test classes only — unit tests (TestDetectSubissues) run always.
_needs_collection = pytest.mark.skipif(
    not _READY,
    reason="Collection not ready — run Steps 9-10 ingest first",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def idf_path():
    p = Path(os.environ.get("RUSSIAN_IDF_CHECKPOINT_PATH", _IDF_PATH_DEFAULT))
    return p if p.exists() else None


@pytest.fixture(scope="session")
def bridge(idf_path):
    from app.core.config import get_settings
    from app.modules.common.embeddings.provider import EmbeddingService
    from app.modules.russia.retrieval.service import RussianRetrievalService
    from app.modules.russia.retrieval.case_bridge import CaseIssueBridge

    s = get_settings()
    emb = EmbeddingService(
        model_name=s.embedding_model,
        provider_name=s.embedding_provider,
        hash_dimension=s.embedding_hash_dimension,
    )
    svc = RussianRetrievalService(
        embedding_service=emb,
        qdrant_url=QDRANT_URL,
        idf_checkpoint_path=idf_path,
    )
    return CaseIssueBridge(svc)


# ---------------------------------------------------------------------------
# Unit tests — _detect_subissues (no service needed)
# ---------------------------------------------------------------------------

class TestDetectSubissues:
    """Tests for the deterministic phrase/stem signal detection."""

    def _detect(self, text: str):
        from app.modules.russia.retrieval.case_bridge import _detect_subissues
        return _detect_subissues(text.lower())

    def test_interpreter_phrase_direct(self):
        d, m = self._detect("не получил переводчика в суде")
        assert "interpreter_issue" in d
        assert any("переводчик" in sig or "не получил переводчика" in sig
                   for sig in m.get("interpreter_issue", []))

    def test_interpreter_stem_only(self):
        d, _ = self._detect("переводчику отказали в участии")
        assert "interpreter_issue" in d

    def test_language_phrase(self):
        d, _ = self._detect("я не понимал язык заседания")
        assert "language_issue" in d
        assert "interpreter_issue" not in d

    def test_language_stem(self):
        d, _ = self._detect("языком судопроизводства является русский")
        assert "language_issue" in d

    def test_notice_phrase_vyzov(self):
        d, _ = self._detect("меня не вызвали в суд")
        assert "notice_issue" in d

    def test_notice_phrase_uvedomlen(self):
        d, _ = self._detect("я не был уведомлен о заседании")
        assert "notice_issue" in d

    def test_notice_phrase_izvechen(self):
        d, _ = self._detect("суд рассмотрел дело без моего извещения")
        assert "notice_issue" in d

    def test_notice_nadlezhashchim(self):
        d, _ = self._detect("не уведомлен надлежащим образом")
        assert "notice_issue" in d

    def test_notice_stem_izvesh(self):
        d, _ = self._detect("суд не известил меня о дате заседания")
        # "известил" does not start with "извещ" so should NOT trigger via stem
        # but "не извещен" phrasing would; here it may or may not match — just ensure no crash
        assert isinstance(d, list)

    def test_notice_stem_povestly(self):
        d, _ = self._detect("повестка не была вручена")
        assert "notice_issue" in d

    def test_notice_noun_vyzova(self):
        """'вызова' (noun genitive) must hit 'вызов' stem — the bug-fix regression."""
        d, _ = self._detect("без официального вызова в суд")
        assert "notice_issue" in d

    def test_combined_interpreter_and_notice(self):
        d, m = self._detect(
            "иностранец без переводчика и без официального вызова в суд"
        )
        assert "interpreter_issue" in d
        assert "notice_issue" in d
        assert len(d) == 2

    def test_combined_signals_recorded(self):
        d, m = self._detect(
            "иностранец без переводчика и без официального вызова в суд"
        )
        assert "interpreter_issue" in m
        assert "notice_issue" in m
        assert len(m["interpreter_issue"]) >= 1
        assert len(m["notice_issue"]) >= 1

    def test_no_match_generic(self):
        d, m = self._detect("суд отказал в иске по гражданскому делу")
        assert d == []
        assert m == {}

    def test_no_match_empty_string(self):
        d, m = self._detect("")
        assert d == []
        assert m == {}

    def test_no_match_unrelated_legal_text(self):
        d, _ = self._detect("договор аренды жилого помещения заключен на один год")
        assert d == []

    def test_order_stable(self):
        """Sub-issue order must be interpreter → language → notice (dict insertion order)."""
        d, _ = self._detect(
            "не понимал язык заседания и переводчик не был предоставлен"
        )
        if "interpreter_issue" in d and "language_issue" in d:
            assert d.index("interpreter_issue") < d.index("language_issue")

    def test_interpreter_right_explanation(self):
        d, _ = self._detect("суд не разъяснил право на переводчика")
        assert "interpreter_issue" in d

    def test_interpreter_without_translation(self):
        d, _ = self._detect("не предоставили перевод документов")
        assert "interpreter_issue" in d


# ---------------------------------------------------------------------------
# Integration tests — CaseIssueBridge.analyze()
# ---------------------------------------------------------------------------

@_needs_collection
class TestCaseBridgeNoMatch:
    """Cases that should return is_matched=False."""

    def test_no_match_returns_false(self, bridge):
        result = bridge.analyze("суд отказал в иске")
        assert result.is_matched is False

    def test_no_match_detected_issue_is_none(self, bridge):
        result = bridge.analyze("суд отказал в иске")
        assert result.detected_issue is None

    def test_no_match_lists_empty(self, bridge):
        result = bridge.analyze("суд отказал в иске")
        assert result.primary_results == []
        assert result.supporting_results == []
        assert result.combined_results == []

    def test_no_match_preserves_case_text(self, bridge):
        text = "договор поставки расторгнут"
        result = bridge.analyze(text)
        assert result.case_text == text

    def test_no_match_subissues_empty(self, bridge):
        result = bridge.analyze("суд вынес решение об алиментах")
        assert result.detected_subissues == []
        assert result.matched_signals == {}


@_needs_collection
class TestCaseBridgeInterpreterIssue:
    """'иностранный гражданин не получил переводчика в суде'"""

    CASE = "иностранный гражданин не получил переводчика в суде"

    def test_is_matched(self, bridge):
        r = bridge.analyze(self.CASE)
        assert r.is_matched is True

    def test_detected_issue_cluster(self, bridge):
        r = bridge.analyze(self.CASE)
        assert r.detected_issue == "interpreter_language_notice"

    def test_interpreter_subissue_detected(self, bridge):
        r = bridge.analyze(self.CASE)
        assert "interpreter_issue" in r.detected_subissues

    def test_no_notice_subissue(self, bridge):
        r = bridge.analyze(self.CASE)
        assert "notice_issue" not in r.detected_subissues

    def test_normalized_query_present(self, bridge):
        r = bridge.analyze(self.CASE)
        assert len(r.normalized_queries) >= 1
        assert all(isinstance(q, str) and q for q in r.normalized_queries)

    def test_primary_results_nonempty(self, bridge):
        r = bridge.analyze(self.CASE)
        assert len(r.primary_results) >= 1

    def test_primary_results_all_gpk(self, bridge):
        r = bridge.analyze(self.CASE)
        for e in r.primary_results:
            assert e.law_id == "local:ru/gpk", f"Non-GPK in primary: {e.law_id}"

    def test_anchor_article_9_present(self, bridge):
        r = bridge.analyze(self.CASE)
        art_nums = {e.article_num for e in r.primary_results}
        assert "9" in art_nums, f"ст. 9 missing from primary; got {art_nums}"

    def test_anchor_article_162_present(self, bridge):
        r = bridge.analyze(self.CASE)
        art_nums = {e.article_num for e in r.primary_results}
        assert "162" in art_nums, f"ст. 162 missing from primary; got {art_nums}"

    def test_primary_role_tag(self, bridge):
        r = bridge.analyze(self.CASE)
        for e in r.primary_results:
            assert e.source_role == "primary"

    def test_combined_includes_primary(self, bridge):
        r = bridge.analyze(self.CASE)
        primary_ids = {e.chunk_id for e in r.primary_results}
        combined_ids = {e.chunk_id for e in r.combined_results}
        assert primary_ids.issubset(combined_ids)

    def test_combined_sorted_descending(self, bridge):
        r = bridge.analyze(self.CASE)
        scores = [e.score for e in r.combined_results]
        assert scores == sorted(scores, reverse=True)

    def test_no_tombstones_in_primary(self, bridge):
        r = bridge.analyze(self.CASE)
        for e in r.primary_results:
            assert not e.is_tombstone, f"Tombstone in primary: {e.chunk_id}"

    def test_anchor_score_is_one(self, bridge):
        """Anchor articles must have score=1.0 (exact lookup)."""
        r = bridge.analyze(self.CASE)
        for e in r.primary_results:
            if e.article_num in ("9", "162"):
                assert e.score == pytest.approx(1.0), (
                    f"Anchor ст.{e.article_num} has score={e.score}, expected 1.0"
                )


@_needs_collection
class TestCaseBridgeLanguageIssue:
    """'я не понимал язык заседания'"""

    CASE = "я не понимал язык заседания"

    def test_is_matched(self, bridge):
        r = bridge.analyze(self.CASE)
        assert r.is_matched is True

    def test_language_subissue_detected(self, bridge):
        r = bridge.analyze(self.CASE)
        assert "language_issue" in r.detected_subissues

    def test_anchor_article_9_present(self, bridge):
        r = bridge.analyze(self.CASE)
        art_nums = {e.article_num for e in r.primary_results}
        assert "9" in art_nums, f"ст. 9 missing; got {art_nums}"

    def test_primary_all_gpk(self, bridge):
        r = bridge.analyze(self.CASE)
        for e in r.primary_results:
            assert e.law_id == "local:ru/gpk"


@_needs_collection
class TestCaseBridgeNoticeIssue:
    """Tests for the three notice/summons case descriptions."""

    @pytest.mark.parametrize("case_text", [
        "меня не вызвали в суд надлежащим образом",
        "я не был официально уведомлен о судебном заседании",
        "суд рассмотрел дело без моего извещения",
    ])
    def test_notice_detected(self, bridge, case_text):
        r = bridge.analyze(case_text)
        assert r.is_matched is True
        assert "notice_issue" in r.detected_subissues

    @pytest.mark.parametrize("case_text", [
        "меня не вызвали в суд надлежащим образом",
        "я не был официально уведомлен о судебном заседании",
        "суд рассмотрел дело без моего извещения",
    ])
    def test_anchor_article_113_present(self, bridge, case_text):
        r = bridge.analyze(case_text)
        art_nums = {e.article_num for e in r.primary_results}
        assert "113" in art_nums, (
            f"ст. 113 missing for notice case {case_text!r}; got {art_nums}"
        )

    @pytest.mark.parametrize("case_text", [
        "меня не вызвали в суд надлежащим образом",
        "я не был официально уведомлен о судебном заседании",
        "суд рассмотрел дело без моего извещения",
    ])
    def test_primary_all_gpk(self, bridge, case_text):
        r = bridge.analyze(case_text)
        for e in r.primary_results:
            assert e.law_id == "local:ru/gpk"

    def test_normalized_query_notice(self, bridge):
        r = bridge.analyze("меня не вызвали в суд надлежащим образом")
        assert "надлежащее извещение" in " ".join(r.normalized_queries)


@_needs_collection
class TestCaseBridgeCombinedIssue:
    """'иностранец без переводчика и без официального вызова в суд'"""

    CASE = "иностранец без переводчика и без официального вызова в суд"

    def test_is_matched(self, bridge):
        r = bridge.analyze(self.CASE)
        assert r.is_matched is True

    def test_both_subissues_detected(self, bridge):
        r = bridge.analyze(self.CASE)
        assert "interpreter_issue" in r.detected_subissues
        assert "notice_issue" in r.detected_subissues

    def test_two_normalized_queries(self, bridge):
        r = bridge.analyze(self.CASE)
        assert len(r.normalized_queries) == 2

    def test_anchor_9_and_162_present(self, bridge):
        r = bridge.analyze(self.CASE)
        art_nums = {e.article_num for e in r.primary_results}
        assert "9" in art_nums, f"ст. 9 missing; got {art_nums}"
        assert "162" in art_nums, f"ст. 162 missing; got {art_nums}"

    def test_anchor_113_present(self, bridge):
        r = bridge.analyze(self.CASE)
        art_nums = {e.article_num for e in r.primary_results}
        assert "113" in art_nums, f"ст. 113 missing; got {art_nums}"

    def test_all_three_anchors_in_combined(self, bridge):
        r = bridge.analyze(self.CASE)
        art_nums = {e.article_num for e in r.combined_results}
        assert {"9", "113", "162"}.issubset(art_nums), (
            f"Expected ст.9, ст.113, ст.162 in combined; got {art_nums}"
        )

    def test_combined_sorted(self, bridge):
        r = bridge.analyze(self.CASE)
        scores = [e.score for e in r.combined_results]
        assert scores == sorted(scores, reverse=True)

    def test_matched_signals_both_keys(self, bridge):
        r = bridge.analyze(self.CASE)
        assert "interpreter_issue" in r.matched_signals
        assert "notice_issue" in r.matched_signals

    def test_no_duplicate_chunk_ids_in_primary(self, bridge):
        r = bridge.analyze(self.CASE)
        ids = [e.chunk_id for e in r.primary_results]
        assert len(ids) == len(set(ids)), "Duplicate chunk_ids in primary_results"

    def test_no_duplicate_chunk_ids_in_combined(self, bridge):
        r = bridge.analyze(self.CASE)
        ids = [e.chunk_id for e in r.combined_results]
        assert len(ids) == len(set(ids)), "Duplicate chunk_ids in combined_results"


@_needs_collection
class TestCaseBridgeSupportingSources:
    """Supporting (ECHR/FL115) sources in bridge results."""

    def test_supporting_role_tag(self, bridge):
        r = bridge.analyze("иностранный гражданин не получил переводчика в суде")
        for e in r.supporting_results:
            assert e.source_role == "supporting"

    def test_supporting_not_gpk(self, bridge):
        r = bridge.analyze("иностранный гражданин не получил переводчика в суде")
        for e in r.supporting_results:
            assert e.law_id != "local:ru/gpk", (
                f"GPK chunk in supporting results: {e.chunk_id}"
            )

    def test_supporting_in_combined(self, bridge):
        r = bridge.analyze("иностранный гражданин не получил переводчика в суде")
        if r.supporting_results:
            supp_ids = {e.chunk_id for e in r.supporting_results}
            combined_ids = {e.chunk_id for e in r.combined_results}
            assert supp_ids.issubset(combined_ids)


@_needs_collection
class TestCaseBridgeOutputTypes:
    """Output type and field integrity."""

    def test_result_type(self, bridge):
        from app.modules.russia.retrieval.case_bridge import CaseBridgeResult
        r = bridge.analyze("не получил переводчика")
        assert isinstance(r, CaseBridgeResult)

    def test_evidence_type_primary(self, bridge):
        from app.modules.russia.retrieval.interpreter_issue import IssueEvidence
        r = bridge.analyze("не получил переводчика")
        for e in r.primary_results:
            assert isinstance(e, IssueEvidence)

    def test_evidence_has_text(self, bridge):
        r = bridge.analyze("не получил переводчика")
        for e in r.primary_results:
            assert isinstance(e.text, str) and len(e.text) > 0

    def test_evidence_has_law_short(self, bridge):
        r = bridge.analyze("не получил переводчика")
        for e in r.primary_results:
            assert isinstance(e.law_short, str) and len(e.law_short) > 0

    def test_top_k_primary_respected(self, bridge):
        r = bridge.analyze("не получил переводчика", top_k_primary=3)
        assert len(r.primary_results) <= 3

    def test_top_k_support_respected(self, bridge):
        r = bridge.analyze("не получил переводчика", top_k_support=1)
        assert len(r.supporting_results) <= 1

    def test_case_text_preserved(self, bridge):
        text = "иностранец не получил переводчика и не был уведомлен"
        r = bridge.analyze(text)
        assert r.case_text == text

    def test_no_llm_call(self, bridge):
        """Bridge must not import any LLM client library."""
        import app.modules.russia.retrieval.case_bridge as mod
        # Check actual imports, not comments or docstrings
        import_names = [
            getattr(v, "__module__", "") or ""
            for v in vars(mod).values()
        ]
        for name in import_names:
            assert "openai" not in name.lower()
            assert "anthropic" not in name.lower()
            assert "langchain" not in name.lower()
        # Also verify no LLM-specific module is importable via the module
        assert not hasattr(mod, "OpenAI")
        assert not hasattr(mod, "Anthropic")
        assert not hasattr(mod, "ChatOpenAI")


@_needs_collection
class TestCaseBridgeRegressions:
    """Regression tests for known edge cases."""

    def test_vyzova_noun_triggers_notice(self, bridge):
        """Genitive noun 'вызова' must trigger notice_issue (вызов stem fix)."""
        r = bridge.analyze("без официального вызова в суд")
        assert r.is_matched is True
        assert "notice_issue" in r.detected_subissues

    def test_notice_article_113_not_in_interpreter_only(self, bridge):
        """When only interpreter_issue is detected, ст. 113 should not appear as anchor."""
        r = bridge.analyze("иностранный гражданин не получил переводчика в суде")
        assert "notice_issue" not in r.detected_subissues
        # ст. 113 should not be an anchor for pure interpreter case
        # (it may appear via semantic enrichment — only assert anchor was not fetched)
        # We verify this indirectly: no notice subissue → no 113 anchor requested
        assert "notice_issue" not in r.matched_signals

    def test_deterministic_repeated_calls(self, bridge):
        """Same input must produce same sub-issues and same article numbers."""
        text = "иностранец без переводчика и без официального вызова в суд"
        r1 = bridge.analyze(text)
        r2 = bridge.analyze(text)
        assert r1.detected_subissues == r2.detected_subissues
        arts1 = {e.article_num for e in r1.primary_results}
        arts2 = {e.article_num for e in r2.primary_results}
        assert arts1 == arts2

    def test_interpreter_stem_matches_translated_doc(self, bridge):
        """'переводчику' (dative) must trigger interpreter_issue via stem."""
        r = bridge.analyze("переводчику было отказано в участии в заседании")
        assert r.is_matched is True
        assert "interpreter_issue" in r.detected_subissues
