from __future__ import annotations

import re

from app.modules.czechia.retrieval.schemas import (
    DetectedLawRef,
    DetectedDomain,
    QueryMode,
    QueryUnderstanding,
)
from app.modules.czechia.retrieval.text_utils import (
    collapse_whitespace,
    law_ref_to_iri,
    normalize_text,
    tokenize,
    unique_preserve,
)

_LAW_CITATION_RE = re.compile(
    r"(?:z[aá]kon(?:a|u|em|ě)?(?:\s+č\.?)?\s+)?(\d{1,4})\s*/\s*(\d{4})(?:\s+Sb\.?)?",
    re.IGNORECASE,
)
_PARAGRAPH_RE = re.compile(r"§+\s*(\d+[a-z]?)", re.IGNORECASE)

_LAW_NAME_ALIASES: dict[str, tuple[str, str]] = {
    "zakonik prace": ("262", "2006"),
    "obcansky zakonik": ("89", "2012"),
    "trestni zakonik": ("40", "2009"),
    "trestni rad": ("141", "1961"),
    "obcansky soudni rad": ("99", "1963"),
    "spravni rad": ("500", "2004"),
    "ustava ceske republiky": ("1", "1993"),
    "zakon o danich z prijmu": ("586", "1992"),
    "zakon o obchodnich korporacich": ("90", "2012"),
    "zakon o zvlastnich rizenich soudnich": ("292", "2013"),
}

_LAW_DOMAIN_MAP: dict[tuple[str, str], DetectedDomain] = {
    ("262", "2006"): "employment",
    ("89", "2012"): "civil",
    ("99", "1963"): "civil",
    ("292", "2013"): "civil",
    ("40", "2009"): "criminal",
    ("141", "1961"): "criminal",
    ("586", "1992"): "tax",
    ("500", "2004"): "administrative",
    ("1", "1993"): "constitutional",
    ("90", "2012"): "corporate",
}

_DOMAIN_SIGNAL_PHRASES: dict[DetectedDomain, dict[str, float]] = {
    "employment": {
        "pracovni pomer": 4.0,
        "vypoved z pracovniho pomeru": 6.0,
        "okamzite zruseni": 4.0,
        "zakonik prace": 5.0,
    },
    "civil": {
        "obcansky zakonik": 5.0,
        "najemni smlouva": 4.0,
        "kupni smlouva": 4.0,
        "nahrada skody": 4.0,
    },
    "criminal": {
        "trestni zakonik": 5.0,
        "trestni rad": 5.0,
        "trestny cin": 4.0,
        "trestni stihani": 4.0,
    },
    "tax": {
        "dan z prijmu": 5.0,
        "danove priznani": 4.0,
        "zakon o danich z prijmu": 5.0,
    },
    "administrative": {
        "spravni rizeni": 4.0,
        "spravni rad": 5.0,
        "spravni organ": 3.0,
    },
    "constitutional": {
        "ustava ceske republiky": 5.0,
        "ustavni poradek": 4.0,
        "zakladni prava": 4.0,
    },
    "corporate": {
        "obchodni korporace": 5.0,
        "spolecnost s rucenim omezenym": 4.0,
        "akciova spolecnost": 4.0,
    },
    "unknown": {},
}

_DOMAIN_SIGNAL_STEMS: dict[DetectedDomain, dict[str, float]] = {
    "employment": {
        "prac": 2.5,       # práci, práce, pracovat, pracovní — shorter stem covers inflections
        "pomer": 2.0,
        "zamestnan": 3.0,  # zaměstnanec/zaměstnanci — 100% employment specific
        "zamestnav": 3.0,  # zaměstnavatel/zaměstnavatele — 100% employment specific
        "vypoved": 3.5,
        "odstupn": 2.5,
        "dovolen": 3.0,    # dovolená/dovolené — employment specific (raised from 2.0)
        "mzda": 2.0,
        "zkusebn": 2.5,    # zkušební doba — probationary period in employment context
    },
    "civil": {
        "smlouv": 2.5,
        "najem": 2.5,
        "vlastnict": 2.5,
        "dedic": 2.0,
        "manzel": 2.0,
        "obcansk": 2.0,
        "zavaz": 3.0,      # závazek/závazky/závazná — obligation, clearly civil law
    },
    "criminal": {
        "trestn": 3.0,
        "obvin": 2.5,
        "obzal": 2.5,
        "delikt": 2.0,
        "zkusebn": 1.0,    # zkušební doba can also appear in criminal (conditional sentence), lower weight
    },
    "tax": {
        "dan": 2.0,
        "prijm": 2.5,
        "financn": 1.5,
    },
    "administrative": {
        "spravn": 3.0,
        "rizen": 1.5,
        "urad": 1.5,
    },
    "constitutional": {
        "ustav": 3.0,
        "zakladn": 1.5,
        "prav": 1.0,
    },
    "corporate": {
        "korporac": 3.0,
        "spolecnost": 2.0,
        "jednatel": 1.5,
        "valna": 1.5,
    },
    "unknown": {},
}

