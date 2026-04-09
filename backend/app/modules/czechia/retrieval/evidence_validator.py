from __future__ import annotations

from app.modules.czechia.retrieval.schemas import EvidencePack, QueryUnderstanding, RetrievalPlan, ValidationResult


class CzechLawEvidenceValidator:
    def validate(
        self,
        evidence_pack: EvidencePack,
        understanding: QueryUnderstanding,
        plan: RetrievalPlan,
        top_k: int,
    ) -> ValidationResult:
        items = _deduplicate(evidence_pack.items)
        if not items:
            return ValidationResult(
                evidence_pack=EvidencePack(items=[], understanding=understanding, plan=plan),
                should_broaden=plan.allow_fallback_broadening and plan.mode != "broad",
                reason="no_candidates",
            )

        top_score = items[0].score
        min_required = max(2, min(top_k, 4))
        validated = []
        for item in items:
            flags = item.validation_flags
            if plan.mode == "constrained" and plan.law_filter and item.law_iri not in plan.law_filter:
                continue

            if (
                plan.mode == "exact"
                and plan.paragraph_filter
                and not flags.get("paragraph_match")
                and not flags.get("neighbor_of_exact_match")
                and not flags.get("exact_match")
            ):
                continue

            score_floor = max(0.12, top_score * 0.30)
            if item.score < score_floor:
                if not (
                    flags.get("exact_match")
                    or flags.get("paragraph_match")
                    or flags.get("strict_law_match")
                    or flags.get("preferred_law_match")
                ):
                    continue

            if (
                item.score < max(0.08, top_score * 0.18)
                and not flags.get("exact_match")
                and float(flags.get("text_overlap", 0.0)) < 0.05
            ):
                continue

            validated.append(item)

        if not validated:
            return ValidationResult(
                evidence_pack=EvidencePack(items=[], understanding=understanding, plan=plan),
                should_broaden=plan.allow_fallback_broadening and plan.mode != "broad",
                reason="all_candidates_rejected",
            )

        if len(validated) < min_required and plan.allow_fallback_broadening and plan.mode != "broad":
            return ValidationResult(
                evidence_pack=EvidencePack(items=validated, understanding=understanding, plan=plan),
                should_broaden=True,
                reason="insufficient_validated_results",
            )

        return ValidationResult(
            evidence_pack=EvidencePack(items=validated, understanding=understanding, plan=plan),
            should_broaden=False,
            reason="validated",
        )


def _deduplicate(items):
    unique = {}
    for item in items:
        if item.chunk_id not in unique:
            unique[item.chunk_id] = item
            continue
        if item.score > unique[item.chunk_id].score:
            unique[item.chunk_id] = item
    deduped = list(unique.values())
    deduped.sort(
        key=lambda item: (
            -item.score,
            -bool(item.validation_flags.get("exact_match")),
            -bool(item.validation_flags.get("paragraph_match")),
            item.chunk_index,
            item.chunk_id,
        )
    )
    return deduped
