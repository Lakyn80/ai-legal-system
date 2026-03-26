from app.modules.common.embeddings.provider import EmbeddingService
from app.modules.common.qdrant.client import QdrantVectorStore
from app.modules.common.qdrant.lexical_reranker import LexicalReranker
from app.modules.common.qdrant.schemas import (
    HybridSearchResponse,
    RankedSearchResult,
    RetrievalFeatureSet,
    SearchRequest,
    SearchResultItem,
)


class RetrievalService:
    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: QdrantVectorStore,
        reranker: LexicalReranker | None = None,
    ) -> None:
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.reranker = reranker or LexicalReranker()

    def search(self, request: SearchRequest) -> list[SearchResultItem]:
        return self.retrieve(request).results

    def retrieve(self, request: SearchRequest) -> HybridSearchResponse:
        query_vector = self.embedding_service.embed_query(request.query)
        candidate_count = min(max(request.top_k * 4, request.top_k), 25)
        dense_results = self.vector_store.search(
            query_vector=query_vector,
            top_k=candidate_count,
            country=request.country.value if request.country else None,
            domain=request.domain.value if request.domain else None,
            document_ids=request.document_ids,
            case_id=request.case_id,
        )
        if not dense_results:
            return HybridSearchResponse()

        ranked_results = self._rank_results(request.query, dense_results)
        selected_ranked = ranked_results[: request.top_k]
        selected_results = [
            ranked.item.model_copy(update={"score": ranked.fused_score})
            for ranked in selected_ranked
        ]
        return HybridSearchResponse(
            results=selected_results,
            ranked_results=selected_ranked,
            features=self._build_feature_set(request, dense_results, selected_ranked),
        )

    def _rank_results(self, query: str, dense_results: list[SearchResultItem]) -> list[RankedSearchResult]:
        dense_rank_map = {result.chunk_id: index + 1 for index, result in enumerate(dense_results)}
        lexical_scores = [
            (result, self.reranker.score_result(query, result))
            for result in dense_results
        ]
        lexical_sorted = sorted(
            lexical_scores,
            key=lambda item: (float(item[1]["lexical_score"]), float(item[1]["combined_score"])),
            reverse=True,
        )
        lexical_rank_map = {result.chunk_id: index + 1 for index, (result, _) in enumerate(lexical_sorted)}
        lexical_data_map = {result.chunk_id: data for result, data in lexical_scores}

        ranked_results: list[RankedSearchResult] = []
        for result in dense_results:
            dense_rank = dense_rank_map[result.chunk_id]
            lexical_rank = lexical_rank_map[result.chunk_id]
            lexical_data = lexical_data_map[result.chunk_id]
            fused_score = self._fused_score(
                dense_rank=dense_rank,
                lexical_rank=lexical_rank,
                dense_score=float(result.score),
                lexical_score=float(lexical_data["lexical_score"]),
                phrase_match=bool(lexical_data["phrase_match"]),
                citation_match=bool(lexical_data["citation_match"]),
            )
            ranked_results.append(
                RankedSearchResult(
                    item=result,
                    dense_rank=dense_rank,
                    dense_score=float(result.score),
                    lexical_rank=lexical_rank,
                    lexical_score=float(lexical_data["lexical_score"]),
                    fused_score=fused_score,
                    overlap_count=int(lexical_data["overlap_count"]),
                    overlap_ratio=float(lexical_data["overlap_ratio"]),
                    phrase_match=bool(lexical_data["phrase_match"]),
                    citation_match=bool(lexical_data["citation_match"]),
                    filename_match=bool(lexical_data["filename_match"]),
                    source_match=bool(lexical_data["source_match"]),
                )
            )

        ranked_results.sort(key=lambda item: item.fused_score, reverse=True)
        return ranked_results

    def _build_feature_set(
        self,
        request: SearchRequest,
        dense_results: list[SearchResultItem],
        ranked_results: list[RankedSearchResult],
    ) -> RetrievalFeatureSet:
        if not ranked_results:
            return RetrievalFeatureSet()

        top_result = ranked_results[0]
        next_score = ranked_results[1].fused_score if len(ranked_results) > 1 else 0.0
        supporting_chunks = sum(
            1
            for result in ranked_results
            if result.overlap_ratio >= 0.45 or result.phrase_match or result.citation_match
        )
        matched_domain = 0
        for result in ranked_results:
            if request.domain is None or result.item.domain == request.domain:
                matched_domain += 1
        return RetrievalFeatureSet(
            top_dense_score=float(dense_results[0].score),
            top_fused_score=top_result.fused_score,
            score_gap=max(top_result.fused_score - next_score, 0.0),
            keyword_coverage=top_result.overlap_ratio,
            phrase_match=top_result.phrase_match,
            citation_match=top_result.citation_match,
            domain_consistency=matched_domain / max(1, len(ranked_results)),
            supporting_chunks=supporting_chunks,
        )

    @staticmethod
    def _fused_score(
        dense_rank: int,
        lexical_rank: int,
        dense_score: float,
        lexical_score: float,
        phrase_match: bool,
        citation_match: bool,
    ) -> float:
        dense_rrf = 1.0 / (60 + dense_rank)
        lexical_rrf = 1.0 / (60 + lexical_rank)
        bonus = (0.08 if phrase_match else 0.0) + (0.1 if citation_match else 0.0)
        return (dense_score * 0.45) + (lexical_score * 0.3) + (dense_rrf * 12.0) + (lexical_rrf * 9.0) + bonus
