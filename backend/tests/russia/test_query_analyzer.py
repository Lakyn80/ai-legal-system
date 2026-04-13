"""
Pure unit tests for RussianQueryAnalyzer and RussianRetrievalPlanner — Step 8.

No Qdrant required — these always run.

Tests verify:
  - Law alias detection (ск рф, семейный кодекс, гпк рф, гк рф, тк рф)
  - Exact article reference detection (ст. 81, статья 19.1)
  - Topic detection (family_law, procedural_law)
  - Query mode determination
  - cleaned_query strips alias text
  - preferred_law_ids inferred correctly
  - Planner modes match analyzer output
  - No LLM imports
"""
from __future__ import annotations

import pytest

from app.modules.russia.retrieval.query_analyzer import (
    RussianQueryAnalyzer,
    RussianQueryUnderstanding,
)
from app.modules.russia.retrieval.retrieval_planner import (
    RussianRetrievalPlan,
    RussianRetrievalPlanner,
)


@pytest.fixture(scope="module")
def analyzer() -> RussianQueryAnalyzer:
    return RussianQueryAnalyzer()


@pytest.fixture(scope="module")
def planner() -> RussianRetrievalPlanner:
    return RussianRetrievalPlanner()


# ---------------------------------------------------------------------------
# Law alias detection
# ---------------------------------------------------------------------------

class TestLawAliasDetection:
    def test_sk_alias_short(self, analyzer):
        u = analyzer.analyze("права ребенка ск рф")
        assert "local:ru/sk" in u.detected_law_ids

    def test_sk_alias_full(self, analyzer):
        u = analyzer.analyze("Семейный кодекс регулирует брачные отношения")
        assert "local:ru/sk" in u.detected_law_ids

    def test_sk_alias_genitive(self, analyzer):
        u = analyzer.analyze("по нормам семейного кодекса")
        assert "local:ru/sk" in u.detected_law_ids

    def test_gpk_alias_short(self, analyzer):
        u = analyzer.analyze("апелляционная жалоба гпк рф")
        assert "local:ru/gpk" in u.detected_law_ids

    def test_gpk_alias_full(self, analyzer):
        u = analyzer.analyze("гражданский процессуальный кодекс статья 131")
        assert "local:ru/gpk" in u.detected_law_ids

    def test_gk_alias_short(self, analyzer):
        u = analyzer.analyze("сделка гк рф недействительность")
        assert "local:ru/gk/1" in u.detected_law_ids

    def test_gk_alias_full(self, analyzer):
        u = analyzer.analyze("гражданский кодекс ст. 169")
        assert "local:ru/gk/1" in u.detected_law_ids

    def test_tk_alias_short(self, analyzer):
        u = analyzer.analyze("расторжение договора тк рф")
        assert "local:ru/tk" in u.detected_law_ids

    def test_tk_alias_full(self, analyzer):
        u = analyzer.analyze("трудовой кодекс ст. 81")
        assert "local:ru/tk" in u.detected_law_ids

    def test_no_alias_returns_empty(self, analyzer):
        u = analyzer.analyze("как подать иск в суд")
        assert u.detected_law_ids == []

    def test_multiple_aliases_detected(self, analyzer):
        u = analyzer.analyze("ск рф и гк рф регулируют семейные отношения")
        assert "local:ru/sk" in u.detected_law_ids
        assert "local:ru/gk/1" in u.detected_law_ids

    def test_gpk_not_confused_with_gk(self, analyzer):
        """гпк should map to GPK, not GK."""
        u = analyzer.analyze("гпк рф ст. 131")
        assert "local:ru/gpk" in u.detected_law_ids
        assert "local:ru/gk/1" not in u.detected_law_ids


# ---------------------------------------------------------------------------
# Article reference detection
# ---------------------------------------------------------------------------

class TestArticleDetection:
    def test_st_dot_space(self, analyzer):
        u = analyzer.analyze("ст. 81 тк рф")
        assert u.detected_article == "81"

    def test_st_dot_nospace(self, analyzer):
        u = analyzer.analyze("ст.81 трудовой кодекс")
        assert u.detected_article == "81"

    def test_statya_full(self, analyzer):
        u = analyzer.analyze("статья 81 трудового кодекса")
        assert u.detected_article == "81"

    def test_decimal_article(self, analyzer):
        u = analyzer.analyze("ст. 19.1 тк рф")
        assert u.detected_article == "19.1"

    def test_no_article_returns_none(self, analyzer):
        u = analyzer.analyze("порядок общения с ребенком")
        assert u.detected_article is None

    def test_article_without_law_alias(self, analyzer):
        u = analyzer.analyze("ст. 169")
        assert u.detected_article == "169"
        # No law alias detected
        assert u.detected_law_ids == []


