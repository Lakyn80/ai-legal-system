"""
Reciprocal Rank Fusion (RRF) for Russian law retrieval.

Fuses dense and sparse result lists into a single ranked list of RussianSearchResult.

RRF score for each chunk:
  score = Σ  1 / (k + rank_in_list)
  where k=60 (standard) and the sum is over all result lists that contain the chunk.

Tie-breaking order:
  1. RRF score descending (higher is better)
  2. Dense rank ascending (prefer chunks ranked high by dense retriever)
  3. Sparse rank ascending
  4. Encounter order (stability)
  5. chunk_id lexicographic (determinism)

Does NOT:
  - Call any LLM
  - Access Qdrant
  - Import ingestion modules
"""
from __future__ import annotations

from math import inf

from app.modules.russia.retrieval.schemas import RussianSearchResult

_RRF_K = 60


def reciprocal_rank_fusion(
    dense_results: list[RussianSearchResult],
    sparse_results: list[RussianSearchResult],
    top_k: int | None = None,
) -> list[RussianSearchResult]:
    """
    Fuse dense and sparse result lists using Reciprocal Rank Fusion.

    Args:
        dense_results:  Ordered list from dense (vector) search, score-descending.
        sparse_results: Ordered list from sparse (BM25) search, score-descending.
        top_k:          Maximum results to return. None = return all fused results.

    Returns:
        List of RussianSearchResult in RRF-score-descending order.
        The .score field on each result is set to the RRF score.
        Duplicate chunk_ids are deduplicated — the higher-scored payload wins.
    """
    dense_rank = _build_rank_map(dense_results)
    sparse_rank = _build_rank_map(sparse_results)

    # Collect unique chunks — prefer payload from the first encounter (dense first)
    merged: dict[str, RussianSearchResult] = {}
    encounter_order: dict[str, int] = {}

    for results in (dense_results, sparse_results):
        for item in results:
            cid = item.chunk_id
            if not cid:
                continue
            if cid not in merged:
                merged[cid] = item
                encounter_order[cid] = len(encounter_order)

    # Compute RRF scores
    scored: list[tuple[float, float, float, int, str]] = []
    for cid, item in merged.items():
        rrf_score = 0.0
        if cid in dense_rank:
            rrf_score += 1.0 / (_RRF_K + dense_rank[cid])
        if cid in sparse_rank:
            rrf_score += 1.0 / (_RRF_K + sparse_rank[cid])

        scored.append((
            rrf_score,
            float(dense_rank.get(cid, inf)),
            float(sparse_rank.get(cid, inf)),
            encounter_order[cid],
            cid,
        ))

    scored.sort(key=lambda x: (-x[0], x[1], x[2], x[3], x[4]))
    limit = len(scored) if top_k is None else max(0, top_k)

    results_out: list[RussianSearchResult] = []
    for rrf_score, _, _, _, cid in scored[:limit]:
        item = merged[cid]
        # Replace .score with the RRF score for downstream consumers
        fused = RussianSearchResult(
            score=rrf_score,
            chunk_id=item.chunk_id,
            law_id=item.law_id,
            law_short=item.law_short,
            article_num=item.article_num,
            article_heading=item.article_heading,
            part_num=item.part_num,
            chunk_index=item.chunk_index,
            razdel=item.razdel,
            glava=item.glava,
            text=item.text,
            fragment_id=item.fragment_id,
            source_type=item.source_type,
            is_tombstone=item.is_tombstone,
            source_file=item.source_file,
        )
        results_out.append(fused)

    return results_out


# ── helpers ────────────────────────────────────────────────────────────────────

def _build_rank_map(results: list[RussianSearchResult]) -> dict[str, int]:
    """Map chunk_id → 1-based rank (first occurrence wins)."""
    rank_map: dict[str, int] = {}
    for rank, item in enumerate(results, start=1):
        if item.chunk_id and item.chunk_id not in rank_map:
            rank_map[item.chunk_id] = rank
    return rank_map