_STOPWORD_STEMS: tuple[str, ...] = (
    "zakon",
    "ustanov",
    "odstav",
    "pism",
    "podle",
    "nebo",
    "ktery",
    "ktera",
    "ktere",
    "cesk",
    "republik",
)


class CzechQueryAnalyzer:
    """Deterministic query understanding for Czech legal retrieval."""

    def analyze(self, query: str) -> QueryUnderstanding:
        normalized_query = normalize_text(query)
        law_refs = self._detect_law_refs(query, normalized_query)
        paragraphs = unique_preserve([match.group(1) for match in _PARAGRAPH_RE.finditer(query)])
        cleaned_query = self._clean_query(query, normalized_query)
        keywords = self._extract_keywords(cleaned_query)
        detected_domain, domain_confidence = self._detect_domain(
            normalized_query=normalized_query,
            keywords=keywords,
            law_refs=law_refs,
        )
        query_mode = self._determine_query_mode(law_refs, paragraphs, detected_domain)
        return QueryUnderstanding(
            raw_query=query,
            cleaned_query=cleaned_query,
            detected_law_refs=law_refs,
            detected_paragraphs=paragraphs,
            detected_domain=detected_domain,
            query_mode=query_mode,
            keywords=keywords,
            normalized_tokens=keywords,
            domain_confidence=domain_confidence,
        )

    def _detect_law_refs(self, raw_query: str, normalized_query: str) -> list[DetectedLawRef]:
        refs: list[DetectedLawRef] = []
        seen: set[str] = set()

        for match in _LAW_CITATION_RE.finditer(raw_query):
            number, year = match.group(1), match.group(2)
            law_iri = law_ref_to_iri(number, year)
            if law_iri in seen:
                continue
            seen.add(law_iri)
            refs.append(
                DetectedLawRef(
                    raw_ref=match.group(0),
                    law_number=number,
                    year=year,
                    law_iri=law_iri,
                )
            )

        for alias, (number, year) in _LAW_NAME_ALIASES.items():
            if alias not in normalized_query:
                continue
            law_iri = law_ref_to_iri(number, year)
            if law_iri in seen:
                continue
            seen.add(law_iri)
            refs.append(
                DetectedLawRef(
                    raw_ref=alias,
                    law_number=number,
                    year=year,
                    law_iri=law_iri,
                )
            )

        return refs

    def _clean_query(self, raw_query: str, normalized_query: str) -> str:
        cleaned = _LAW_CITATION_RE.sub(" ", raw_query)
        cleaned = _PARAGRAPH_RE.sub(" ", cleaned)
        collapsed = collapse_whitespace(cleaned)
        if collapsed:
            return collapsed
        return collapse_whitespace(raw_query)

    def _extract_keywords(self, cleaned_query: str) -> list[str]:
        keywords: list[str] = []
        for token in tokenize(cleaned_query):
            if any(token.startswith(stem) for stem in _STOPWORD_STEMS):
                continue
            if len(token) < 3:
                continue
            keywords.append(token)
        return unique_preserve(keywords)

    def _detect_domain(
        self,
        normalized_query: str,
        keywords: list[str],
        law_refs: list[DetectedLawRef],
    ) -> tuple[DetectedDomain, float]:
        scores: dict[DetectedDomain, float] = {
            "employment": 0.0,
            "civil": 0.0,
            "criminal": 0.0,
            "tax": 0.0,
            "administrative": 0.0,
            "constitutional": 0.0,
            "corporate": 0.0,
            "unknown": 0.0,
        }

        for domain, phrases in _DOMAIN_SIGNAL_PHRASES.items():
            for phrase, weight in phrases.items():
                if phrase in normalized_query:
                    scores[domain] += weight

        for domain, stems in _DOMAIN_SIGNAL_STEMS.items():
            for token in keywords:
                for stem, weight in stems.items():
                    if token.startswith(stem) or stem.startswith(token):
                        scores[domain] += weight
                        break

        for law_ref in law_refs:
            domain = _LAW_DOMAIN_MAP.get((law_ref.law_number, law_ref.year))
            if domain:
                scores[domain] += 5.0

        ranked = sorted(
            ((domain, score) for domain, score in scores.items() if domain != "unknown"),
            key=lambda item: item[1],
            reverse=True,
        )
        if not ranked or ranked[0][1] < 2.5:
            return "unknown", 0.0

        top_domain, top_score = ranked[0]
        next_score = ranked[1][1] if len(ranked) > 1 else 0.0
        confidence = top_score / max(top_score + next_score, 1.0)
        return top_domain, confidence

    @staticmethod
    def _determine_query_mode(
        law_refs: list[DetectedLawRef],
        paragraphs: list[str],
        detected_domain: DetectedDomain,
    ) -> QueryMode:
        if law_refs and paragraphs:
            return "exact_lookup"
        if law_refs:
            return "law_constrained_search"
        if detected_domain != "unknown":
            return "domain_search"
        return "broad_search"
