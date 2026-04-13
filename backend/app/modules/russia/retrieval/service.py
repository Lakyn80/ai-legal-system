"""
Russian law retrieval service — Milestone 1 / Steps 5–8.

Step 5: exact article lookup (no vector search)
Step 6: dense semantic search added
Step 7: sparse BM25 search + hybrid RRF fusion added
Step 8: query-aware topic retrieval added (query_analyzer + retrieval_planner)

Does NOT:
  - Call any LLM
  - Import ingestion modules
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.modules.common.embeddings.provider import EmbeddingService
from app.modules.common.legal_taxonomy.service import (
    FocusLegalTaxonomyService,
    get_russia_focus_taxonomy_service,
)
from app.modules.russia.retrieval.dense_retriever import RussianDenseRetriever
from app.modules.russia.retrieval.exact_lookup import RussianExactLookup
from app.modules.russia.retrieval.fusion import reciprocal_rank_fusion
from app.modules.russia.retrieval.query_analyzer import RussianQueryAnalyzer, RussianQueryUnderstanding
from app.modules.russia.retrieval.retrieval_planner import RussianRetrievalPlan, RussianRetrievalPlanner
from app.modules.russia.retrieval.schemas import ArticleLookupResult, RussianChunkResult, RussianSearchResult
from app.modules.russia.retrieval.sparse_retriever import RussianSparseRetriever
from app.modules.russia.retrieval.taxonomy_first import taxonomy_first_search

log = logging.getLogger(__name__)


class RussianRetrievalService:
    """
    Retrieval service for Russian law — Milestone 1.

    Supports:
      - Exact article lookup (no embedding, pure payload filter)
      - Dense semantic search (embedding + vector search)
      - Sparse BM25 search (requires IDF checkpoint)
      - Hybrid search (dense + sparse fused via RRF)

    Usage:
        service = RussianRetrievalService(
            embedding_service=...,
            qdrant_url="http://qdrant:6333",
        )
        result   = service.get_article("local:ru/tk", "81")
        dense    = service.search("расторжение договора", law_id="local:ru/tk")
        sparse   = service.sparse_search("расторжение договора", law_id="local:ru/tk")
        hybrid   = service.hybrid_search("расторжение договора", law_id="local:ru/tk")
    """

    def __init__(
        self,
        embedding_service: EmbeddingService,
        qdrant_url: str,
        qdrant_api_key: str | None = None,
        idf_checkpoint_path: Path | None = None,
        taxonomy_service: FocusLegalTaxonomyService | None = None,
    ) -> None:
        self._exact = RussianExactLookup(url=qdrant_url, api_key=qdrant_api_key)
        self._dense = RussianDenseRetriever(
            embedding_service=embedding_service,
            url=qdrant_url,
            api_key=qdrant_api_key,
        )
        self._sparse = RussianSparseRetriever(
            url=qdrant_url,
            api_key=qdrant_api_key,
            idf_checkpoint_path=idf_checkpoint_path,
        )
        self._analyzer = RussianQueryAnalyzer()
        self._planner = RussianRetrievalPlanner()
        self._taxonomy = taxonomy_service or get_russia_focus_taxonomy_service()

    def get_article(
        self,
        law_id: str,
        article_num: str,
        part_num: int | None = None,
    ) -> ArticleLookupResult:
        """
        Look up a Russian law article by law_id + article_num.

        Args:
            law_id:      Canonical IRI, e.g. 'local:ru/tk'
            article_num: Article number as string, e.g. '81', '19.1'
            part_num:    Optional — return only the specified part

        Returns:
            ArticleLookupResult. Always structured — never raises.
        """
        return self._exact.get_article(law_id=law_id, article_num=article_num, part_num=part_num)

    def search(
        self,
        query: str,
        law_id: str | None = None,
        top_k: int = 10,
    ) -> list[RussianSearchResult]:
        """
        Dense semantic search over russian_laws_v1.

        Args:
            query:   Free-text query
            law_id:  Optional — restrict to one law (e.g. 'local:ru/tk')
            top_k:   Maximum results to return

        Returns:
            List of RussianSearchResult in score-descending order.
        """
        return taxonomy_first_search(
            svc=self,
            taxonomy=self._taxonomy,
            mode="dense",
            query=query,
            top_k=top_k,
            law_id=law_id,
        ).results

    def sparse_search(
        self,
        query: str,
        law_id: str | None = None,
        top_k: int = 10,
    ) -> list[RussianSearchResult]:
        """
        BM25 sparse search over russian_laws_v1.

        Returns empty list if IDF checkpoint is not available.

        Args:
            query:   Free-text query in Russian
            law_id:  Optional — restrict to one law
            top_k:   Maximum results to return

        Returns:
            List of RussianSearchResult in BM25-score-descending order.
        """
        return taxonomy_first_search(
            svc=self,
            taxonomy=self._taxonomy,
            mode="sparse",
            query=query,
            top_k=top_k,
            law_id=law_id,
        ).results

    def hybrid_search(
        self,
        query: str,
        law_id: str | None = None,
        top_k: int = 10,
        dense_candidates: int | None = None,
        sparse_candidates: int | None = None,
    ) -> list[RussianSearchResult]:
        """
        Hybrid search: dense + sparse BM25 fused via Reciprocal Rank Fusion.

        Each retriever is called with a larger candidate pool (2×top_k by default)
        so that the fusion has enough candidates to find the best top_k.

        Falls back to dense-only if sparse retrieval is unavailable
        (IDF checkpoint missing or query encodes to empty).

        Args:
            query:             Free-text query in Russian
            law_id:            Optional — restrict to one law
            top_k:             Maximum results to return after fusion
            dense_candidates:  Override candidate count for dense retriever
            sparse_candidates: Override candidate count for sparse retriever

        Returns:
            List of RussianSearchResult in RRF-score-descending order.
            The .score field contains the RRF score (not cosine similarity).
        """
        return taxonomy_first_search(
            svc=self,
            taxonomy=self._taxonomy,
            mode="hybrid",
            query=query,
            top_k=top_k,
            law_id=law_id,
        ).results

    # ── Step 8: query-aware topic retrieval ───────────────────────────────────

    def analyze_query(self, query: str) -> RussianQueryUnderstanding:
        """
        Analyze a Russian legal query and return structured understanding.

        Useful for debugging, testing, and building the topic_search pipeline.
        """
        return self._analyzer.analyze(query)

    def topic_search(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[RussianSearchResult]:
        """
        Query-aware retrieval: analyzes the query, builds a retrieval plan,
        and executes the appropriate retrieval strategy.

        Strategies (determined by query analysis):
          exact_lookup            → get_article() → convert chunks to results
          law_constrained_search  → hybrid_search with hard law_id filter
          topic_search            → hybrid_search with inferred law_id filter
          broad_search            → unconstrained hybrid_search

        Falls back to dense-only if sparse is unavailable.

        Args:
            query:  Free-text query in Russian (any topic, article ref, law alias)
            top_k:  Maximum number of results to return

        Returns:
            List of RussianSearchResult in relevance-score-descending order.
            For exact_lookup mode, .score is 1.0 (exact match).
            For search modes, .score is RRF score.
        """
        understanding = self._analyzer.analyze(query)
        plan = self._planner.plan(understanding, top_k=top_k)

        log.debug(
            "topic_search query=%r mode=%r law_ids=%r article=%r topic=%r",
            query[:60], plan.mode, plan.law_ids, plan.article_num,
            understanding.detected_topic,
        )

        # ── Exact article lookup ─────────────────────────────────────────
        if plan.mode == "exact" and plan.article_num:
            law_id = plan.law_ids[0] if plan.law_ids else None
            if law_id:
                result = self._exact.get_article(
                    law_id=law_id,
                    article_num=plan.article_num,
                )
                if result.hit:
                    return [_chunk_to_search_result(c) for c in result.chunks[:top_k]]
            # Fall through to hybrid if no law_id or not found

        # ── Taxonomy-first for internal topic search consistency ──────────
        mode = "hybrid" if plan.use_hybrid else "dense"
        law_id_filter = plan.law_ids[0] if (plan.mode == "constrained" and plan.law_ids) else None
        outcome = taxonomy_first_search(
            svc=self,
            taxonomy=self._taxonomy,
            mode=mode,
            query=understanding.cleaned_query,
            top_k=top_k,
            law_id=law_id_filter,
        )
        return outcome.results

    # ── Base (non-taxonomy) mode executor for shared wrapper ───────────────

    def _taxonomy_base_search(
        self,
        *,
        mode: str,
        query: str,
        law_id: str | None,
        top_k: int,
    ) -> list[RussianSearchResult]:
        if mode == "dense":
            return self._dense.search(query=query, law_id=law_id, top_k=top_k)
        if mode == "sparse":
            return self._sparse.search(query=query, law_id=law_id, top_k=top_k)

        # hybrid
        candidates = max(top_k * 2, 20)
        dense_k = candidates
        sparse_k = candidates

        dense_results = self._dense.search(query=query, law_id=law_id, top_k=dense_k)
        sparse_results = self._sparse.search(query=query, law_id=law_id, top_k=sparse_k)

        if not sparse_results:
            return dense_results[:top_k]
        return reciprocal_rank_fusion(dense_results, sparse_results, top_k=top_k)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chunk_to_search_result(chunk: RussianChunkResult) -> RussianSearchResult:
    """Convert an exact lookup chunk to a RussianSearchResult with score=1.0."""
    return RussianSearchResult(
        score=1.0,
        chunk_id=chunk.chunk_id,
        law_id=chunk.law_id,
        law_short=chunk.law_short,
        article_num=chunk.article_num,
        article_heading=chunk.article_heading,
        part_num=chunk.part_num,
        chunk_index=chunk.chunk_index,
        razdel=chunk.razdel,
        glava=chunk.glava,
        text=chunk.text,
        fragment_id=chunk.fragment_id,
        source_type=chunk.source_type,
        is_tombstone=chunk.is_tombstone,
        source_file=chunk.source_file,
    )
