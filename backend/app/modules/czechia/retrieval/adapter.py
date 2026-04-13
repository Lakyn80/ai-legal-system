from __future__ import annotations

from app.modules.common.qdrant.lexical_reranker import LexicalReranker
from app.modules.common.qdrant.schemas import HybridSearchResponse, RetrievalFeatureSet
from app.modules.czechia.retrieval.service import CzechLawRetrievalService


class CzechLawRetrievalAdapter:
    """
    Wraps CzechLawRetrievalService so it can be used as a drop-in replacement
    for the retrieval_service slot in SearchAnswerService.

    SearchAnswerService calls:
      - retrieve(request) -> HybridSearchResponse   (answer pipeline)
      - search(request)   -> list[SearchResultItem] (used internally by some paths)
    """

    def __init__(
        self,
        service: CzechLawRetrievalService,
        reranker: LexicalReranker | None = None,
    ) -> None:
        self.service = service
        self._reranker = reranker or LexicalReranker()

    def search(self, request):
        return self.service.search(request)

    def retrieve(self, request) -> HybridSearchResponse:
        results = self.service.search(request)
        return HybridSearchResponse(
            results=results,
            features=self._build_feature_set(request, results),
        )

    def _build_feature_set(self, request, results) -> RetrievalFeatureSet:
        if not results:
            return RetrievalFeatureSet()
        if results[0].chunk_id.startswith("labor_gate:"):
            return RetrievalFeatureSet()

        lexical_scores = [self._reranker.score_result(request.query, result) for result in results]
        top_score = float(results[0].score)
        next_score = float(results[1].score) if len(results) > 1 else 0.0
        top_lexical = lexical_scores[0] if lexical_scores else {}
        supporting_chunks = sum(
            1
            for score_data in lexical_scores
            if float(score_data.get("overlap_ratio", 0.0)) >= 0.45
            or bool(score_data.get("phrase_match"))
            or bool(score_data.get("citation_match"))
        )
        matched_domain = sum(
            1
            for result in results
            if request.domain is None or result.domain == request.domain
        )
        return RetrievalFeatureSet(
            top_dense_score=top_score,
            top_fused_score=top_score,
            score_gap=max(top_score - next_score, 0.0),
            keyword_coverage=float(top_lexical.get("overlap_ratio", 0.0)),
            phrase_match=bool(top_lexical.get("phrase_match")),
            citation_match=bool(top_lexical.get("citation_match")),
            domain_consistency=matched_domain / max(1, len(results)),
            supporting_chunks=supporting_chunks,
        )