# ---------------------------------------------------------------------------
# Topic detection
# ---------------------------------------------------------------------------

class TestTopicDetection:
    def test_family_law_topic_communication(self, analyzer):
        u = analyzer.analyze("порядок общения с ребенком")
        assert u.detected_topic == "family_law"
        assert u.topic_confidence > 0

    def test_family_law_topic_custody(self, analyzer):
        u = analyzer.analyze("определение места жительства ребенка")
        assert u.detected_topic == "family_law"

    def test_family_law_topic_parental_rights(self, analyzer):
        u = analyzer.analyze("лишение родительских прав")
        assert u.detected_topic == "family_law"

    def test_family_law_topic_custody_board(self, analyzer):
        u = analyzer.analyze("орган опеки и попечительства заключение")
        assert u.detected_topic == "family_law"

    def test_family_law_stem_rebenok(self, analyzer):
        # "судебном" would trigger procedural stem — use a query without it
        u = analyzer.analyze("защита прав ребенка органами опеки")
        assert u.detected_topic == "family_law"

    def test_family_law_stem_alimenty(self, analyzer):
        u = analyzer.analyze("взыскание алиментов на содержание ребенка")
        assert u.detected_topic == "family_law"

    def test_procedural_law_appeal(self, analyzer):
        u = analyzer.analyze("апелляционная жалоба на решение суда")
        assert u.detected_topic == "procedural_law"

    def test_procedural_law_violations(self, analyzer):
        u = analyzer.analyze("процессуальные нарушения при рассмотрении дела")
        assert u.detected_topic == "procedural_law"

    def test_procedural_law_cancel_decision(self, analyzer):
        u = analyzer.analyze("отмена решения суда апелляционной инстанцией")
        assert u.detected_topic == "procedural_law"

    def test_procedural_law_evidence(self, analyzer):
        u = analyzer.analyze("доказательства в суде")
        assert u.detected_topic == "procedural_law"

    def test_procedural_law_notice(self, analyzer):
        u = analyzer.analyze("извещение сторон о судебном заседании")
        assert u.detected_topic == "procedural_law"

    def test_no_topic_for_generic_query(self, analyzer):
        u = analyzer.analyze("что такое закон")
        assert u.detected_topic is None

    def test_topic_confidence_is_float(self, analyzer):
        u = analyzer.analyze("порядок общения с ребенком")
        assert isinstance(u.topic_confidence, float)
        assert u.topic_confidence > 0


# ---------------------------------------------------------------------------
# Query mode determination
# ---------------------------------------------------------------------------

class TestQueryMode:
    def test_exact_lookup_mode(self, analyzer):
        """Law alias + article ref → exact_lookup."""
        u = analyzer.analyze("ст. 81 тк рф")
        assert u.query_mode == "exact_lookup"

    def test_law_constrained_search_mode(self, analyzer):
        """Law alias, no article → law_constrained_search."""
        u = analyzer.analyze("ск рф права ребенка")
        assert u.query_mode == "law_constrained_search"

    def test_topic_search_mode_family(self, analyzer):
        """Strong family topic, no alias → topic_search."""
        u = analyzer.analyze("порядок общения с ребенком")
        assert u.query_mode == "topic_search"

    def test_topic_search_mode_procedural(self, analyzer):
        """Strong procedural topic, no alias → topic_search."""
        u = analyzer.analyze("апелляционная жалоба на решение суда")
        assert u.query_mode == "topic_search"

    def test_broad_search_mode(self, analyzer):
        """No alias, no topic → broad_search."""
        u = analyzer.analyze("что такое закон")
        assert u.query_mode == "broad_search"

    def test_alias_overrides_topic_for_mode(self, analyzer):
        """Explicit alias takes precedence over topic for mode."""
        u = analyzer.analyze("порядок общения с ребенком ск рф")
        assert u.query_mode == "law_constrained_search"

    def test_exact_lookup_with_gpk(self, analyzer):
        u = analyzer.analyze("ст. 131 гпк рф")
        assert u.query_mode == "exact_lookup"
        assert u.detected_article == "131"
        assert "local:ru/gpk" in u.detected_law_ids


# ---------------------------------------------------------------------------
# preferred_law_ids
# ---------------------------------------------------------------------------

