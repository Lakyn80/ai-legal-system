from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.core.enums import CountryEnum, DomainEnum
from app.modules.common.qdrant.schemas import SearchResultItem
from app.modules.czechia.retrieval.query_analyzer import CzechQueryAnalyzer
from app.modules.czechia.retrieval.schemas import QueryUnderstanding
from app.modules.czechia.retrieval.text_utils import normalize_text, tokenize

LABOR_LAW_IRI = "local:sb/2006/262"

NON_LEGAL_FALLBACK = (
    "Váš dotaz se netýká právní problematiky. "
    "Ptejte se prosím na relevantní otázky ze zákoníku práce nebo pracovního práva."
)
LEGAL_OUT_OF_SCOPE_FALLBACK = (
    "Dotaz je právní, ale netýká se zákoníku práce ani pracovněprávní oblasti. "
    "Ptejte se prosím na témata související se zaměstnáním, pracovním poměrem, "
    "výpovědí, mzdou, dovolenou nebo pracovní dobou."
)
AMBIGUOUS_FALLBACK = (
    "Dotaz je příliš obecný. Upřesněte prosím, že jde o zákoník práce, "
    "nebo popište pracovní situaci."
)

LaborGateBucket = Literal["non_legal", "legal_out_of_scope", "ambiguous", "labor_in_domain"]

_AMBIGUOUS_EMPLOYMENT_PHRASES = {
    "vypoved",
    "narok",
    "mzda",
    "dovolena",
}
_LABOR_HINT_PHRASES = {
    "zakonik prace",
    "pracovni pomer",
    "vypovedni doba",
    "okamzite zruseni",
    "zkusebni doba",
    "pracovni smlouva",
    "odstupne",
    "dovolena",
    "pracovni doba",
    "prestavka v praci",
}
_OTHER_LEGAL_PHRASES = {
    "kupni smlouva",
    "najemni smlouva",
    "obcansky zakonik",
    "trestni zakonik",
    "spravni rizeni",
    "spravni rad",
    "danove priznani",
    "dan z prijmu",
    "vrazda",
    "rozvod",
    "dedicke rizeni",
    "nahrada skody",
    "obchodni korporace",
    "akciova spolecnost",
}
_GENERIC_LEGAL_STEMS = (
    "zakon",
    "zakonik",
    "paragraf",
    "ustanov",
    "odstav",
    "pism",
    "prac",
    "zamestnan",
    "zamestnav",
    "vypoved",
    "odstupn",
    "dovolen",
    "mzda",
    "narok",
    "smlouv",
    "trestn",
    "vrazd",
    "spravn",
    "dan",
    "priznan",
    "rozvod",
    "obcansk",
    "najem",
    "dedic",
    "skod",
    "korporac",
)
_OTHER_LEGAL_STEMS = (
    "smlouv",
    "trestn",
    "vrazd",
    "spravn",
    "dan",
    "priznan",
    "rozvod",
    "obcansk",
    "najem",
    "dedic",
    "skod",
    "korporac",
)
_EMPLOYMENT_STEMS = (
    "prac",
    "zamestnan",
    "zamestnav",
    "vypoved",
    "odstupn",
    "dovolen",
    "mzda",
    "zkusebn",
    "prestav",
)


@dataclass(slots=True)
class LaborGateDecision:
    bucket: LaborGateBucket
    message: str
    reason_codes: list[str] = field(default_factory=list)
    understanding: QueryUnderstanding | None = None
    explicit_labor_law: bool = False

    @property
    def allows_retrieval(self) -> bool:
        return self.bucket == "labor_in_domain"

    def to_search_result(self) -> SearchResultItem:
        source_type = "clarification" if self.bucket == "ambiguous" else "system_fallback"
        filename = {
            "non_legal": "Mimo právní oblast",
            "legal_out_of_scope": "Mimo zákoník práce",
            "ambiguous": "Upřesnění dotazu",
            "labor_in_domain": "Zákoník práce",
        }[self.bucket]
        return SearchResultItem(
            chunk_id=f"labor_gate:{self.bucket}",
            document_id="",
            filename=filename,
            country=CountryEnum.CZECHIA,
            domain=DomainEnum.LAW,
            jurisdiction_module="czechia",
            text=self.message,
            chunk_index=0,
            source_type=source_type,
            source="labor_gate",
            case_id=None,
            tags=["labor_gate", self.bucket],
            score=1.0,
        )


