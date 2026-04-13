"""Shared taxonomy-first retrieval helpers for Russian search flows."""
from __future__ import annotations

from dataclasses import dataclass, replace

from app.modules.common.legal_taxonomy.service import FocusLegalTaxonomyService
from app.modules.russia.retrieval.schemas import RussianSearchResult


@dataclass(frozen=True)
class TaxonomySearchOutcome:
    results: list[RussianSearchResult]
    issue_flags: list[str]
    taxonomy_applied: bool


def run_mode_search(svc, mode: str, query: str, law_id: str | None, top_k: int) -> list[RussianSearchResult]:
    base = getattr(svc, "_taxonomy_base_search", None)
    if callable(base):
        return base(mode=mode, query=query, law_id=law_id, top_k=top_k)

    if mode == "dense":
        return svc.search(query, law_id=law_id, top_k=top_k)
    if mode == "sparse":
        return svc.sparse_search(query, law_id=law_id, top_k=top_k)
    if mode == "topic":
        raw = svc.topic_search(query, top_k=max(top_k * 4, top_k))
        if law_id is None:
            return raw[:top_k]
        return [r for r in raw if r.law_id == law_id][:top_k]
    return svc.hybrid_search(query, law_id=law_id, top_k=top_k)


def taxonomy_first_search(
    *,
    svc,
    taxonomy: FocusLegalTaxonomyService,
    mode: str,
    query: str,
    top_k: int,
    law_id: str | None,
) -> TaxonomySearchOutcome:
    issue_flags = taxonomy.detect_issue_flags(query)

    if law_id is not None:
        return TaxonomySearchOutcome(
            results=run_mode_search(svc, mode, query, law_id, top_k),
            issue_flags=issue_flags,
            taxonomy_applied=False,
        )

    if not issue_flags:
        return TaxonomySearchOutcome(
            results=run_mode_search(svc, mode, query, None, top_k),
            issue_flags=[],
            taxonomy_applied=False,
        )

    cand = taxonomy.build_candidates_for_query(query)
    candidate_rows = [
        r for r in cand.candidate_articles if r.legal_role in {"primary_basis", "procedural_support", "enforcement_support"}
    ]
    candidate_laws = sorted({r.law_id for r in candidate_rows}) or sorted(cand.candidate_laws)
    pool_k = max(top_k * 4, 20)
    merged: dict[str, RussianSearchResult] = {}
    for c_law in candidate_laws:
        law_results = run_mode_search(svc, mode, query, c_law, pool_k)
        for row in law_results:
            cur = merged.get(row.chunk_id)
            if cur is None or row.score > cur.score:
                merged[row.chunk_id] = row

    raw0 = list(merged.values())
    ranked = _apply_taxonomy_ranking(raw0, taxonomy, issue_flags, candidate_rows, top_k)
    if ranked:
        return TaxonomySearchOutcome(results=ranked, issue_flags=issue_flags, taxonomy_applied=True)

    return TaxonomySearchOutcome(
        results=run_mode_search(svc, mode, query, None, top_k),
        issue_flags=issue_flags,
        taxonomy_applied=False,
    )


def _apply_taxonomy_ranking(
    raw: list[RussianSearchResult],
    taxonomy: FocusLegalTaxonomyService,
    issue_flags: list[str],
    candidate_rows: list,
    top_k: int,
) -> list[RussianSearchResult]:
    if not issue_flags:
        return raw[:top_k]

    candidate_keys: set[tuple[str, str]] = {(r.law_id, str(r.article_num)) for r in candidate_rows}
    if not candidate_keys:
        return raw[:top_k]

    anchor_priority = {(r.law_id, str(r.article_num)): r.anchor_priority for r in candidate_rows}
    topic_hints: list[str] = []
    for flag in issue_flags:
        for topic in taxonomy.get_topics_for_issue(flag):
            if topic not in topic_hints:
                topic_hints.append(topic)

    law_priority: dict[str, int] = {}
    for topic in topic_hints:
        for l_id, score in taxonomy.get_law_priority_for_topic(topic).items():
            law_priority[l_id] = max(score, law_priority.get(l_id, 0))

    boosted: list[RussianSearchResult] = []
    for row in raw:
        key = (row.law_id, str(row.article_num or ""))
        if key not in candidate_keys:
            continue
        base = float(row.score)
        anchor_boost = {"core": 2.5, "strong": 1.6, "secondary": 0.6, "peripheral": 0.0}[
            anchor_priority.get(key, "peripheral")
        ]
        law_boost = min(law_priority.get(row.law_id, 0) / 100.0, 2.0)
        boosted.append(replace(row, score=base + anchor_boost + law_boost))

    boosted.sort(key=lambda x: x.score, reverse=True)
    return boosted[:top_k]
