from collections import OrderedDict

from app.modules.common.querying.schemas import QueryContext
from app.modules.common.qdrant.schemas import HybridSearchResponse, SearchResultItem
from app.modules.common.reasoning.schemas import ConfidenceDecision
from app.modules.common.responses.schemas import (
    CitationAnswer,
    ResponseProvenance,
    SearchAnswerResponse,
    SemanticExplanation,
    SourceReference,
    StrategyAnswerPayload,
)


class SearchResponseBuilder:
    def build_answer_response(
        self,
        query_context: QueryContext,
        retrieval: HybridSearchResponse,
        decision: ConfidenceDecision,
        response_payload: CitationAnswer | SemanticExplanation | StrategyAnswerPayload,
    ) -> SearchAnswerResponse:
        return SearchAnswerResponse(
            query_context=query_context,
            decision=decision,
            response=response_payload,
            results=retrieval.results,
        )

    def build_citation_answer(
        self,
        query_context: QueryContext,
        retrieval: HybridSearchResponse,
        decision: ConfidenceDecision,
        llm_used: bool = False,
        model_name: str | None = None,
    ) -> CitationAnswer:
        sources = self.build_sources(retrieval.results)
        top_result = retrieval.results[0]
        answer = self.compact_preview(top_result.text)
        citations = list(OrderedDict.fromkeys([top_result.filename, *(result.source or "" for result in retrieval.results)]))
        citations = [value for value in citations if value]
        return CitationAnswer(
            jurisdiction=query_context.jurisdiction.value,
            domain=(query_context.domain.value if query_context.domain else "mixed"),
            query=query_context.raw_query,
            answer=answer,
            citations=citations,
            document_ids=self._document_ids(retrieval.results),
            chunk_ids=self._chunk_ids(retrieval.results),
            confidence=self.confidence_value(decision),
            provenance=ResponseProvenance(
                llm_used=llm_used,
                reason_codes=decision.reason_codes,
                model_name=model_name,
            ),
            sources=sources,
        )

    def build_semantic_answer(
        self,
        query_context: QueryContext,
        retrieval: HybridSearchResponse,
        decision: ConfidenceDecision,
        summary: str,
        explanation: str,
        key_points: list[str],
        llm_used: bool = False,
        model_name: str | None = None,
    ) -> SemanticExplanation:
        return SemanticExplanation(
            jurisdiction=query_context.jurisdiction.value,
            domain=(query_context.domain.value if query_context.domain else "mixed"),
            query=query_context.raw_query,
            summary=summary,
            explanation=explanation,
            key_points=key_points,
            document_ids=self._document_ids(retrieval.results),
            chunk_ids=self._chunk_ids(retrieval.results),
            confidence=self.confidence_value(decision),
            provenance=ResponseProvenance(
                llm_used=llm_used,
                reason_codes=decision.reason_codes,
                model_name=model_name,
            ),
            sources=self.build_sources(retrieval.results),
        )

    def build_strategy_payload(
        self,
        query_context: QueryContext,
        summary: str,
        facts: list[str],
        relevant_laws: list[str],
        relevant_court_positions: list[str],
        arguments_for_client: list[str],
        arguments_against_client: list[str],
        risks: list[str],
        recommended_actions: list[str],
        missing_documents: list[str],
        chunk_ids: list[str],
        document_ids: list[str],
        sources: list[SourceReference],
        decision: ConfidenceDecision,
        llm_used: bool,
        model_name: str | None,
    ) -> StrategyAnswerPayload:
        return StrategyAnswerPayload(
            jurisdiction=query_context.jurisdiction.value,
            summary=summary,
            facts=facts,
            relevant_laws=relevant_laws,
            relevant_court_positions=relevant_court_positions,
            arguments_for_client=arguments_for_client,
            arguments_against_client=arguments_against_client,
            risks=risks,
            recommended_actions=recommended_actions,
            missing_documents=missing_documents,
            confidence=self.confidence_value(decision),
            chunk_ids=chunk_ids,
            document_ids=document_ids,
            provenance=ResponseProvenance(
                llm_used=llm_used,
                reason_codes=decision.reason_codes,
                model_name=model_name,
            ),
            sources=sources,
        )

    def build_sources(self, results: list[SearchResultItem]) -> list[SourceReference]:
        return [
            SourceReference(
                chunk_id=result.chunk_id,
                document_id=result.document_id,
                filename=result.filename,
                source=result.source,
                score=result.score,
            )
            for result in results
        ]

    def compact_preview(self, text: str, limit: int = 280) -> str:
        return self._compact_preview(text, limit=limit)

    def confidence_value(self, decision: ConfidenceDecision) -> float:
        return self._confidence_value(decision)

    @staticmethod
    def _document_ids(results: list[SearchResultItem]) -> list[str]:
        return list(OrderedDict.fromkeys(result.document_id for result in results))

    @staticmethod
    def _chunk_ids(results: list[SearchResultItem]) -> list[str]:
        return [result.chunk_id for result in results]

    @staticmethod
    def _compact_preview(text: str, limit: int = 280) -> str:
        preview = " ".join(text.split())
        if len(preview) <= limit:
            return preview
        return preview[: limit - 3].rstrip() + "..."

    @staticmethod
    def _confidence_value(decision: ConfidenceDecision) -> float:
        mapping = {
            "high": 0.88,
            "medium": 0.64,
            "low": 0.38,
        }
        return mapping[decision.level.value]