class LaborGate:
    """Hard pre-retrieval gate for the labor-only Czech-law vertical."""

    def __init__(self, analyzer: CzechQueryAnalyzer | None = None) -> None:
        self._analyzer = analyzer or CzechQueryAnalyzer()

    def evaluate(
        self,
        query: str,
        *,
        understanding: QueryUnderstanding | None = None,
    ) -> LaborGateDecision:
        analysis = understanding or self._analyzer.analyze(query)
        normalized_query = normalize_text(query)
        raw_tokens = tokenize(query)
        explicit_labor_law = self._is_explicit_labor_law_ref(normalized_query, analysis)
        explicit_other_law = bool(analysis.detected_law_refs) and not explicit_labor_law
        has_paragraph = bool(analysis.detected_paragraphs)
        token_count = len(raw_tokens)

        if explicit_other_law:
            return LaborGateDecision(
                bucket="legal_out_of_scope",
                message=LEGAL_OUT_OF_SCOPE_FALLBACK,
                reason_codes=["explicit_other_law_ref"],
                understanding=analysis,
                explicit_labor_law=False,
            )

        if explicit_labor_law:
            return LaborGateDecision(
                bucket="labor_in_domain",
                message="",
                reason_codes=["explicit_labor_law_ref"],
                understanding=analysis,
                explicit_labor_law=True,
            )

        if has_paragraph:
            return LaborGateDecision(
                bucket="ambiguous",
                message=AMBIGUOUS_FALLBACK,
                reason_codes=["bare_paragraph_reference"],
                understanding=analysis,
                explicit_labor_law=False,
            )

        if self._is_ambiguous_employment_query(normalized_query, raw_tokens, analysis):
            return LaborGateDecision(
                bucket="ambiguous",
                message=AMBIGUOUS_FALLBACK,
                reason_codes=["generic_employment_query"],
                understanding=analysis,
                explicit_labor_law=False,
            )

        if analysis.detected_domain == "employment":
            return LaborGateDecision(
                bucket="labor_in_domain",
                message="",
                reason_codes=["employment_domain_signal"],
                understanding=analysis,
                explicit_labor_law=False,
            )

        if analysis.detected_domain != "unknown":
            return LaborGateDecision(
                bucket="legal_out_of_scope",
                message=LEGAL_OUT_OF_SCOPE_FALLBACK,
                reason_codes=[f"detected_domain:{analysis.detected_domain}"],
                understanding=analysis,
                explicit_labor_law=False,
            )

        if self._contains_other_legal_signal(normalized_query, raw_tokens):
            return LaborGateDecision(
                bucket="legal_out_of_scope",
                message=LEGAL_OUT_OF_SCOPE_FALLBACK,
                reason_codes=["other_legal_signal"],
                understanding=analysis,
                explicit_labor_law=False,
            )

        if self._contains_any_legal_signal(normalized_query, raw_tokens):
            reason_code = "generic_legal_signal" if token_count <= 2 else "weak_legal_signal"
            bucket: LaborGateBucket = "ambiguous" if token_count <= 2 else "legal_out_of_scope"
            message = AMBIGUOUS_FALLBACK if bucket == "ambiguous" else LEGAL_OUT_OF_SCOPE_FALLBACK
            return LaborGateDecision(
                bucket=bucket,
                message=message,
                reason_codes=[reason_code],
                understanding=analysis,
                explicit_labor_law=False,
            )

        return LaborGateDecision(
            bucket="non_legal",
            message=NON_LEGAL_FALLBACK,
            reason_codes=["non_legal_query"],
            understanding=analysis,
            explicit_labor_law=False,
        )

    @staticmethod
    def _is_explicit_labor_law_ref(normalized_query: str, understanding: QueryUnderstanding) -> bool:
        if any(ref.law_iri == LABOR_LAW_IRI for ref in understanding.detected_law_refs):
            return True
        if "zakonik prace" in normalized_query:
            return True
        if "262/2006" in normalized_query:
            return True
        tokens = set(tokenize(normalized_query))
        return "zp" in tokens

    @staticmethod
    def _is_ambiguous_employment_query(
        normalized_query: str,
        raw_tokens: list[str],
        understanding: QueryUnderstanding,
    ) -> bool:
        if normalized_query in _AMBIGUOUS_EMPLOYMENT_PHRASES:
            return True
        if understanding.detected_domain != "employment":
            return False
        if any(phrase in normalized_query for phrase in _LABOR_HINT_PHRASES):
            return False
        if len(raw_tokens) <= 2 and all(
            any(token.startswith(stem) for stem in _EMPLOYMENT_STEMS)
            for token in raw_tokens
        ):
            return True
        return False

    @staticmethod
    def _contains_other_legal_signal(normalized_query: str, raw_tokens: list[str]) -> bool:
        if any(phrase in normalized_query for phrase in _OTHER_LEGAL_PHRASES):
            return True
        return any(
            any(token.startswith(stem) for stem in _OTHER_LEGAL_STEMS)
            for token in raw_tokens
        )

    @staticmethod
    def _contains_any_legal_signal(normalized_query: str, raw_tokens: list[str]) -> bool:
        if any(phrase in normalized_query for phrase in _LABOR_HINT_PHRASES):
            return True
        if any(phrase in normalized_query for phrase in _OTHER_LEGAL_PHRASES):
            return True
        return any(
            any(token.startswith(stem) for stem in _GENERIC_LEGAL_STEMS)
            for token in raw_tokens
        )
