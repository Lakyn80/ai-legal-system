"""
Deterministic legal taxonomy schemas for retrieval-oriented mapping.

This module intentionally models only narrow, curated legal scope.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


AnchorPriority = Literal["core", "strong", "secondary", "peripheral"]
LegalRole = Literal[
    "primary_basis",
    "supporting_basis",
    "procedural_support",
    "enforcement_support",
]


class LawTaxonomyItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    law_id: str
    law_short: str
    law_full_name: str
    broad_domain: str
    supported_primary_topics: list[str] = Field(default_factory=list)
    supported_secondary_topics: list[str] = Field(default_factory=list)
    notes_for_retrieval: str = ""


class ArticleTaxonomyItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    law_id: str
    article_num: str
    article_heading: str
    short_topic_label: str
    detailed_topic_labels: list[str] = Field(default_factory=list)
    issue_flags: list[str] = Field(default_factory=list)
    retrieval_keywords_ru: list[str] = Field(default_factory=list)
    retrieval_keywords_cz: list[str] = Field(default_factory=list)
    anchor_priority: AnchorPriority
    legal_role: LegalRole
    summary_for_retrieval: str
    exclude_for_topics: list[str] = Field(default_factory=list)
    related_articles: list[str] = Field(default_factory=list)


class FocusTaxonomyDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    jurisdiction: str
    scope_notes: str
    laws: list[LawTaxonomyItem] = Field(default_factory=list)
    articles: list[ArticleTaxonomyItem] = Field(default_factory=list)
