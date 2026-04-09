from __future__ import annotations

from math import inf

_RRF_K = 60


def rrf_fuse(
    dense_hits: list[dict],
    sparse_hits: list[dict],
    top_k: int | None = None,
) -> list[dict]:
    dense_rank = _build_rank_map(dense_hits)
    sparse_rank = _build_rank_map(sparse_hits)

    merged: dict[str, dict] = {}
    encounter_order: dict[str, int] = {}

    for hits in (dense_hits, sparse_hits):
        for hit in hits:
            chunk_id = hit.get("chunk_id")
            if not chunk_id:
                continue
            if chunk_id not in merged:
                merged[chunk_id] = dict(hit)
                encounter_order[chunk_id] = len(encounter_order)
                continue
            _merge_payload(merged[chunk_id], hit)

    scored: list[tuple[float, float, float, int, str]] = []
    for chunk_id, payload in merged.items():
        score = 0.0
        if chunk_id in dense_rank:
            score += 1.0 / (_RRF_K + dense_rank[chunk_id])
        if chunk_id in sparse_rank:
            score += 1.0 / (_RRF_K + sparse_rank[chunk_id])

        payload["_rrf_score"] = score
        payload["_dense_rank"] = dense_rank.get(chunk_id)
        payload["_sparse_rank"] = sparse_rank.get(chunk_id)

        scored.append(
            (
                score,
                float(dense_rank.get(chunk_id, inf)),
                float(sparse_rank.get(chunk_id, inf)),
                encounter_order[chunk_id],
                chunk_id,
            )
        )

    scored.sort(key=lambda item: (-item[0], item[1], item[2], item[3], item[4]))
    limit = len(scored) if top_k is None else max(0, top_k)

    results: list[dict] = []
    for _, _, _, _, chunk_id in scored[:limit]:
        results.append(merged[chunk_id])
    return results


def _build_rank_map(hits: list[dict]) -> dict[str, int]:
    rank_map: dict[str, int] = {}
    for index, hit in enumerate(hits, start=1):
        chunk_id = hit.get("chunk_id")
        if chunk_id and chunk_id not in rank_map:
            rank_map[chunk_id] = index
    return rank_map


def _merge_payload(target: dict, source: dict) -> None:
    for key, value in source.items():
        if key in {"_dense_score", "_sparse_score", "_rrf_score"}:
            target[key] = max(float(target.get(key, 0.0)), float(value or 0.0))
            continue
        if key not in target or target[key] in (None, "", []):
            target[key] = value
