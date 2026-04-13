"""Deterministic legal taxonomy helpers for retrieval scaffolding."""

from app.modules.common.legal_taxonomy.russia_focus_taxonomy import RUSSIA_FOCUS_DATASET
from app.modules.common.legal_taxonomy.schemas import (
    ArticleTaxonomyItem,
    FocusTaxonomyDataset,
    LawTaxonomyItem,
)
from app.modules.common.legal_taxonomy.service import (
    FocusLegalTaxonomyService,
    get_russia_focus_taxonomy_service,
)

__all__ = [
    "ArticleTaxonomyItem",
    "FocusLegalTaxonomyService",
    "FocusTaxonomyDataset",
    "LawTaxonomyItem",
    "RUSSIA_FOCUS_DATASET",
    "get_russia_focus_taxonomy_service",
]