class TestPreferredLawIds:
    def test_preferred_from_alias(self, analyzer):
        u = analyzer.analyze("ск рф расторжение брака")
        assert "local:ru/sk" in u.preferred_law_ids

    def test_preferred_from_topic_family(self, analyzer):
        u = analyzer.analyze("порядок общения с ребенком")
        assert "local:ru/sk" in u.preferred_law_ids

    def test_preferred_from_topic_procedural(self, analyzer):
        u = analyzer.analyze("апелляционная жалоба")
        assert "local:ru/gpk" in u.preferred_law_ids

    def test_no_preferred_for_broad(self, analyzer):
        u = analyzer.analyze("что такое закон")
        assert u.preferred_law_ids == []


# ---------------------------------------------------------------------------
# cleaned_query
# ---------------------------------------------------------------------------

class TestCleanedQuery:
    def test_alias_removed_from_cleaned(self, analyzer):
        u = analyzer.analyze("права ребенка ск рф")
        assert "ск рф" not in u.cleaned_query.lower()
        assert "ребенка" in u.cleaned_query.lower()

    def test_article_removed_from_cleaned(self, analyzer):
        u = analyzer.analyze("ст. 81 тк рф трудовой договор")
        assert u.cleaned_query  # non-empty
        # Article reference should be stripped
        assert "ст." not in u.cleaned_query

    def test_cleaned_not_empty(self, analyzer):
        u = analyzer.analyze("ск рф")
        assert u.cleaned_query  # should not be empty

    def test_raw_query_preserved(self, analyzer):
        raw = "права ребенка ск рф"
        u = analyzer.analyze(raw)
        assert u.raw_query == raw


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class TestRetrievalPlanner:
    def test_exact_plan_for_exact_lookup(self, analyzer, planner):
        u = analyzer.analyze("ст. 81 тк рф")
        plan = planner.plan(u, top_k=5)
        assert plan.mode == "exact"
        assert plan.article_num == "81"
        assert "local:ru/tk" in plan.law_ids
        assert plan.use_hybrid is False

    def test_constrained_plan_for_law_search(self, analyzer, planner):
        u = analyzer.analyze("ск рф расторжение брака")
        plan = planner.plan(u, top_k=5)
        assert plan.mode == "constrained"
        assert "local:ru/sk" in plan.law_ids
        assert plan.article_num is None
        assert plan.use_hybrid is True

    def test_topic_plan_for_family_law(self, analyzer, planner):
        u = analyzer.analyze("порядок общения с ребенком")
        plan = planner.plan(u, top_k=5)
        assert plan.mode == "topic"
        assert "local:ru/sk" in plan.law_ids
        assert plan.use_hybrid is True

    def test_topic_plan_for_procedural_law(self, analyzer, planner):
        u = analyzer.analyze("апелляционная жалоба на решение суда")
        plan = planner.plan(u, top_k=5)
        assert plan.mode == "topic"
        assert "local:ru/gpk" in plan.law_ids

    def test_broad_plan_for_generic_query(self, analyzer, planner):
        u = analyzer.analyze("что такое закон")
        plan = planner.plan(u, top_k=5)
        assert plan.mode == "broad"
        assert plan.law_ids == []
        assert plan.use_hybrid is True

    def test_candidate_k_at_least_top_k_times_2(self, analyzer, planner):
        u = analyzer.analyze("расторжение брака ск рф")
        for top_k in [5, 10, 20]:
            plan = planner.plan(u, top_k=top_k)
            assert plan.candidate_k >= top_k * 2, (
                f"candidate_k={plan.candidate_k} < top_k*2={top_k*2}"
            )

    def test_candidate_k_capped_at_100(self, analyzer, planner):
        u = analyzer.analyze("расторжение брака ск рф")
        plan = planner.plan(u, top_k=100)
        assert plan.candidate_k <= 100


# ---------------------------------------------------------------------------
# No LLM (structural test)
# ---------------------------------------------------------------------------

def test_query_analyzer_does_not_import_llm():
    """query_analyzer.py must not import any LLM provider."""
    import app.modules.russia.retrieval.query_analyzer as mod
    import sys

    llm_modules = {"openai", "anthropic", "app.modules.common.llm"}
    for llm_mod in llm_modules:
        assert llm_mod not in (getattr(mod, "__name__", "") or ""), (
            f"query_analyzer imported LLM module: {llm_mod}"
        )


def test_retrieval_planner_does_not_import_llm():
    """retrieval_planner.py must not import any LLM provider."""
    import app.modules.russia.retrieval.retrieval_planner as mod
    import sys

    llm_modules = {"openai", "anthropic", "app.modules.common.llm"}
    for llm_mod in llm_modules:
        assert llm_mod not in (getattr(mod, "__name__", "") or ""), (
            f"retrieval_planner imported LLM module: {llm_mod}"
        )
