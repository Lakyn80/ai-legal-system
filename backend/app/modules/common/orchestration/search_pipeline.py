import logging

from app.modules.common.cache.exact_cache import ExactCacheService
from app.modules.common.cache.semantic_cache import SemanticCacheService
from app.core.enums import CountryEnum, DomainEnum
from app.modules.common.graph.schemas import StrategyRequest
from app.modules.common.graph.strategy_engine import StrategyEngine
from app.modules.common.llm.provider import BaseLLMProvider
from app.modules.common.observability.cache_metrics import CacheMetricsService
from app.modules.common.observability.logging import log_event
from app.modules.common.prompts.search_answers import (
    SEARCH_EXPLANATION_SYSTEM_PROMPT,
    build_search_explanation_prompt,
)
from app.modules.common.qdrant.retrieval_service import RetrievalService
from app.modules.common.qdrant.schemas import HybridSearchResponse, SearchRequest
from app.modules.common.querying.schemas import QueryType
from app.modules.common.querying.service import QueryProcessingService
from app.modules.common.reasoning.confidence import ConfidenceGate
from app.modules.common.responses.builders import SearchResponseBuilder
from app.modules.common.responses.schemas import SearchAnswerResponse, SemanticExplanation


logger = logging.getLogger(__name__)


class SearchAnswerService:
    def __init__(
        self,
        query_processing_service: QueryProcessingService,
        retrieval_service: RetrievalService,
        confidence_gate: ConfidenceGate,
        response_builder: SearchResponseBuilder,
        llm_provider: BaseLLMProvider,
        strategy_engine: StrategyEngine,
        llm_model_name: str,
        exact_cache_service: ExactCacheService | None = None,
        semantic_cache_service: SemanticCacheService | None = None,
        metrics_service: CacheMetricsService | None = None,
    ) -> None:
        self.query_processing_service = query_processing_service
        self.retrieval_service = retrieval_service
        self.confidence_gate = confidence_gate
        self.response_builder = response_builder
        self.llm_provider = llm_provider
        self.strategy_engine = strategy_engine
        self.llm_model_name = llm_model_name
        self.exact_cache_service = exact_cache_service
        self.semantic_cache_service = semantic_cache_service
        self.metrics_service = metrics_service

    def answer(self, request: SearchRequest) -> SearchAnswerResponse:
        if self.metrics_service is not None:
            self.metrics_service.increment_requests()
        query_context = self.query_processing_service.process(
            query=request.query,
            requested_country=request.country,
            requested_domain=request.domain,
        )
        self._log(
            "search.pipeline.request_received",
            query_context=query_context,
            requested_country=request.country.value if request.country is not None else None,
            requested_domain=request.domain.value if request.domain is not None else None,
            top_k=request.top_k,
        )
        cached_response = self._get_cached_response(query_context)
        if cached_response is not None:
            self._log("search.pipeline.short_circuit_exact_cache", query_context=query_context)
            return cached_response
        semantic_cached_response = self._get_semantic_cached_response(query_context)
        if semantic_cached_response is not None:
            self._log("search.pipeline.short_circuit_semantic_cache", query_context=query_context)
            return semantic_cached_response

        if query_context.query_type == QueryType.STRATEGY:
            if self.metrics_service is not None:
                self.metrics_service.increment_strategy()
            self._log("search.pipeline.route_strategy", query_context=query_context)
            response = self._build_strategy_response(request, query_context.jurisdiction)
            self._cache_response(query_context, response)
            return response

        retrieval_request = request.model_copy(
            update={
                "country": request.country or query_context.jurisdiction,
                "domain": self._resolved_domain(request.domain, query_context.domain),
            }
        )
        if self.metrics_service is not None:
            self.metrics_service.increment_retrieval()
        retrieval = self.retrieval_service.retrieve(retrieval_request)
        decision = self.confidence_gate.evaluate(query_context, retrieval)
        self._log(
            "search.pipeline.retrieval_completed",
            query_context=query_context,
            result_count=len(retrieval.results),
            decision_response_type=decision.response_type,
            decision_use_llm=decision.use_llm,
            confidence_level=decision.level.value,
            reason_codes=decision.reason_codes,
            score_summary=decision.score_summary,
        )

        if decision.use_llm:
            if self.metrics_service is not None:
                self.metrics_service.increment_llm()
            self._log("search.pipeline.route_llm", query_context=query_context)
            response_payload = self._build_llm_semantic_response(query_context, retrieval, decision)
        elif decision.response_type == "citation_answer":
            self._log("search.pipeline.route_citation_answer", query_context=query_context)
            response_payload = self.response_builder.build_citation_answer(query_context, retrieval, decision)
        else:
            self._log("search.pipeline.route_deterministic_semantic", query_context=query_context)
            response_payload = self._build_deterministic_semantic_response(query_context, retrieval, decision)

        response = self.response_builder.build_answer_response(
            query_context=query_context,
            retrieval=retrieval,
            decision=decision,
            response_payload=response_payload,
        )
        self._cache_response(query_context, response)
        return response

    def _build_strategy_response(self, request: SearchRequest, country: CountryEnum) -> SearchAnswerResponse:
        strategy = self.strategy_engine.generate(
            StrategyRequest(
                query=request.query,
                country=country,
                domain=request.domain,
                document_ids=request.document_ids,
                case_id=request.case_id,
                top_k=max(4, request.top_k),
            )
        )
        query_context = self.query_processing_service.process(
            query=request.query,
            requested_country=country,
            requested_domain=request.domain,
        )
        retrieval = HybridSearchResponse(results=strategy.retrieved_chunks)
        decision = self.confidence_gate.strategy_decision()
        response_payload = self.response_builder.build_strategy_payload(
            query_context=query_context,
            summary=strategy.strategy.summary,
            facts=strategy.strategy.facts,
            relevant_laws=strategy.strategy.relevant_laws,
            relevant_court_positions=strategy.strategy.relevant_court_positions,
            arguments_for_client=strategy.strategy.arguments_for_client,
            arguments_against_client=strategy.strategy.arguments_against_client,
            risks=strategy.strategy.risks,
            recommended_actions=strategy.strategy.recommended_actions,
            missing_documents=strategy.strategy.missing_documents,
            chunk_ids=[chunk.chunk_id for chunk in strategy.retrieved_chunks],
            document_ids=list(dict.fromkeys(chunk.document_id for chunk in strategy.retrieved_chunks)),
            sources=self.response_builder.build_sources(strategy.retrieved_chunks),
            decision=decision,
            llm_used=True,
            model_name=self.llm_model_name,
        )
        return self.response_builder.build_answer_response(
            query_context=query_context,
            retrieval=retrieval,
            decision=decision,
            response_payload=response_payload,
        )

    def _build_deterministic_semantic_response(self, query_context, retrieval, decision):
        top_results = retrieval.results[:3]
        summary = top_results[0].text.split(".")[0].strip() if top_results else "No relevant evidence found."
        key_points = [self.response_builder.compact_preview(result.text, limit=180) for result in top_results]
        explanation = " ".join(key_points) if key_points else "No relevant evidence found."
        return self.response_builder.build_semantic_answer(
            query_context=query_context,
            retrieval=retrieval,
            decision=decision,
            summary=summary or "Relevant legal context located.",
            explanation=explanation,
            key_points=key_points,
        )

    def _build_llm_semantic_response(self, query_context, retrieval, decision):
        user_prompt = build_search_explanation_prompt(query_context, retrieval)
        llm_output = self.llm_provider.invoke_structured(
            SEARCH_EXPLANATION_SYSTEM_PROMPT,
            user_prompt,
            schema=SemanticExplanation,
        )
        return self.response_builder.build_semantic_answer(
            query_context=query_context,
            retrieval=retrieval,
            decision=decision,
            summary=llm_output.summary or "Evidence-grounded legal summary.",
            explanation=llm_output.explanation or llm_output.summary,
            key_points=llm_output.key_points,
            llm_used=True,
            model_name=self.llm_model_name,
        )

    @staticmethod
    def _resolved_domain(requested_domain: DomainEnum | None, detected_domain: DomainEnum | None) -> DomainEnum | None:
        if requested_domain:
            return requested_domain
        return detected_domain

    def _get_cached_response(self, query_context) -> SearchAnswerResponse | None:
        if self.exact_cache_service is None:
            return None
        return self.exact_cache_service.get(query_context)

    def _get_semantic_cached_response(self, query_context) -> SearchAnswerResponse | None:
        if self.semantic_cache_service is None:
            return None
        return self.semantic_cache_service.get(query_context)

    def _cache_response(self, query_context, response: SearchAnswerResponse) -> None:
        if self.exact_cache_service is None:
            if self.semantic_cache_service is None:
                return
        if self.exact_cache_service is not None:
            self.exact_cache_service.set(query_context, response)
        if self.semantic_cache_service is not None:
            self.semantic_cache_service.set(query_context, response)

    def _log(self, event: str, query_context, **fields) -> None:
        log_event(
            logger,
            event,
            jurisdiction=query_context.jurisdiction.value,
            domain=query_context.domain.value if query_context.domain is not None else None,
            query_type=query_context.query_type.value,
            query_hash=query_context.query_hash,
            normalized_query=query_context.normalized_query,
            **fields,
        )
