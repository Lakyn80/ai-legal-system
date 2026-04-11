from __future__ import annotations

import re

from app.modules.czechia.retrieval.schemas import EvidencePack, EvidencePackItem, QueryUnderstanding, RetrievalPlan
from app.modules.czechia.retrieval.text_utils import normalize_text, overlap_ratio, pick_primary_paragraph

# Numbered entries in derogation/amendment schedules, e.g.:
#   "1. zákon č. 65/1965 Sb., zákoník práce ,"
#   "16. nařízení vlády č. 108/1994 Sb., ..."
#   "21. Část první zákona č. 367/2000 Sb., ..."  ← part-of-act entries
# These rank artificially high on BM25 but are never the answer to an
# informational query — penalise them early so they don't reach the top.
_INDEX_LINE_RE = re.compile(
    r"^\d{1,3}\.\s+(?:(?:část|hlava|díl)\s+\w+\s+)?(?:z[aá]kon|na[rř][íi]zen[íi]|vyhl[áa][šs]ka|sd[eě]len[íi])",
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
# Matches "reference-only" fragments: very short text consisting primarily of
# cross-paragraph references with no substantive content.  Examples:
#   "§ 52 odst. 2 a § 54"          ← pure reference, no normative text
#   "odstavce 1 a 2"               ← structural connector only
_PURE_REFERENCE_RE = re.compile(
    r"^(?:§\s*\d+[a-z]?(?:\s+odst\.\s*\d+)?(?:\s+(?:a|nebo|,)\s*§\s*\d+[a-z]?)*"
    r"|odstavce?\s+\d+(?:\s+(?:a|nebo|,)\s*\d+)*"
    r"|písmene?\s+[a-z]\)(?:\s+(?:a|nebo)\s+[a-z]\))*)\s*[,.]?$",
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
_PURE_REFERENCE_PENALTY = 0.25   # short cross-reference fragments, lower than heading

# ── Topic heading boost ────────────────────────────────────────────────────────
# For non-exact (topic/domain) modes, boost substantive named headings like
# "Odstupné", "Dovolená", "Výpověď" that name an institute of law — these are
# the most relevant entry points for a topic query and should rank above
# random mid-paragraph fragments.
#
# Conditions (all must hold):
#   1. query_mode is not exact_lookup
#   2. chunk belongs to law_filter or preferred_law_iris (no cross-law boost)
#   3. text is a short title-case or upper-case heading without verb content
#      (i.e. _looks_like_heading() is True — already excludes ČÁST/HLAVA/DÍL)
#   4. NOT a structural section heading (ČÁST, HLAVA, DÍL …)
#   5. At least one heading token overlaps with the query's normalized tokens
_TOPIC_HEADING_BOOST = 0.18


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

    # Pure cross-reference fragment: "§ 52 odst. 1 a § 54" — no normative text.
    # Lighter penalty than index lines because they can still provide context.
    if not penalty and _PURE_REFERENCE_RE.match(value):
        penalty += _PURE_REFERENCE_PENALTY

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


def _topic_heading_boost(
    text: str,
    law_iri: str,
    strict_law_match: bool,
    preferred_law_match: bool,
    query_mode: str,
    query_tokens: list[str],
) -> float:
    """
    Return a positive boost for named legal-institute headings in topic mode.

    Zero is returned when:
    - query is exact_lookup (paragraph headings are handled by exact_lookup sort)
    - chunk does not belong to the query's target law(s)
    - text is a structural section heading (ČÁST/HLAVA/DÍL)
    - text is not heading-like (too long, has verb content)
    - no heading token overlaps with query tokens
    """
    if query_mode == "exact_lookup":
        return 0.0
    if not (strict_law_match or preferred_law_match):
        return 0.0

    value = (text or "").strip()
    if not value:
        return 0.0

    # Exclude structural section headings (ČÁST PRVNÍ, HLAVA II, …)
    if _SECTION_HEADING_RE.match(value):
        return 0.0
    # Exclude derogation index lines
    if _INDEX_LINE_RE.match(value):
        return 0.0

    words = re.findall(r"\w+", value, flags=re.UNICODE)
    if not _looks_like_heading(value, words):
        return 0.0

    # Require at least one heading token to match a query token (normalised).
    heading_tokens = set(normalize_text(value).split())
    if not heading_tokens.intersection(query_tokens):
        return 0.0

    return _TOPIC_HEADING_BOOST


def diversify_by_paragraph(
    items: list[EvidencePackItem],
    top_k: int,
    max_per_paragraph: int = 2,
) -> list[EvidencePackItem]:
    """
    Ensure coverage across paragraphs for topic/domain queries.

    Keeps at most `max_per_paragraph` items per (law_iri, paragraph) group in
    the primary selection, appending overflow items afterwards so the final
    list still reaches top_k.

    Not applied for exact_lookup mode — that needs all chunks of one paragraph.
    """
    para_count: dict[tuple[str, str], int] = {}
    primary: list[EvidencePackItem] = []
    overflow: list[EvidencePackItem] = []

    for item in items:
        key = (item.law_iri or "", item.paragraph or item.chunk_id)
        count = para_count.get(key, 0)
        if count < max_per_paragraph:
            para_count[key] = count + 1
            primary.append(item)
        else:
            overflow.append(item)
        if len(primary) >= top_k:
            break

    # Fill up to top_k from overflow if primary came up short
    result = primary + overflow[: max(0, top_k - len(primary))]
    return result[:top_k]


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
            text = str(hit.get("text", ""))
            text_overlap = overlap_ratio(understanding.normalized_tokens, text)

            penalty = _structural_penalty(text)
            if plan.law_filter and law_iri and law_iri not in plan.law_filter:
                penalty += plan.boost_factors.law_mismatch_penalty
            elif (
                understanding.detected_domain != "unknown"
                and plan.preferred_law_iris
                and law_iri
                and law_iri not in plan.preferred_law_iris
            ):
                penalty += plan.boost_factors.law_mismatch_penalty * 0.35

            heading_boost = _topic_heading_boost(
                text=text,
                law_iri=law_iri,
                strict_law_match=strict_law_match,
                preferred_law_match=preferred_law_match,
                query_mode=understanding.query_mode,
                query_tokens=understanding.normalized_tokens,
            )

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
                + heading_boost
                - penalty
            )

            items.append(
                EvidencePackItem(
                    chunk_id=str(hit.get("chunk_id", "")),
                    law_iri=law_iri,
                    paragraph=paragraph,
                    text=text,
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
                        "heading_boost": heading_boost > 0,
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
