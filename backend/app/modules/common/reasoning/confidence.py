from app.modules.common.qdrant.schemas import HybridSearchResponse
from app.modules.common.querying.schemas import QueryContext, QueryType
from app.modules.common.reasoning.schemas import ConfidenceDecision, ConfidenceLevel


class ConfidenceGate:
    def evaluate(self, query_context: QueryContext, retrieval: HybridSearchResponse) -> ConfidenceDecision:
        if not retrieval.results:
            return ConfidenceDecision(
                level=ConfidenceLevel.LOW,
                use_llm=True,
                response_type="semantic_explanation",
                reason_codes=["no_results"],
                score_summary={"result_count": 0},
            )

        features = retrieval.features
        top_score = features.top_fused_score
        score_gap = features.score_gap
        keyword_coverage = features.keyword_coverage
        reason_codes: list[str] = []

        if features.citation_match:
            reason_codes.append("citation_match")
        if features.phrase_match:
            reason_codes.append("phrase_match")
        if keyword_coverage >= 0.6:
            reason_codes.append("keyword_coverage")
        if score_gap >= 0.03:
            reason_codes.append("score_gap")

        if query_context.query_type == QueryType.EXACT_STATUTE:
            if features.citation_match and keyword_coverage >= 0.45 and score_gap >= 0.02:
                return self._decision(
                    ConfidenceLevel.HIGH,
                    False,
                    "citation_answer",
                    reason_codes or ["exact_statute_match"],
                    features,
                )
            return self._decision(
                ConfidenceLevel.MEDIUM,
                True,
                "semantic_explanation",
                reason_codes or ["exact_statute_needs_explanation"],
                features,
            )

        if query_context.query_type == QueryType.CASE_LOOKUP:
            if (features.phrase_match or keyword_coverage >= 0.5) and score_gap >= 0.02:
                return self._decision(
                    ConfidenceLevel.HIGH,
                    False,
                    "citation_answer",
                    reason_codes or ["case_lookup_match"],
                    features,
                )
            return self._decision(ConfidenceLevel.MEDIUM, True, "semantic_explanation", reason_codes, features)

        if query_context.query_type == QueryType.SEMANTIC_LAW:
            if top_score >= 0.7 and keyword_coverage >= 0.65 and features.supporting_chunks >= 1:
                return self._decision(
                    ConfidenceLevel.HIGH,
                    False,
                    "semantic_explanation",
                    reason_codes or ["semantic_high_confidence"],
                    features,
                )
            if top_score >= 0.55:
                return self._decision(
                    ConfidenceLevel.MEDIUM,
                    True,
                    "semantic_explanation",
                    reason_codes or ["semantic_needs_llm"],
                    features,
                )
            return self._decision(
                ConfidenceLevel.LOW,
                True,
                "semantic_explanation",
                reason_codes or ["weak_retrieval"],
                features,
            )

        return self.strategy_decision()

    def strategy_decision(self) -> ConfidenceDecision:
        return ConfidenceDecision(
            level=ConfidenceLevel.MEDIUM,
            use_llm=True,
            response_type="strategy_answer",
            reason_codes=["strategy_requires_llm"],
            score_summary={"result_count": 0},
        )

    @staticmethod
    def _decision(
        level: ConfidenceLevel,
        use_llm: bool,
        response_type: str,
        reason_codes: list[str],
        features,
    ) -> ConfidenceDecision:
        return ConfidenceDecision(
            level=level,
            use_llm=use_llm,
            response_type=response_type,  # type: ignore[arg-type]
            reason_codes=reason_codes,
            score_summary={
                "top_fused_score": round(features.top_fused_score, 4),
                "score_gap": round(features.score_gap, 4),
                "keyword_coverage": round(features.keyword_coverage, 4),
                "supporting_chunks": features.supporting_chunks,
                "citation_match": features.citation_match,
                "phrase_match": features.phrase_match,
            },
        )
