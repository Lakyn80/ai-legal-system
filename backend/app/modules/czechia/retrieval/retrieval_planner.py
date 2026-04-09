from __future__ import annotations

from dataclasses import replace

from app.modules.czechia.retrieval.schemas import (
    DetectedLawRef,
    RetrievalBoostFactors,
    RetrievalPlan,
    QueryUnderstanding,
)
from app.modules.czechia.retrieval.text_utils import unique_preserve

_DOMAIN_PREFERRED_LAWS: dict[str, list[str]] = {
    "employment": ["local:sb/2006/262"],
    "civil": ["local:sb/2012/89", "local:sb/1963/99", "local:sb/2013/292"],
    "criminal": ["local:sb/2009/40", "local:sb/1961/141"],
    "tax": ["local:sb/1992/586"],
    "administrative": ["local:sb/2004/500"],
    "constitutional": ["local:sb/1993/1"],
    "corporate": ["local:sb/2012/90"],
    "unknown": [],
}


class CzechLawRetrievalPlanner:
    def build(
        self,
        understanding: QueryUnderstanding,
        top_k: int,
        document_ids: list[str] | None = None,
        forced_paragraph: int | None = None,
        forced_law: str | None = None,
    ) -> RetrievalPlan:
        explicit_laws = [ref.law_iri for ref in understanding.detected_law_refs]
        if document_ids:
            explicit_laws.extend(document_ids)
        law_filter = unique_preserve(explicit_laws)
        preferred_law_iris = law_filter or _DOMAIN_PREFERRED_LAWS.get(
            understanding.detected_domain,
            [],
        )

        if understanding.query_mode == "exact_lookup":
            plan = RetrievalPlan(
                law_filter=law_filter,
                paragraph_filter=list(understanding.detected_paragraphs),
                preferred_law_iris=preferred_law_iris,
                candidate_k=_candidate_k(top_k, 80),
                boost_factors=RetrievalBoostFactors(
                    law_match_boost=0.34,
                    paragraph_match_boost=0.42,
                    preferred_law_boost=0.18,
                    exact_match_boost=0.48,
                    structural_neighbor_boost=0.06,
                    text_overlap_weight=0.24,
                    law_mismatch_penalty=0.50,
                ),
                mode="exact",
            )
            return self._apply_forced_signals(plan, forced_paragraph=forced_paragraph, forced_law=forced_law)

        if understanding.query_mode == "law_constrained_search":
            plan = RetrievalPlan(
                law_filter=law_filter,
                paragraph_filter=list(understanding.detected_paragraphs),
                preferred_law_iris=preferred_law_iris,
                candidate_k=_candidate_k(top_k, 75),
                boost_factors=RetrievalBoostFactors(
                    law_match_boost=0.32,
                    paragraph_match_boost=0.30,
                    preferred_law_boost=0.12,
                    exact_match_boost=0.35,
                    structural_neighbor_boost=0.05,
                    text_overlap_weight=0.26,
                    law_mismatch_penalty=0.45,
                ),
                mode="constrained",
            )
            return self._apply_forced_signals(plan, forced_paragraph=forced_paragraph, forced_law=forced_law)

        if understanding.query_mode == "domain_search":
            plan = RetrievalPlan(
                law_filter=[],
                paragraph_filter=list(understanding.detected_paragraphs),
                preferred_law_iris=list(preferred_law_iris),
                candidate_k=_candidate_k(top_k, 90),
                boost_factors=RetrievalBoostFactors(
                    law_match_boost=0.0,
                    paragraph_match_boost=0.24,
                    preferred_law_boost=0.24,
                    exact_match_boost=0.30,
                    structural_neighbor_boost=0.05,
                    text_overlap_weight=0.30,
                    law_mismatch_penalty=0.12,
                ),
                mode="constrained",
            )
            return self._apply_forced_signals(plan, forced_paragraph=forced_paragraph, forced_law=forced_law)

        plan = RetrievalPlan(
            law_filter=[],
            paragraph_filter=list(understanding.detected_paragraphs),
            preferred_law_iris=list(preferred_law_iris),
            candidate_k=_candidate_k(top_k, 100),
            boost_factors=RetrievalBoostFactors(
                law_match_boost=0.0,
                paragraph_match_boost=0.18,
                preferred_law_boost=0.12,
                exact_match_boost=0.24,
                structural_neighbor_boost=0.04,
                text_overlap_weight=0.32,
                law_mismatch_penalty=0.05,
            ),
            mode="broad",
        )
        return self._apply_forced_signals(plan, forced_paragraph=forced_paragraph, forced_law=forced_law)

    def broaden(self, plan: RetrievalPlan, understanding: QueryUnderstanding, top_k: int) -> RetrievalPlan:
        if plan.mode == "exact":
            return replace(
                plan,
                paragraph_filter=[],
                candidate_k=_candidate_k(top_k, 90),
                mode="constrained",
            )

        if plan.mode == "constrained" and plan.law_filter:
            return replace(
                plan,
                paragraph_filter=[],
                candidate_k=_candidate_k(top_k, 100),
            )

        return RetrievalPlan(
            law_filter=[],
            paragraph_filter=[],
            preferred_law_iris=_DOMAIN_PREFERRED_LAWS.get(understanding.detected_domain, []),
            candidate_k=_candidate_k(top_k, 100),
            boost_factors=RetrievalBoostFactors(),
            mode="broad",
        )

    def _apply_forced_signals(
        self,
        plan: RetrievalPlan,
        forced_paragraph: int | None,
        forced_law: str | None,
    ) -> RetrievalPlan:
        if forced_law:
            plan.law_filter = _ensure_unique(plan.law_filter, forced_law)
            if not plan.preferred_law_iris:
                plan.preferred_law_iris = list(plan.law_filter)

        if forced_paragraph is not None:
            plan.mode = "exact"
            plan.paragraph_filter = [str(forced_paragraph)]

        return plan


def _candidate_k(top_k: int, baseline: int) -> int:
    return min(100, max(50, baseline, top_k * 10))


def _ensure_unique(values: list[str], value: str) -> list[str]:
    result = list(values)
    if value not in result:
        result.append(value)
    return result
