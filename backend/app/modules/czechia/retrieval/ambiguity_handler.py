from __future__ import annotations

from typing import Dict, List, Optional

IMPORTANT_LAWS = [
    {"law_iri": "local:sb/2006/262", "name": "zákoník práce"},
    {"law_iri": "local:sb/2012/89", "name": "občanský zákoník"},
    {"law_iri": "local:sb/2009/40", "name": "trestní zákoník"},
]

LEGAL_KEYWORDS = [
    "výpověď",
    "zaměstnavatel",
    "smlouva",
    "trest",
    "odpovědnost",
    "pracovní",
]


class AmbiguityResult:
    def __init__(self, needs_clarification: bool, message: str, suggestions: List[Dict]):
        self.needs_clarification = needs_clarification
        self.message = message
        self.suggestions = suggestions


class CzechAmbiguityHandler:
    def evaluate(
        self,
        query: str,
        paragraph: Optional[int],
        law_id: Optional[str],
        has_context: bool,
        context_law_hint: Optional[str],
    ) -> Optional[AmbiguityResult]:
        if paragraph is None:
            return None

        if law_id:
            return None

        normalized_query = query or ""
        text = normalized_query.lower()
        has_keywords = any(keyword in text for keyword in LEGAL_KEYWORDS)
        print("AMBIGUITY CHECK:", normalized_query, has_keywords)
        if has_keywords:
            return None

        if not has_context:
            return AmbiguityResult(
                needs_clarification=True,
                message="Dotaz je nejednoznačný. Uveď, o jaký zákon se jedná nebo popiš problém.",
                suggestions=self._default_suggestions(paragraph),
            )

        return AmbiguityResult(
            needs_clarification=True,
            message="Upřesni zákon. Na základě kontextu nabízím relevantní možnosti:",
            suggestions=self._context_suggestions(paragraph, context_law_hint),
        )

    def _default_suggestions(self, paragraph: int) -> List[Dict]:
        return [
            {
                "label": f"§ {paragraph} {law['name']}",
                "law_iri": law["law_iri"],
                "paragraph": paragraph,
            }
            for law in IMPORTANT_LAWS
        ]

    def _context_suggestions(self, paragraph: int, context_law_hint: Optional[str]) -> List[Dict]:
        ordered = IMPORTANT_LAWS.copy()

        if context_law_hint:
            ordered.sort(key=lambda law: law["law_iri"] != context_law_hint)

        return [
            {
                "label": f"§ {paragraph} {law['name']}",
                "law_iri": law["law_iri"],
                "paragraph": paragraph,
            }
            for law in ordered[:5]
        ]
