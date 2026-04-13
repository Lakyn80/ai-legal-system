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
    fallback_applied: bool = False
    fallback_reason: str | None = None
    guaranteed_anchor_keys: list[tuple[str, str]] | None = None


_ISSUE_ANCHOR_GUARANTEES: dict[str, tuple[tuple[str, str], ...]] = {
    "interpreter_issue": (("local:ru/gpk", "9"), ("local:ru/gpk", "162")),
    "language_issue": (("local:ru/gpk", "9"),),
    "notice_issue": (("local:ru/gpk", "113"),),
    "service_address_issue": (("local:ru/gpk", "113"),),
    "foreign_party_issue": (("local:ru/gpk", "9"), ("local:ru/gpk", "162")),
    "alimony_issue": (("local:ru/sk", "80"), ("local:ru/sk", "81")),
    "alimony_debt_issue": (("local:ru/sk", "113"),),
    "alimony_enforcement_issue": (("local:ru/sk", "113"),),
}


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
    strict_taxonomy_mode: bool = True,
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
    guaranteed_anchor_keys = _build_guaranteed_anchor_keys(issue_flags)
    min_useful = min(top_k, max(1, len(guaranteed_anchor_keys)))
    if not candidate_rows and strict_taxonomy_mode:
        fallback_rows = _resolve_fallback_rows(
            svc=svc,
            taxonomy=taxonomy,
            mode=mode,
            query=query,
            top_k=top_k,
            trigger_reason="no_taxonomy_candidates",
            guaranteed_anchor_keys=guaranteed_anchor_keys,
            candidate_rows=[],
        )
        return TaxonomySearchOutcome(
            results=fallback_rows,
            issue_flags=issue_flags,
            taxonomy_applied=True,
            fallback_applied=True,
            fallback_reason="no_taxonomy_candidates",
            guaranteed_anchor_keys=guaranteed_anchor_keys,
        )

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
    ranked = _dedupe_by_article(ranked)
    if len(ranked) >= min_useful and _contains_minimum_anchors(ranked, guaranteed_anchor_keys):
        return TaxonomySearchOutcome(
            results=ranked[:top_k],
            issue_flags=issue_flags,
            taxonomy_applied=True,
            guaranteed_anchor_keys=guaranteed_anchor_keys,
        )
    trigger_reason = "retrieval_empty" if not ranked else "retrieval_below_threshold"
    fallback_rows = _resolve_fallback_rows(
        svc=svc,
        taxonomy=taxonomy,
        mode=mode,
        query=query,
        top_k=top_k,
        trigger_reason=trigger_reason,
        guaranteed_anchor_keys=guaranteed_anchor_keys,
        candidate_rows=candidate_rows,
        initial_rows=ranked,
    )
    if fallback_rows:
        used_deterministic = any(getattr(row, "source_type", "") == "deterministic_anchor_fallback" for row in fallback_rows)
        return TaxonomySearchOutcome(
            results=fallback_rows,
            issue_flags=issue_flags,
            taxonomy_applied=True,
            fallback_applied=True,
            fallback_reason="deterministic_anchor_injection" if used_deterministic else trigger_reason,
            guaranteed_anchor_keys=guaranteed_anchor_keys,
        )
    if strict_taxonomy_mode:
        return TaxonomySearchOutcome(
            results=_inject_deterministic_anchor_references(taxonomy, guaranteed_anchor_keys, top_k),
            issue_flags=issue_flags,
            taxonomy_applied=True,
            fallback_applied=True,
            fallback_reason="deterministic_anchor_injection",
            guaranteed_anchor_keys=guaranteed_anchor_keys,
        )

    return TaxonomySearchOutcome(
        results=run_mode_search(svc, mode, query, None, top_k),
        issue_flags=issue_flags,
        taxonomy_applied=False,
        guaranteed_anchor_keys=guaranteed_anchor_keys,
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
        anchor_boost = {"core": 4.0, "strong": 2.5, "secondary": 0.9, "peripheral": 0.0}[
            anchor_priority.get(key, "peripheral")
        ]
        law_boost = min(law_priority.get(row.law_id, 0) / 80.0, 3.0)
        boosted.append(replace(row, score=base + anchor_boost + law_boost))

    boosted.sort(key=lambda x: x.score, reverse=True)
    return boosted[:top_k]


def _build_guaranteed_anchor_keys(issue_flags: list[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for issue in issue_flags:
        for key in _ISSUE_ANCHOR_GUARANTEES.get(issue, ()):
            if key not in out:
                out.append(key)
    return out


def _contains_minimum_anchors(rows: list[RussianSearchResult], required: list[tuple[str, str]]) -> bool:
    if not required:
        return bool(rows)
    seen = {(r.law_id, str(r.article_num or "")) for r in rows}
    return any(key in seen for key in required)


def _dedupe_by_article(rows: list[RussianSearchResult]) -> list[RussianSearchResult]:
    by_article: dict[tuple[str, str], RussianSearchResult] = {}
    for row in rows:
        key = (row.law_id, str(row.article_num or ""))
        cur = by_article.get(key)
        if cur is None or row.score > cur.score:
            by_article[key] = row
    deduped = list(by_article.values())
    deduped.sort(key=lambda x: x.score, reverse=True)
    return deduped


def _resolve_fallback_rows(
    *,
    svc,
    taxonomy: FocusLegalTaxonomyService,
    mode: str,
    query: str,
    top_k: int,
    trigger_reason: str,
    guaranteed_anchor_keys: list[tuple[str, str]],
    candidate_rows: list,
    initial_rows: list[RussianSearchResult] | None = None,
) -> list[RussianSearchResult]:
    pool_k = max(top_k * 4, 20)
    merged: dict[str, RussianSearchResult] = {}
    if initial_rows:
        for row in initial_rows:
            merged[row.chunk_id] = row

    fetch_laws = sorted({law for law, _ in guaranteed_anchor_keys} | {r.law_id for r in candidate_rows})
    for c_law in fetch_laws:
        for row in run_mode_search(svc, mode, query, c_law, pool_k):
            cur = merged.get(row.chunk_id)
            if cur is None or row.score > cur.score:
                merged[row.chunk_id] = row

    deduped = _dedupe_by_article(list(merged.values()))
    by_key = {(r.law_id, str(r.article_num or "")): r for r in deduped}

    anchors: list[RussianSearchResult] = []
    for key in guaranteed_anchor_keys:
        row = by_key.get(key)
        if row is not None:
            anchors.append(replace(row, score=max(row.score, 10_000.0 - len(anchors))))

    allowed_laws = {law for law, _ in guaranteed_anchor_keys}
    for r in candidate_rows:
        allowed_laws.add(r.law_id)
    tail = [row for row in deduped if row not in anchors and (not allowed_laws or row.law_id in allowed_laws)]
    tail.sort(key=lambda x: x.score, reverse=True)

    final_rows = _dedupe_by_article(anchors + tail)
    if _contains_minimum_anchors(final_rows, guaranteed_anchor_keys):
        return final_rows[:top_k]

    # Hard guarantee: supported issue never returns empty, even when index lacks chunks.
    injected = _inject_deterministic_anchor_references(taxonomy, guaranteed_anchor_keys, top_k)
    if injected:
        return injected
    # Should not happen for supported issues, but keep deterministic fallback behavior explicit.
    if trigger_reason in {"no_taxonomy_candidates", "retrieval_empty", "retrieval_below_threshold"}:
        return []
    return []


def _inject_deterministic_anchor_references(
    taxonomy: FocusLegalTaxonomyService,
    guaranteed_anchor_keys: list[tuple[str, str]],
    top_k: int,
) -> list[RussianSearchResult]:
    out: list[RussianSearchResult] = []
    for idx, (law_id, article_num) in enumerate(guaranteed_anchor_keys):
        law = taxonomy.get_law(law_id)
        article = taxonomy.get_article(law_id, article_num)
        law_short = law.law_short if law is not None else law_id
        article_heading = article.article_heading if article is not None else ""
        out.append(
            RussianSearchResult(
                score=20_000.0 - idx,
                chunk_id=f"deterministic-anchor:{law_id}:{article_num}",
                law_id=law_id,
                law_short=law_short,
                article_num=article_num,
                article_heading=article_heading,
                part_num=None,
                chunk_index=0,
                razdel=None,
                glava="",
                text=f"Deterministic fallback anchor reference: {law_short} ст.{article_num}",
                fragment_id=f"deterministic-anchor/{law_id}/{article_num}",
                source_type="deterministic_anchor_fallback",
                is_tombstone=False,
                source_file="deterministic_anchor_fallback",
            )
        )
    deduped = _dedupe_by_article(out)
    return deduped[:top_k]
