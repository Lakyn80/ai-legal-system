"""
Issue-focused multi-source retrieval for the foreign-party / interpreter /
language-of-proceedings problem in Russian civil proceedings.

Primary legal basis:  ГПК РФ (ст. 9 — язык судопроизводства, ст. 162 — переводчик)
Supporting sources:   ЕКПЧ (ст. 5, ст. 6) and ФЗ-115 (legal status of foreign nationals)

This module is narrow by design — it targets one specific legal issue cluster.

Does NOT:
  - Synthesize answers
  - Call any LLM
  - Implement agent logic
  - Handle other legal issue clusters
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.modules.russia.retrieval.schemas import RussianSearchResult

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PRIMARY_LAW = "local:ru/gpk"
_SUPPORT_LAWS = frozenset({"local:ru/echr", "local:ru/fl115"})

# Pool size for the unconstrained support pass.
# Must be large enough to surface ECHR / FL115 results despite GPK dominance.
_SUPPORT_POOL_SIZE = 30


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------

@dataclass
class IssueEvidence:
    """
    A single piece of retrieved evidence for the interpreter/language issue.

    source_role distinguishes where this evidence belongs in the legal argument:
      'primary'   — ГПК РФ (procedural guarantee directly applicable)
      'supporting' — ЕКПЧ or ФЗ-115 (international / statutory support)
    """

    score: float
    chunk_id: str
    law_id: str
    law_short: str
    article_num: str | None
    article_heading: str | None
    text: str
    is_tombstone: bool
    source_role: str  # "primary" | "supporting"


@dataclass
class InterpreterIssueResult:
    """
    Multi-source retrieval result for the interpreter/language-of-proceedings issue.

    Attributes
    ----------
    query      : original input query
    primary    : results from ГПК РФ (primary legal basis)
    supporting : results from ЕКПЧ and/or ФЗ-115 (supporting sources)
    combined   : primary + supporting sorted by score descending
    """

    query: str
    primary: list[IssueEvidence] = field(default_factory=list)
    supporting: list[IssueEvidence] = field(default_factory=list)
    combined: list[IssueEvidence] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Retrieval class
# ---------------------------------------------------------------------------

class InterpreterIssueRetrieval:
    """
    Issue-focused retrieval for the foreign-party / interpreter /
    language-of-proceedings problem.

    Combines a GPK-constrained primary pass with an unconstrained support pass
    that filters results to ЕКПЧ and ФЗ-115.

    Thread-safe: no mutable state after construction.

    Usage:
        from app.modules.russia.retrieval.interpreter_issue import (
            InterpreterIssueRetrieval,
        )
        retrieval = InterpreterIssueRetrieval(service)
        result = retrieval.retrieve("суд не предоставил переводчика")
        # result.primary    — GPK articles
        # result.supporting — ECHR / FL-115 articles (may be empty for narrow queries)
        # result.combined   — all evidence, ranked by score
    """

    def __init__(self, service: object) -> None:
        """
        Args:
            service: RussianRetrievalService instance (typed as object to avoid
                     circular import; the required methods are duck-typed).
        """
        self._service = service

    def retrieve(
        self,
        query: str,
        top_k_primary: int = 5,
        top_k_support: int = 3,
    ) -> InterpreterIssueResult:
        """
        Execute multi-source retrieval for the interpreter/language issue.

        Retrieval steps
        ---------------
        1. Analyze the query (detect exact-lookup mode, aliases, cleaned text).
        2. Primary pass:
           - If query is exact-lookup for GPK (e.g. 'ст. 162 гпк рф'):
               use topic_search() to get exact-match chunks (score=1.0).
           - Otherwise:
               use hybrid_search() constrained to GPK.
        3. Support pass:
           - Use hybrid_search() on the cleaned query, unconstrained.
           - Filter results to ЕКПЧ (local:ru/echr) and ФЗ-115 (local:ru/fl115).
           - Return up to top_k_support results.
           - Returns empty list if neither ECHR nor FL115 ranked in the top pool.
        4. Combine and sort by score descending.

        Args:
            query:          Free-text legal query in Russian
            top_k_primary:  Maximum GPK results to return
            top_k_support:  Maximum ECHR/FL115 results to return

        Returns:
            InterpreterIssueResult with primary, supporting, and combined fields.
        """
        understanding = self._service.analyze_query(query)

        log.debug(
            "interpreter_issue.retrieve query=%r mode=%r law_ids=%r",
            query[:60], understanding.query_mode, understanding.detected_law_ids,
        )

        # ── Primary: GPK ────────────────────────────────────────────────────
        if (
            understanding.query_mode == "exact_lookup"
            and _PRIMARY_LAW in understanding.detected_law_ids
        ):
            # Exact article lookup — deterministic, score=1.0
            primary_raw = self._service.topic_search(query, top_k=top_k_primary)
        else:
            # Always constrain primary to GPK for this issue class
            primary_raw = self._service.hybrid_search(
                query=query,
                law_id=_PRIMARY_LAW,
                top_k=top_k_primary,
            )

        # ── Support: ЕКПЧ + ФЗ-115 ─────────────────────────────────────────
        # Use cleaned query (aliases stripped) to maximize semantic recall
        support_query = understanding.cleaned_query if understanding.cleaned_query else query
        support_pool = self._service.hybrid_search(
            query=support_query,
            law_id=None,
            top_k=_SUPPORT_POOL_SIZE,
        )
        support_raw = [
            r for r in support_pool if r.law_id in _SUPPORT_LAWS
        ][:top_k_support]

        log.debug(
            "interpreter_issue.retrieve primary=%d support=%d (pool=%d)",
            len(primary_raw), len(support_raw), len(support_pool),
        )

        # ── Build output ────────────────────────────────────────────────────
        primary = [_to_evidence(r, "primary") for r in primary_raw]
        supporting = [_to_evidence(r, "supporting") for r in support_raw]
        combined = sorted(primary + supporting, key=lambda e: -e.score)

        return InterpreterIssueResult(
            query=query,
            primary=primary,
            supporting=supporting,
            combined=combined,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_evidence(result: RussianSearchResult, role: str) -> IssueEvidence:
    """Convert a RussianSearchResult to IssueEvidence with the given source_role."""
    return IssueEvidence(
        score=result.score,
        chunk_id=result.chunk_id,
        law_id=result.law_id,
        law_short=result.law_short,
        article_num=result.article_num,
        article_heading=result.article_heading,
        text=result.text,
        is_tombstone=result.is_tombstone,
        source_role=role,
    )
