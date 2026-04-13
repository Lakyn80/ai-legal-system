"""
Lookup helpers for deterministic legal taxonomy usage in retrieval layers.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict

from app.modules.common.legal_taxonomy.russia_focus_taxonomy import RUSSIA_FOCUS_DATASET
from app.modules.common.legal_taxonomy.schemas import (
    ArticleTaxonomyItem,
    FocusTaxonomyDataset,
    LawTaxonomyItem,
)

_ISSUE_DETECTION_RULES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "interpreter_issue": (
        (
            "без переводчика",
            "не предоставили переводчика",
            "право на переводчика",
            "суд прошел без переводчика",
        ),
        ("переводч", "перевод "),
    ),
    "language_issue": (
        (
            "язык судопроизводства",
            "не владеет языком",
            "не понимал язык",
            "решение не перевели",
            "решение не перевели на мой язык",
            "документы суда не перевели на мой язык",
            "документы суда были только на русском",
        ),
        ("язык",),
    ),
    "notice_issue": (
        (
            "без уведомления",
            "не был уведомлен",
            "без извещения",
            "не получил повестку",
            "не получил извещение",
            "не получил извещение о заседании",
            "решение суда не было вручено",
            "решение мне не направили",
        ),
        ("извещ", "уведомл", "повестк", "вызов"),
    ),
    "service_address_issue": (
        (
            "по месту регистрации",
            "по адресу регистрации",
            "не проживал по адресу",
            "повестка была отправлена на адрес регистрации",
            "я там не проживал",
        ),
        ("регистрац", "адрес"),
    ),
    "foreign_party_issue": (
        ("иностранный гражданин", "иностранец", "турист", "нерезидент", "я был там только как турист"),
        ("иностран", "нерезидент"),
    ),
    "alimony_issue": (
        ("алименты", "взыскание алиментов", "содержание ребенка"),
        ("алимент",),
    ),
    "alimony_debt_issue": (
        ("задолженность по алиментам", "долг по алиментам", "расчет задолженности"),
        ("задолж", "долг"),
    ),
    "alimony_enforcement_issue": (
        ("исполнение алиментов", "взыскание долга по алиментам", "приставы"),
        ("пристав", "исполн"),
    ),
}

_ISSUE_TO_TOPICS: dict[str, tuple[str, ...]] = {
    "interpreter_issue": ("interpreter_rights", "language_of_proceedings"),
    "language_issue": ("language_of_proceedings",),
    "notice_issue": ("proper_notice_service",),
    "service_address_issue": ("service_mechanics",),
    "foreign_party_issue": ("foreign_party_status_support",),
    "alimony_issue": ("alimony", "alimony_obligation"),
    "alimony_debt_issue": ("alimony_debt",),
    "alimony_enforcement_issue": ("enforcement_support", "alimony_debt"),
}


@dataclass(frozen=True)
class TaxonomyCandidateSet:
    issue_flags: list[str]
    candidate_articles: list[ArticleTaxonomyItem]
    candidate_article_keys: set[tuple[str, str]]
    candidate_laws: set[str]
    topic_hints: list[str]


class FocusLegalTaxonomyService:
    """In-memory deterministic lookup service over a curated taxonomy dataset."""

    def __init__(self, dataset: FocusTaxonomyDataset) -> None:
        self._dataset = dataset
        self._laws_by_id: dict[str, LawTaxonomyItem] = {l.law_id: l for l in dataset.laws}
        self._articles_by_key: dict[tuple[str, str], ArticleTaxonomyItem] = {
            (a.law_id, a.article_num): a for a in dataset.articles
        }
        self._articles_by_issue: dict[str, list[ArticleTaxonomyItem]] = defaultdict(list)
        self._articles_by_topic: dict[str, list[ArticleTaxonomyItem]] = defaultdict(list)
        self._excluded_laws_by_topic: dict[str, set[str]] = defaultdict(set)
        for article in dataset.articles:
            for issue in article.issue_flags:
                self._articles_by_issue[issue].append(article)
            for topic in article.detailed_topic_labels:
                self._articles_by_topic[topic].append(article)
            for excluded_topic in article.exclude_for_topics:
                # Exclusion hints are applied at law-level during ranking filters.
                self._excluded_laws_by_topic[excluded_topic].add(article.law_id)

    @property
    def dataset(self) -> FocusTaxonomyDataset:
        return self._dataset

    def get_law(self, law_id: str) -> LawTaxonomyItem | None:
        return self._laws_by_id.get(law_id)

    def get_article(self, law_id: str, article_num: str) -> ArticleTaxonomyItem | None:
        return self._articles_by_key.get((law_id, article_num))

    def get_articles_for_issue(self, issue_flag: str) -> list[ArticleTaxonomyItem]:
        rows = list(self._articles_by_issue.get(issue_flag, []))
        return _sort_articles(rows)

    def get_anchor_articles_for_topic(self, topic: str) -> list[ArticleTaxonomyItem]:
        rows = [a for a in self._articles_by_topic.get(topic, []) if a.anchor_priority in {"core", "strong"}]
        return _sort_articles(rows)

    def get_law_priority_for_topic(self, topic: str) -> dict[str, int]:
        """
        Return deterministic per-law score hints for ranking filters.
        Higher means stronger priority.
        """
        weights = {"core": 100, "strong": 70, "secondary": 40, "peripheral": 10}
        score: dict[str, int] = defaultdict(int)
        for article in self._articles_by_topic.get(topic, []):
            score[article.law_id] += weights[article.anchor_priority]
        return dict(sorted(score.items(), key=lambda x: (-x[1], x[0])))

    def get_excluded_laws_for_topic(self, topic: str) -> list[str]:
        return sorted(self._excluded_laws_by_topic.get(topic, set()))

    def get_topic_to_anchor_articles(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for topic, rows in self._articles_by_topic.items():
            anchors = [f"{a.law_id}:{a.article_num}" for a in _sort_articles(rows) if a.anchor_priority in {"core", "strong"}]
            if anchors:
                out[topic] = anchors
        return out

    def get_issue_to_candidate_articles(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for issue, rows in self._articles_by_issue.items():
            out[issue] = [f"{a.law_id}:{a.article_num}" for a in _sort_articles(rows)]
        return out

    def get_topics_for_issue(self, issue_flag: str) -> list[str]:
        return list(_ISSUE_TO_TOPICS.get(issue_flag, ()))

    def detect_issue_flags(self, query: str) -> list[str]:
        """Simple deterministic issue detection from raw query text."""
        q = query.lower()
        out: list[str] = []
        for issue, (phrases, stems) in _ISSUE_DETECTION_RULES.items():
            phrase_hit = any(p in q for p in phrases)
            stem_hit = any(token.startswith(stem) for token in q.split() for stem in stems)
            if phrase_hit or stem_hit:
                out.append(issue)
        return out

    def build_candidates_for_query(self, query: str) -> TaxonomyCandidateSet:
        issue_flags = self.detect_issue_flags(query)
        rows: list[ArticleTaxonomyItem] = []
        seen: set[tuple[str, str]] = set()
        topic_hints: list[str] = []

        for issue in issue_flags:
            for topic in _ISSUE_TO_TOPICS.get(issue, ()):
                if topic not in topic_hints:
                    topic_hints.append(topic)
            for row in self.get_articles_for_issue(issue):
                key = (row.law_id, row.article_num)
                if key not in seen:
                    seen.add(key)
                    rows.append(row)

        return TaxonomyCandidateSet(
            issue_flags=issue_flags,
            candidate_articles=_sort_articles(rows),
            candidate_article_keys=seen,
            candidate_laws={r.law_id for r in rows},
            topic_hints=topic_hints,
        )


def _sort_articles(rows: list[ArticleTaxonomyItem]) -> list[ArticleTaxonomyItem]:
    priority_order = {"core": 0, "strong": 1, "secondary": 2, "peripheral": 3}
    return sorted(rows, key=lambda a: (priority_order[a.anchor_priority], a.law_id, a.article_num))


def get_russia_focus_taxonomy_service() -> FocusLegalTaxonomyService:
    """Factory kept simple for dependency wiring later."""
    return FocusLegalTaxonomyService(RUSSIA_FOCUS_DATASET)
