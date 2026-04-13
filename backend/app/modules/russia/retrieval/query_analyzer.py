"""
Russian query analyzer — Step 8.

Provides minimal deterministic query understanding for:
  - Family law topics (→ local:ru/sk)
  - Civil procedural topics (→ local:ru/gpk)
  - Civil law topics (→ local:ru/gk/1)
  - Employment law topics (→ local:ru/tk)

Detects:
  1. Law aliases (e.g. "ск рф", "гпк рф") → canonical law_id
  2. Exact article references (ст. 81, статья 19.1) → article number
  3. Topic signals → preferred law_id(s)
  4. Query mode: exact_lookup | law_constrained_search | topic_search | broad_search

Does NOT:
  - Call any LLM
  - Access Qdrant
  - Import ingestion modules
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Matches: ст. 81 / ст.81 / ст 81 / ст.19.1 / статья 81 / статьи 81
_ARTICLE_RE = re.compile(
    r'\b(?:ст(?:атьи|атья|\.)?\.?\s*)(\d+(?:\.\d+)?)',
    re.IGNORECASE | re.UNICODE,
)

# ---------------------------------------------------------------------------
# Law aliases — matched as substrings of the lowercased query.
# Sorted longest-first so more specific aliases take precedence.
# Maps alias → canonical law_id
# ---------------------------------------------------------------------------
_LAW_ALIASES: list[tuple[str, str]] = sorted(
    [
        # Семейный кодекс
        ("семейный кодекс",                      "local:ru/sk"),
        ("ск рф",                                "local:ru/sk"),
        ("семейному кодексу",                    "local:ru/sk"),
        ("семейного кодекса",                    "local:ru/sk"),
        # Гражданский процессуальный кодекс
        ("гражданский процессуальный кодекс",    "local:ru/gpk"),
        ("гражданско-процессуальный кодекс",     "local:ru/gpk"),
        ("гпк рф",                               "local:ru/gpk"),
        ("гпк",                                  "local:ru/gpk"),
        # Гражданский кодекс (be careful — must not match гпк / гражданский процессуальный)
        ("гражданский кодекс",                   "local:ru/gk/1"),
        ("гк рф",                                "local:ru/gk/1"),
        # Трудовой кодекс
        ("трудовой кодекс",                      "local:ru/tk"),
        ("тк рф",                                "local:ru/tk"),
        # Европейская конвенция о защите прав человека (ЕКПЧ)
        ("конвенция о защите прав человека и основных свобод", "local:ru/echr"),
        ("конвенция о защите прав человека",     "local:ru/echr"),
        ("екпч",                                 "local:ru/echr"),
        # ФЗ-115 (О правовом положении иностранных граждан)
        ("федеральный закон 115-фз",             "local:ru/fl115"),
        ("фз-115",                               "local:ru/fl115"),
        ("115-фз",                               "local:ru/fl115"),
    ],
    key=lambda x: -len(x[0]),  # longest first
)

# ---------------------------------------------------------------------------
# Topic signals
#
# Each entry is (topic_id, phrase_list, stem_list)
# phrase_list: multi-word phrases — matched as substrings of lowercased query
# stem_list:   word-stems — matched as prefix of any space-separated token
#
# Topic → preferred law_ids mapping
# ---------------------------------------------------------------------------

_TOPIC_PREFERRED_LAWS: dict[str, list[str]] = {
    "family_law":     ["local:ru/sk"],
    "procedural_law": ["local:ru/gpk"],
    "civil_law":      ["local:ru/gk/1"],
    "employment_law": ["local:ru/tk"],
}

# (topic_id, phrase_weight, stem_weight, phrases, stems)
_TOPIC_SIGNALS: list[tuple[str, float, float, list[str], list[str]]] = [
    (
        "family_law",
        3.0, 1.5,
        [
            "порядок общения с ребенком",
            "определение места жительства ребенка",
            "место жительства ребенка",
            "место жительства детей",
            "лишение родительских прав",
            "ограничение родительских прав",
            "родительские права",
            "родительские обязанности",
            "права родителей",
            "орган опеки и попечительства",
            "органы опеки",
            "орган опеки",
            "усыновление",
            "удочерение",
            "расторжение брака",
            "раздел общего имущества",
            "алиментные обязательства",
            "алименты",
            "брачный договор",
            "опека и попечительство",
            "семейные отношения",
            "семейное законодательство",
            "права детей",
            "защита прав детей",
        ],
        [
            "ребен",    # ребенок, ребенка, ребенку
            "алимент",  # алименты, алиментных
            "усынов",   # усыновление, усыновить
            "семейн",   # семейный, семейного
            "опекун",   # опекун, опекуна
            "попечит",  # попечитель, попечительства
            "брачн",    # брачный
            "супруг",   # супруг, супруги, супружеский
            "развод",   # развод, развода
        ],
    ),
    (
        "procedural_law",
        3.0, 1.5,
        [
            "апелляционная жалоба",
            "апелляционное определение",
            "кассационная жалоба",
            "кассационное обжалование",
            "надзорная жалоба",
            "процессуальные нарушения",
            "отмена решения суда",
            "обжалование решения суда",
            "исковое заявление",
            "подача иска",
            "гражданский процесс",
            "судебное разбирательство",
            "судебное заседание",
            "доказательства в суде",
            "стороны процесса",
            "истец и ответчик",
            "обеспечение иска",
            "судебные расходы",
            "мировое соглашение",
            "исполнение судебного решения",
            "подсудность",
            "подведомственность",
            "процессуальные сроки",
            "извещение сторон",
            "судебная повестка",
            # interpreter / language of proceedings
            "язык судопроизводства",
            "язык гражданского судопроизводства",
            "право на переводчика",
            "не владеющий языком судопроизводства",
            "лицо не владеющее языком",
            "переводчик в гражданском процессе",
            "переводчик в суде",
            "иностранный гражданин в суде",
        ],
        [
            "апелляц",   # апелляционная, апелляции
            "кассац",    # кассационная, кассации
            "судопроизв", # судопроизводство
            "процессуал", # процессуальный
            "исковы",    # исковое, исковых
            "ответчик",
            "истец",
            "судебн",    # судебный, судебного, судебные
            "подсудн",   # подсудность, подсудного
            "переводчик",  # переводчик, переводчика, переводчику
            "иностран",    # иностранец, иностранца, иностранный (covers all forms)
        ],
    ),
    (
        "civil_law",
        2.0, 1.0,
        [
            "гражданские права",
            "гражданские обязательства",
            "сделка",
            "ничтожная сделка",
            "оспоримая сделка",
            "исковая давность",
            "право собственности",
            "возмещение убытков",
            "неосновательное обогащение",
            "договор",
        ],
        [
            "гражданск",  # гражданский, гражданского
            "обязательств",
            "сделк",
            "собственност",
        ],
    ),
    (
        "employment_law",
        2.0, 1.0,
        [
            "трудовой договор",
            "расторжение трудового договора",
            "увольнение",
            "трудовые отношения",
            "права работника",
            "работодатель",
        ],
        [
            "трудов",   # трудовой, трудового
            "работодат", # работодатель
            "работник",
            "уволен",
        ],
    ),
]

# Confidence threshold to use hard law filter in topic_search
_TOPIC_CONFIDENCE_THRESHOLD = 2.5

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RussianQueryUnderstanding:
    """Result of analyzing a Russian legal query."""

    raw_query: str
    """Original unmodified query."""

    cleaned_query: str
    """Query with law aliases stripped (for embedding / BM25 query encoding)."""

    detected_law_ids: list[str] = field(default_factory=list)
    """Canonical law IDs detected from explicit aliases in the query."""

    detected_article: str | None = None
    """Article number extracted from explicit reference (e.g. '81', '19.1')."""

    detected_topic: str | None = None
    """Detected topic category: family_law | procedural_law | civil_law | employment_law | None."""

    topic_confidence: float = 0.0
    """Sum of matched topic signal weights."""

    preferred_law_ids: list[str] = field(default_factory=list)
    """Law IDs to prefer in retrieval (from alias detection + topic inference)."""

    query_mode: str = "broad_search"
    """
    One of:
      exact_lookup           — explicit law + article number detected
      law_constrained_search — explicit law alias detected, no article
      topic_search           — topic signals detected, no explicit law alias
      broad_search           — no strong signals
    """


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------

class RussianQueryAnalyzer:
    """
    Deterministic, rule-based query understanding for Russian legal retrieval.

    Thread-safe: no mutable state.

    Usage:
        analyzer = RussianQueryAnalyzer()
        u = analyzer.analyze("порядок общения с ребенком ск рф")
        # u.query_mode == "law_constrained_search"
        # u.detected_law_ids == ["local:ru/sk"]
    """

    def analyze(self, query: str) -> RussianQueryUnderstanding:
        """Analyze a Russian legal query and return structured understanding."""
        q_lower = query.lower()

        # ── 1. Detect law aliases ────────────────────────────────────────
        law_ids = _detect_law_aliases(q_lower)

        # ── 2. Detect article reference ──────────────────────────────────
        article_num = _detect_article(query)

        # ── 3. Clean query (remove alias text for better embedding) ──────
        cleaned = _clean_query(query, q_lower)

        # ── 4. Detect topic ──────────────────────────────────────────────
        topic, topic_confidence = _detect_topic(q_lower)

        # ── 5. Resolve preferred law_ids ─────────────────────────────────
        if law_ids:
            preferred = list(law_ids)
        elif topic and topic_confidence >= _TOPIC_CONFIDENCE_THRESHOLD:
            preferred = list(_TOPIC_PREFERRED_LAWS.get(topic, []))
        else:
            preferred = []

        # ── 6. Determine query mode ──────────────────────────────────────
        mode = _determine_mode(law_ids, article_num, topic, topic_confidence)

        return RussianQueryUnderstanding(
            raw_query=query,
            cleaned_query=cleaned,
            detected_law_ids=law_ids,
            detected_article=article_num,
            detected_topic=topic,
            topic_confidence=topic_confidence,
            preferred_law_ids=preferred,
            query_mode=mode,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_law_aliases(q_lower: str) -> list[str]:
    """Detect law aliases in lowercased query. Longest match first, dedup."""
    seen: set[str] = set()
    result: list[str] = []
    for alias, law_id in _LAW_ALIASES:
        if alias in q_lower and law_id not in seen:
            seen.add(law_id)
            result.append(law_id)
    return result


def _detect_article(query: str) -> str | None:
    """Extract first article number from query if present."""
    m = _ARTICLE_RE.search(query)
    return m.group(1) if m else None


def _clean_query(raw_query: str, q_lower: str) -> str:
    """
    Remove law alias text and article references from query for cleaner embedding.

    Falls back to original query if cleaning produces empty string.
    """
    cleaned = raw_query
    # Remove article refs
    cleaned = _ARTICLE_RE.sub(" ", cleaned)
    # Remove law aliases (matched case-insensitively by replacing lowercased spans)
    for alias, _ in _LAW_ALIASES:
        # Find the span in the lowercased version and remove that range from cleaned
        start = 0
        while True:
            idx = q_lower.find(alias, start)
            if idx == -1:
                break
            # Replace in cleaned by positional slice (len matches because both are same string length)
            cleaned = cleaned[:idx] + " " * len(alias) + cleaned[idx + len(alias):]
            start = idx + len(alias)
    # Collapse whitespace
    result = " ".join(cleaned.split())
    return result if result.strip() else raw_query.strip()


def _detect_topic(q_lower: str) -> tuple[str | None, float]:
    """
    Detect dominant topic and confidence score.

    Returns (topic_id, score) where score is sum of matched signal weights.
    Returns (None, 0.0) if no topic scores above 0.
    """
    scores: dict[str, float] = {}

    for topic_id, phrase_weight, stem_weight, phrases, stems in _TOPIC_SIGNALS:
        score = 0.0
        # Phrase matching
        for phrase in phrases:
            if phrase in q_lower:
                score += phrase_weight
        # Stem prefix matching on space-split tokens
        tokens = q_lower.split()
        for token in tokens:
            for stem in stems:
                if token.startswith(stem):
                    score += stem_weight
                    break  # one stem match per token
        if score > 0:
            scores[topic_id] = score

    if not scores:
        return None, 0.0

    best_topic = max(scores, key=lambda t: scores[t])
    best_score = scores[best_topic]

    # Require separation from second-best to avoid ambiguity
    second_score = sorted(scores.values(), reverse=True)[1] if len(scores) > 1 else 0.0
    if best_score <= second_score and len(scores) > 1:
        return None, 0.0

    return best_topic, best_score


def _determine_mode(
    law_ids: list[str],
    article_num: str | None,
    topic: str | None,
    topic_confidence: float,
) -> str:
    if law_ids and article_num:
        return "exact_lookup"
    if law_ids:
        return "law_constrained_search"
    if topic and topic_confidence >= _TOPIC_CONFIDENCE_THRESHOLD:
        return "topic_search"
    return "broad_search"
