from __future__ import annotations

import re

from app.modules.czechia.retrieval.schemas import EvidencePack, EvidencePackItem, QueryUnderstanding, RetrievalPlan
from app.modules.czechia.retrieval.text_utils import overlap_ratio, pick_primary_paragraph

# Numbered entries in derogation/amendment schedules, e.g.:
#   "1. zákon č. 65/1965 Sb., zákoník práce ,"
#   "16. nařízení vlády č. 108/1994 Sb., ..."
# These rank artificially high on BM25 but are never the answer to an
# informational query — penalise them early so they don't reach the top.
_INDEX_LINE_RE = re.compile(
    r"^\d{1,3}\.\s+(?:z[aá]kon|na[rř][íi]zen[íi]|vyhl[áa][šs]ka|sd[eě]len[íi])",
    re.IGNORECASE | re.UNICODE,
)
_SECTION_HEADING_RE = re.compile(
    r"^(?:část|hlava|díl|oddíl|pododdíl|kapitola)\b",
    re.IGNORECASE | re.UNICODE,
)
_AMENDMENT_LINE_RE = re.compile(
    r"(?:z[aá]kon|na[rř][íi]zen[íi](?:\s+vl[aá]dy)?|vyhl[áa][šs]ka|sd[eě]len[íi])\s+č\.",
    re.IGNORECASE | re.UNICODE,
)
_HEADING_VERB_HINTS = {
    "je",
    "jsou",
    "má",
    "ma",
    "musí",
    "musi",
    "může",
    "muze",
    "lze",
    "činí",
    "cini",
    "obsahuje",
    "obsahovat",
    "upravuje",
    "vzniká",
    "vznika",
    "zaniká",
    "zanika",
    "trvá",
    "trva",
    "skončí",
    "skonci",
}
_INDEX_LINE_PENALTY = 0.55
_HEADING_PENALTY = 0.35
_SECTION_HEADING_PENALTY = 0.45
_ALL_CAPS_HEADING_PENALTY = 0.15
_AMENDMENT_LINE_PENALTY = 0.35


def _structural_penalty(text: str) -> float:
    """Return a static score penalty for non-substantive chunk types."""
    value = (text or "").strip()
    if not value:
        return 0.0

    penalty = 0.0
    words = re.findall(r"\w+", value, flags=re.UNICODE)

    if _INDEX_LINE_RE.match(value):
        penalty += _INDEX_LINE_PENALTY
    elif _AMENDMENT_LINE_RE.search(value) and len(value) < 140:
        penalty += _AMENDMENT_LINE_PENALTY

    if _SECTION_HEADING_RE.match(value):
        penalty += _SECTION_HEADING_PENALTY

    if _looks_like_heading(value, words):
        penalty += _HEADING_PENALTY
        if _is_all_caps_heading(value):
            penalty += _ALL_CAPS_HEADING_PENALTY

    return min(penalty, 0.85)


def _looks_like_heading(value: str, words: list[str]) -> bool:
    if not words:
        return False
    if len(value) >= 120 or len(words) > 12:
        return False
    if re.search(r"[.!?;:]", value):
        return False

    lowered = value.lower()
    if any(hint in lowered for hint in _HEADING_VERB_HINTS):
        return False

    return True


def _is_all_caps_heading(value: str) -> bool:
    letters = re.sub(r"[^A-Za-zÀ-ž]", "", value, flags=re.UNICODE)
    return bool(letters) and letters == letters.upper()


