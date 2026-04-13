"""
Case-text-to-evidence bridge for the interpreter / language-of-proceedings /
notice-and-summons issue cluster in Russian civil proceedings.

Covers:
  - Foreign party without interpreter
  - Inability to understand the court language
  - Failure to explain the right to an interpreter
  - Lack of official / proper court notice or summons
  - Combined cases (interpreter defect + notice defect)

Primary legal basis:    ГПК РФ (ст. 9, ст. 162, ст. 113 and related articles)
Supporting sources:     ЕКПЧ (ст. 5, ст. 6) and ФЗ-115

Deterministic, no LLM, no synthesis, no agent logic.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.modules.russia.retrieval.interpreter_issue import IssueEvidence, _to_evidence
from app.modules.russia.retrieval.schemas import RussianSearchResult

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ISSUE_CLUSTER = "interpreter_language_notice"
_PRIMARY_LAW = "local:ru/gpk"
_SUPPORT_LAWS = frozenset({"local:ru/echr", "local:ru/fl115"})
_SUPPORT_POOL_SIZE = 30
_DETECTION_THRESHOLD = 1.0  # minimum weighted score to activate a sub-issue

# ---------------------------------------------------------------------------
# Sub-issue signal definitions
# ---------------------------------------------------------------------------
# Each sub-issue has:
#   phrase_weight  : score per matched phrase
#   stem_weight    : score per matched stem token
#   phrases        : multi-word phrases matched as substrings of lowercased text
#   stems          : word-stem prefixes matched against space-split tokens
# ---------------------------------------------------------------------------

_SUBISSUE_SIGNALS: dict[str, dict] = {
    "interpreter_issue": {
        "phrase_weight": 2.0,
        "stem_weight": 1.0,
        "phrases": [
            "не получил переводчика",
            "не предоставили переводчика",
            "без переводчика",
            "не разъяснил право на переводчика",
            "право на переводчика",
            "не предоставили перевод",
            "переводчик не был предоставлен",
            "отказал в переводчике",
            "перевод документов",
            "перевод решения суда",
        ],
        "stems": ["переводчик"],
    },
    "language_issue": {
        "phrase_weight": 2.0,
        "stem_weight": 1.0,
        "phrases": [
            "не понимал язык",
            "не понимаю язык",
            "не владею языком",
            "не владеет языком",
            "язык заседания",
            "язык судопроизводства",
            "не мог защищать свои права",
            "не понимал содержания",
            "не понимал решения",
        ],
        "stems": ["язык"],  # язык, языком, языка
    },
    "notice_issue": {
        "phrase_weight": 2.0,
        "stem_weight": 1.0,
        "phrases": [
            "не вызвали в суд",
            "не был вызван",
            "не уведомлен",
            "не был уведомлен",
            "не был официально уведомлен",
            "не извещен",
            "не был извещен",
            "без извещения",
            "без вызова",
            "без надлежащего",
            "надлежащим образом",
            "надлежащего извещения",
            "рассмотрел дело без",
            "не получил повестку",
            "повестка не была вручена",
            "не уведомил",
        ],
        "stems": ["извещ", "вызов", "вызв", "уведомл", "повестк"],
    },
}

# ---------------------------------------------------------------------------
# Anchor articles — fetched via exact lookup per sub-issue.
# These are the key procedural articles and are always retrieved when a
# sub-issue is detected. Score is set to 1.0 (exact match).
# ---------------------------------------------------------------------------

_SUBISSUE_ANCHOR_ARTICLES: dict[str, list[str]] = {
    "interpreter_issue": ["9", "162"],
    "language_issue": ["9"],
    "notice_issue": ["113"],
}

# ---------------------------------------------------------------------------
# Canonical semantic queries — supplementary GPK enrichment per sub-issue.
# Run as hybrid_search constrained to GPK after anchor lookup.
# ---------------------------------------------------------------------------

_SUBISSUE_QUERIES: dict[str, str] = {
    "interpreter_issue": "переводчик в гражданском процессе",
    "language_issue": "язык судопроизводства",
    "notice_issue": "надлежащее извещение сторон о судебном заседании",
}

# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------

@dataclass
class CaseBridgeResult:
    """
    Result of the case-text-to-evidence bridge.

    Attributes
    ----------
    case_text           : original input case description
    is_matched          : True if any sub-issue signal was detected
    detected_issue      : issue cluster name (None if not matched)
    detected_subissues  : ordered list of detected sub-issue names
    matched_signals     : subissue → list of matched phrases/stems
    normalized_queries  : canonical retrieval query per detected sub-issue
    primary_results     : GPK evidence items (source_role='primary')
    supporting_results  : ЕКПЧ / ФЗ-115 evidence items (source_role='supporting')
    combined_results    : primary + supporting sorted by score descending
    """

    case_text: str
    is_matched: bool
    detected_issue: str | None
    detected_subissues: list[str] = field(default_factory=list)
    matched_signals: dict[str, list[str]] = field(default_factory=dict)
    normalized_queries: list[str] = field(default_factory=list)
    primary_results: list[IssueEvidence] = field(default_factory=list)
    supporting_results: list[IssueEvidence] = field(default_factory=list)
    combined_results: list[IssueEvidence] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Bridge class
# ---------------------------------------------------------------------------

class CaseIssueBridge:
    """
    Case-text-to-evidence bridge for the interpreter / language / notice issue
    cluster in Russian civil proceedings.

    Accepts a short natural-language case description and returns a structured
    evidence set identifying the primary GPK basis and supporting sources.

    Thread-safe: no mutable state after construction.

    Usage:
        bridge = CaseIssueBridge(service)

        result = bridge.analyze(
            "иностранный гражданин не получил переводчика в суде"
        )
        # result.is_matched          → True
        # result.detected_subissues  → ["interpreter_issue"]
        # result.primary_results     → GPK ст. 9, ст. 162, ...
        # result.combined_results    → all evidence sorted by score

        result = bridge.analyze(
            "иностранец без переводчика и без официального вызова в суд"
        )
        # result.detected_subissues  → ["interpreter_issue", "notice_issue"]
        # result.primary_results     → GPK ст. 9, ст. 162, ст. 113, ...
    """

    def __init__(self, service: object) -> None:
        self._service = service

    def analyze(
        self,
        case_text: str,
        top_k_primary: int = 8,
        top_k_support: int = 3,
        semantic_k: int = 3,
    ) -> CaseBridgeResult:
        """
        Analyze a case description and retrieve multi-source evidence.

        Steps
        -----
        1. Detect sub-issues via phrase + stem matching.
        2. Fetch anchor GPK articles (exact lookup, score=1.0) per sub-issue.
        3. Run semantic enrichment search (hybrid, GPK-constrained) per sub-issue.
        4. Run one unconstrained support pass; filter to ЕКПЧ + ФЗ-115.
        5. Deduplicate by chunk_id; sort by score.

        Args:
            case_text:      Short natural-language case description in Russian
            top_k_primary:  Maximum GPK results to return
            top_k_support:  Maximum ЕКПЧ/ФЗ-115 results to return
            semantic_k:     GPK semantic enrichment results per sub-issue

        Returns:
            CaseBridgeResult. If is_matched=False, primary/supporting/combined
            are empty lists.
        """
        text_lower = case_text.lower()

        # ── 1. Signal detection ───────────────────────────────────────────
        detected_subissues, matched_signals = _detect_subissues(text_lower)

        if not detected_subissues:
            log.debug("case_bridge.no_match case_text=%r", case_text[:80])
            return CaseBridgeResult(
                case_text=case_text,
                is_matched=False,
                detected_issue=None,
            )

        normalized_queries = [_SUBISSUE_QUERIES[si] for si in detected_subissues]

        log.debug(
            "case_bridge.matched subissues=%r case_text=%r",
            detected_subissues, case_text[:80],
        )

        # ── 2. Primary: anchor articles + semantic enrichment ─────────────
        primary_map: dict[str, IssueEvidence] = {}

        fetched_articles: set[str] = set()
        for subissue in detected_subissues:
            for art_num in _SUBISSUE_ANCHOR_ARTICLES.get(subissue, []):
                if art_num in fetched_articles:
                    continue
                fetched_articles.add(art_num)
                lookup = self._service.get_article(_PRIMARY_LAW, art_num)
                if lookup.hit:
                    for chunk in lookup.chunks[:2]:  # at most 2 chunks per anchor article
                        e = _chunk_to_evidence(chunk)
                        primary_map[e.chunk_id] = e

        for subissue in detected_subissues:
            q = _SUBISSUE_QUERIES[subissue]
            sem_results = self._service.hybrid_search(
                query=q, law_id=_PRIMARY_LAW, top_k=semantic_k
            )
            for r in sem_results:
                e = _to_evidence(r, "primary")
                if e.chunk_id not in primary_map:
                    primary_map[e.chunk_id] = e

        # ── 3. Support: ЕКПЧ + ФЗ-115 ─────────────────────────────────────
        support_query = case_text  # raw text gives best semantic coverage
        support_pool = self._service.hybrid_search(
            query=support_query, law_id=None, top_k=_SUPPORT_POOL_SIZE
        )
        support_raw = [r for r in support_pool if r.law_id in _SUPPORT_LAWS][:top_k_support]

        # ── 4. Build output ────────────────────────────────────────────────
        primary = sorted(primary_map.values(), key=lambda e: -e.score)[:top_k_primary]
        supporting = [_to_evidence(r, "supporting") for r in support_raw]
        combined = sorted(primary + supporting, key=lambda e: -e.score)

        return CaseBridgeResult(
            case_text=case_text,
            is_matched=True,
            detected_issue=_ISSUE_CLUSTER,
            detected_subissues=list(detected_subissues),
            matched_signals=matched_signals,
            normalized_queries=normalized_queries,
            primary_results=primary,
            supporting_results=supporting,
            combined_results=combined,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_subissues(
    text_lower: str,
) -> tuple[list[str], dict[str, list[str]]]:
    """
    Detect sub-issues in lowercased case text.

    Returns (detected_subissues, matched_signals) where:
      detected_subissues: ordered list of sub-issue names with score >= threshold
      matched_signals:    subissue → list of matched phrase/stem strings
    """
    detected: list[str] = []
    matched: dict[str, list[str]] = {}

    tokens = text_lower.split()

    for subissue, cfg in _SUBISSUE_SIGNALS.items():
        phrase_weight: float = cfg["phrase_weight"]
        stem_weight: float = cfg["stem_weight"]
        phrases: list[str] = cfg["phrases"]
        stems: list[str] = cfg["stems"]

        score = 0.0
        hits: list[str] = []

        for phrase in phrases:
            if phrase in text_lower:
                score += phrase_weight
                hits.append(phrase)

        for token in tokens:
            for stem in stems:
                if token.startswith(stem):
                    score += stem_weight
                    hits.append(f"~{stem}")
                    break  # one stem match per token

        if score >= _DETECTION_THRESHOLD:
            detected.append(subissue)
            matched[subissue] = hits

    return detected, matched


def _chunk_to_evidence(chunk: object) -> IssueEvidence:
    """Convert a RussianChunkResult (from exact lookup) to IssueEvidence."""
    return IssueEvidence(
        score=1.0,  # exact lookup — highest confidence
        chunk_id=chunk.chunk_id,
        law_id=chunk.law_id,
        law_short=chunk.law_short,
        article_num=chunk.article_num,
        article_heading=chunk.article_heading,
        text=chunk.text,
        is_tombstone=chunk.is_tombstone,
        source_role="primary",
    )
