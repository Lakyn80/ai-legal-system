"""
Russian retrieval planner — Step 8.

Translates a RussianQueryUnderstanding into a RussianRetrievalPlan that
specifies how to call the retrieval layer (exact lookup or hybrid search,
with optional law constraints).

Modes and their strategies
──────────────────────────
  exact_lookup          → law filter + article filter → get_article()
  law_constrained_search → hybrid search with law_id filter
  topic_search           → hybrid search with preferred law filter
                           (high confidence only — falls back to broad if
                           preferred law is absent from the collection)
  broad_search           → unconstrained hybrid search

Does NOT:
  - Call Qdrant
  - Call any LLM
  - Import ingestion modules
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.russia.retrieval.query_analyzer import (
    RussianQueryUnderstanding,
    _TOPIC_PREFERRED_LAWS,
)

# ---------------------------------------------------------------------------
# Plan dataclass
# ---------------------------------------------------------------------------

@dataclass
class RussianRetrievalPlan:
    """
    Execution plan produced by RussianRetrievalPlanner.

    All fields are consumed by RussianRetrievalService.topic_search().
    """

    mode: str
    """exact | constrained | topic | broad"""

    law_ids: list[str] = field(default_factory=list)
    """
    Law IDs to use as hard filter in Qdrant query.
    Empty list = no filter.
    For exact_lookup: single law_id (if alias detected) or empty.
    For constrained/topic: one or more law_ids to filter on.
    """

    article_num: str | None = None
    """Article number for exact lookup. None for search modes."""

    candidate_k: int = 20
    """Number of candidates to fetch per retriever before fusion / top_k truncation."""

    use_hybrid: bool = True
    """True = use hybrid (dense + sparse BM25) search. False = dense only."""


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class RussianRetrievalPlanner:
    """
    Builds a RussianRetrievalPlan from a RussianQueryUnderstanding.

    Thread-safe: no mutable state.

    Usage:
        planner = RussianRetrievalPlanner()
        plan = planner.plan(understanding, top_k=10)
    """

    def plan(
        self,
        understanding: RussianQueryUnderstanding,
        top_k: int = 10,
    ) -> RussianRetrievalPlan:
        mode = understanding.query_mode

        if mode == "exact_lookup":
            return self._exact_plan(understanding, top_k)

        if mode == "law_constrained_search":
            return self._constrained_plan(understanding, top_k)

        if mode == "topic_search":
            return self._topic_plan(understanding, top_k)

        # broad_search
        return self._broad_plan(understanding, top_k)

    # ── plan builders ─────────────────────────────────────────────────────────

    @staticmethod
    def _exact_plan(u: RussianQueryUnderstanding, top_k: int) -> RussianRetrievalPlan:
        """Exact article lookup — uses payload filter, no vector search needed."""
        return RussianRetrievalPlan(
            mode="exact",
            law_ids=list(u.detected_law_ids),
            article_num=u.detected_article,
            candidate_k=max(top_k, 10),
            use_hybrid=False,   # exact lookup bypasses vector search
        )

    @staticmethod
    def _constrained_plan(u: RussianQueryUnderstanding, top_k: int) -> RussianRetrievalPlan:
        """Law-constrained hybrid search — explicit law alias detected."""
        return RussianRetrievalPlan(
            mode="constrained",
            law_ids=list(u.detected_law_ids),
            article_num=None,
            candidate_k=_candidate_k(top_k, baseline=40),
            use_hybrid=True,
        )

    @staticmethod
    def _topic_plan(u: RussianQueryUnderstanding, top_k: int) -> RussianRetrievalPlan:
        """
        Topic-inferred law search.

        Uses preferred_law_ids as a hard filter if topic confidence is high.
        For low-confidence topics, falls back to broad search to avoid
        missing relevant results when the preferred law is absent from corpus.
        """
        # Use preferred law filter only if confident
        # (topic_confidence >= _TOPIC_CONFIDENCE_THRESHOLD was already checked by analyzer)
        law_ids = list(u.preferred_law_ids) if u.preferred_law_ids else []
        return RussianRetrievalPlan(
            mode="topic",
            law_ids=law_ids,
            article_num=None,
            candidate_k=_candidate_k(top_k, baseline=40),
            use_hybrid=True,
        )

    @staticmethod
    def _broad_plan(u: RussianQueryUnderstanding, top_k: int) -> RussianRetrievalPlan:
        """Unconstrained hybrid search."""
        return RussianRetrievalPlan(
            mode="broad",
            law_ids=[],
            article_num=None,
            candidate_k=_candidate_k(top_k, baseline=30),
            use_hybrid=True,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candidate_k(top_k: int, baseline: int) -> int:
    """
    Return candidate count for retrieval.

    At least `baseline`, at least `top_k * 2` (for fusion headroom),
    capped at 100.
    """
    return min(100, max(baseline, top_k * 2))