class CzechLawReranker:
    def rerank(
        self,
        candidates: list[dict],
        understanding: QueryUnderstanding,
        plan: RetrievalPlan,
    ) -> EvidencePack:
        if not candidates:
            return EvidencePack(items=[], understanding=understanding, plan=plan)

        max_dense = max((float(hit.get("_dense_score", 0.0)) for hit in candidates), default=0.0)
        max_sparse = max((float(hit.get("_sparse_score", 0.0)) for hit in candidates), default=0.0)
        max_rrf = max((float(hit.get("_rrf_score", 0.0)) for hit in candidates), default=0.0)

        items: list[EvidencePackItem] = []
        for hit in candidates:
            law_iri = str(hit.get("law_iri", ""))
            paragraph = pick_primary_paragraph(hit)
            dense_score = float(hit.get("_dense_score", 0.0))
            sparse_score = float(hit.get("_sparse_score", 0.0))
            rrf_score = float(hit.get("_rrf_score", 0.0))

            dense_norm = _normalize_score(dense_score, max_dense)
            sparse_norm = _normalize_score(sparse_score, max_sparse)
            rrf_norm = _normalize_score(rrf_score, max_rrf)

            strict_law_match = bool(plan.law_filter) and law_iri in plan.law_filter
            preferred_law_match = bool(plan.preferred_law_iris) and law_iri in plan.preferred_law_iris
            paragraph_match = bool(paragraph and paragraph in plan.paragraph_filter)
            exact_match = bool(hit.get("_exact_match"))
            structural_neighbor = bool(hit.get("_structural_neighbor"))
            text_overlap = overlap_ratio(understanding.normalized_tokens, str(hit.get("text", "")))

            penalty = _structural_penalty(str(hit.get("text", "")))
            if plan.law_filter and law_iri and law_iri not in plan.law_filter:
                penalty += plan.boost_factors.law_mismatch_penalty
            elif (
                understanding.detected_domain != "unknown"
                and plan.preferred_law_iris
                and law_iri
                and law_iri not in plan.preferred_law_iris
            ):
                penalty += plan.boost_factors.law_mismatch_penalty * 0.35

            score = (
                (rrf_norm * 0.34)
                + (dense_norm * 0.22)
                + (sparse_norm * 0.22)
                + (text_overlap * plan.boost_factors.text_overlap_weight)
                + (plan.boost_factors.law_match_boost if strict_law_match else 0.0)
                + (plan.boost_factors.preferred_law_boost if preferred_law_match else 0.0)
                + (plan.boost_factors.paragraph_match_boost if paragraph_match else 0.0)
                + (plan.boost_factors.exact_match_boost if exact_match else 0.0)
                + (plan.boost_factors.structural_neighbor_boost if structural_neighbor else 0.0)
                - penalty
            )

            items.append(
                EvidencePackItem(
                    chunk_id=str(hit.get("chunk_id", "")),
                    law_iri=law_iri,
                    paragraph=paragraph,
                    text=str(hit.get("text", "")),
                    score=score,
                    source_metadata={
                        "fragment_id": hit.get("fragment_id"),
                        "chunk_index": int(hit.get("chunk_index", 0) or 0),
                        "source_type": hit.get("source_type", "law_fragment"),
                        "metadata_ref": hit.get("metadata_ref"),
                    },
                    validation_flags={
                        "strict_law_match": strict_law_match,
                        "preferred_law_match": preferred_law_match,
                        "paragraph_match": paragraph_match,
                        "exact_match": exact_match,
                        "structural_neighbor": structural_neighbor,
                        "text_overlap": text_overlap,
                        "neighbor_of_exact_match": bool(hit.get("_neighbor_of_exact_match")),
                    },
                    chunk_index=int(hit.get("chunk_index", 0) or 0),
                    source_type=str(hit.get("source_type", "law_fragment")),
                    source=hit.get("metadata_ref"),
                    dense_score=dense_score,
                    sparse_score=sparse_score,
                    rrf_score=rrf_score,
                )
            )

        items.sort(
            key=lambda item: (
                -item.score,
                -bool(item.validation_flags.get("exact_match")),
                -bool(item.validation_flags.get("paragraph_match")),
                -bool(item.validation_flags.get("strict_law_match")),
                -bool(item.validation_flags.get("preferred_law_match")),
                item.chunk_index,
                item.chunk_id,
            )
        )
        return EvidencePack(items=items, understanding=understanding, plan=plan)


def _normalize_score(value: float, maximum: float) -> float:
    if maximum <= 0.0:
        return 0.0
    return value / maximum
