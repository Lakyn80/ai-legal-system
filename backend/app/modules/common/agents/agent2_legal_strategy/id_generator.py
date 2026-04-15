"""
Deterministic, human-readable ID generator for Agent 2 extraction output.

IDs are:
- deterministic — same inputs always produce same ID
- repeatable — stable across runs and deployments
- readable — understandable by humans in PowerShell / FE queries
- searchable — greppable by case_id, group, doc index, issue slug

Format:
    case::<case_id>::group::<group_name>
    case::<case_id>::doc::<logical_index>
    case::<case_id>::issue::<issue_slug>
    case::<case_id>::defense::<issue_slug>
"""
from __future__ import annotations

import re


def _safe_slug(text: str, max_len: int = 64) -> str:
    """Convert arbitrary text to a stable, URL-safe slug."""
    s = text.lower().strip()
    # Replace anything that isn't alphanumeric or underscore with underscore
    s = re.sub(r"[^a-z0-9_]", "_", s)
    # Collapse runs of underscores
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:max_len] or "unknown"


def make_group_id(case_id: str, group_name: str) -> str:
    """
    Stable ID for a document group.

    Example:
        case::2f393699-ebaa-4c79-b84c-ad9af75d0bcf::group::judgments
    """
    return f"case::{case_id}::group::{_safe_slug(group_name)}"


def make_doc_id(
    case_id: str,
    logical_index: int,
    primary_doc_id: str = "",
) -> str:
    """
    Stable ID for a document within a group.

    Prefers primary_doc_id (upstream ID) when available for stronger stability.
    Falls back to logical_index (0-based) within the group.

    Examples:
        case::2f393699::doc::court_judgment_2024_03_15
        case::2f393699::doc::0
    """
    if primary_doc_id:
        return f"case::{case_id}::doc::{_safe_slug(primary_doc_id)}"
    return f"case::{case_id}::doc::{logical_index}"


def make_issue_id(case_id: str, issue_slug: str) -> str:
    """
    Stable ID for a legal issue.

    Example:
        case::2f393699-ebaa-4c79-b84c-ad9af75d0bcf::issue::service_abroad
    """
    return f"case::{case_id}::issue::{_safe_slug(issue_slug)}"


def make_defense_id(case_id: str, issue_slug: str) -> str:
    """
    Stable ID for a defense block tied to a legal issue.

    Example:
        case::2f393699-ebaa-4c79-b84c-ad9af75d0bcf::defense::service_abroad
    """
    return f"case::{case_id}::defense::{_safe_slug(issue_slug)}"
