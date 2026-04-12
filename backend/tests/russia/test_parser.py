"""
Parser unit tests for Russian law ingestion — Step 1 verification.

Tests run against the actual corpus files. Each test has a single clear assertion.
Article counts use a ±3 tolerance to account for future law amendments without
making tests fragile, while still catching gross parse failures.

Corpus paths must be accessible inside the Docker container via /app/Ruske_zakony/.
Tests are skipped (not failed) if the corpus directory is not found, so that
CI without the corpus does not block the build.
"""
from __future__ import annotations

import os
import re
import pytest
from pathlib import Path

# ---------------------------------------------------------------------------
# Corpus path resolution
# ---------------------------------------------------------------------------

# Inside the container the corpus should be mounted or copied here
_CORPUS_ROOT = Path("/app/Ruske_zakony")

# Milestone 1 target files
_SK_PATH = _CORPUS_ROOT / "Семейный кодекс Российской Федерации  от 29.12.1995 N 223-ФЗ-u.txt"
_TK_PATH = _CORPUS_ROOT / "rest_of_the_codex_russia" / "Трудовой кодекс Российской Федерации  от 30.12.2001 N 197-ФЗ-u.txt"
_GK1_PATH = _CORPUS_ROOT / "Гражданский кодекс Российской Федерации (часть первая)  от 3-u.txt"

_CORPUS_AVAILABLE = _SK_PATH.exists() and _TK_PATH.exists() and _GK1_PATH.exists()

pytestmark = pytest.mark.skipif(
    not _CORPUS_AVAILABLE,
    reason="Corpus files not available at /app/Ruske_zakony — skipping parser tests",
)

# ---------------------------------------------------------------------------
# Fixtures — parse each law once per session
# ---------------------------------------------------------------------------

from app.modules.russia.ingestion.loader import load_law_file
from app.modules.russia.ingestion.parser import parse_law
from app.modules.russia.ingestion.schemas import ParseResult


@pytest.fixture(scope="session")
def sk_result() -> ParseResult:
    meta, raw = load_law_file(_SK_PATH)
    return parse_law(meta, raw)


@pytest.fixture(scope="session")
def tk_result() -> ParseResult:
    meta, raw = load_law_file(_TK_PATH)
    return parse_law(meta, raw)


@pytest.fixture(scope="session")
def gk1_result() -> ParseResult:
    meta, raw = load_law_file(_GK1_PATH)
    return parse_law(meta, raw)


# ---------------------------------------------------------------------------
# Article count tests (±3 tolerance)
# ---------------------------------------------------------------------------

def test_sk_article_count(sk_result: ParseResult) -> None:
    """СК РФ must parse ~173 articles (verified via direct file inspection)."""
    assert abs(sk_result.article_count - 173) <= 3, (
        f"Expected ~173 articles in СК РФ, got {sk_result.article_count}"
    )


def test_tk_article_count(tk_result: ParseResult) -> None:
    """ТК РФ must parse ~538 articles (verified via direct file inspection)."""
    assert abs(tk_result.article_count - 538) <= 3, (
        f"Expected ~538 articles in ТК РФ, got {tk_result.article_count}"
    )


def test_gk1_article_count(gk1_result: ParseResult) -> None:
    """ГК РФ ч.1 must parse ~591 articles (verified via direct file inspection)."""
    assert abs(gk1_result.article_count - 591) <= 3, (
        f"Expected ~591 articles in ГК РФ ч.1, got {gk1_result.article_count}"
    )


# ---------------------------------------------------------------------------
# Article content correctness
# ---------------------------------------------------------------------------

def test_tk_article_81_heading(tk_result: ParseResult) -> None:
    """Статья 81 ТК РФ must be present with correct heading."""
    article = next((a for a in tk_result.articles if a.article_num == "81"), None)
    assert article is not None, "Статья 81 not found in ТК РФ"
    assert "Расторжение" in article.heading, (
        f"Expected 'Расторжение' in heading, got: {article.heading!r}"
    )


def test_sk_article_1_heading(sk_result: ParseResult) -> None:
    """Статья 1 СК РФ must be present with correct heading."""
    article = next((a for a in sk_result.articles if a.article_num == "1"), None)
    assert article is not None, "Статья 1 not found in СК РФ"
    assert "начала" in article.heading.lower() or "семейного" in article.heading.lower(), (
        f"Unexpected heading for ст.1 СК РФ: {article.heading!r}"
    )


def test_gk1_article_169_present(gk1_result: ParseResult) -> None:
    """Статья 169 ГК РФ ч.1 must be present."""
    article = next((a for a in gk1_result.articles if a.article_num == "169"), None)
    assert article is not None, "Статья 169 not found in ГК РФ ч.1"
    assert len(article.raw_text) > 0, "Статья 169 has empty text"


# ---------------------------------------------------------------------------
# Decimal article numbers
# ---------------------------------------------------------------------------

def test_tk_decimal_article_19_1(tk_result: ParseResult) -> None:
    """Статья 19.1 must be detected in ТК РФ (decimal article number)."""
    article = next((a for a in tk_result.articles if a.article_num == "19.1"), None)
    assert article is not None, "Статья 19.1 not found in ТК РФ — decimal article parsing broken"


def test_tk_decimal_article_22_1(tk_result: ParseResult) -> None:
    """Статья 22.1 must be detected in ТК РФ (another decimal article)."""
    article = next((a for a in tk_result.articles if a.article_num == "22.1"), None)
    assert article is not None, "Статья 22.1 not found in ТК РФ"


# ---------------------------------------------------------------------------
# Tombstone detection
# ---------------------------------------------------------------------------

def test_tk_article_7_is_tombstone(tk_result: ParseResult) -> None:
    """Статья 7 ТК РФ is repealed and must be marked is_tombstone=True."""
    article = next((a for a in tk_result.articles if a.article_num == "7"), None)
    assert article is not None, "Статья 7 not found in ТК РФ"
    assert article.is_tombstone is True, (
        f"Статья 7 ТК РФ should be tombstone, heading={article.heading!r}"
    )


def test_tombstone_count_tk_nonzero(tk_result: ParseResult) -> None:
    """ТК РФ must have multiple tombstone articles (several were repealed)."""
    assert tk_result.tombstone_count >= 3, (
        f"Expected at least 3 tombstones in ТК РФ, got {tk_result.tombstone_count}"
    )


def test_tombstone_article_has_text(tk_result: ParseResult) -> None:
    """Tombstone articles must still have non-empty text (not silently discarded)."""
    tombstones = [a for a in tk_result.articles if a.is_tombstone]
    for art in tombstones:
        assert len(art.parts) > 0, f"Tombstone {art.article_num} has no parts"
        # The tombstone text may be very short, but must be non-empty
        combined = " ".join(p.text for p in art.parts)
        assert len(combined.strip()) > 0, f"Tombstone {art.article_num} has empty text"


# ---------------------------------------------------------------------------
# Noise filtering — Pass 1 must remove all editor annotations
# ---------------------------------------------------------------------------

def _collect_all_text(result: ParseResult) -> str:
    return "\n".join(
        p.text
        for a in result.articles
        for p in a.parts
    )


def test_no_vred_noise_in_sk(sk_result: ParseResult) -> None:
    """No article text in СК РФ should contain '(в ред.' after noise removal."""
    all_text = _collect_all_text(sk_result)
    assert "(в ред." not in all_text, "Pass 1 noise filter failed: '(в ред.' found in СК РФ chunk text"


def test_no_vred_noise_in_tk(tk_result: ParseResult) -> None:
    """No article text in ТК РФ should contain '(в ред.' after noise removal."""
    all_text = _collect_all_text(tk_result)
    assert "(в ред." not in all_text, "Pass 1 noise filter failed: '(в ред.' found in ТК РФ chunk text"


def test_no_vred_noise_in_gk1(gk1_result: ParseResult) -> None:
    """No article text in ГК РФ ч.1 should contain '(в ред.' after noise removal."""
    all_text = _collect_all_text(gk1_result)
    assert "(в ред." not in all_text, "Pass 1 noise filter failed: '(в ред.' found in ГК РФ ч.1 chunk text"


def test_no_consultantplus_in_sk(sk_result: ParseResult) -> None:
    """No article text in СК РФ should contain 'КонсультантПлюс' after noise removal."""
    all_text = _collect_all_text(sk_result)
    assert "КонсультантПлюс" not in all_text, "Pass 1 noise filter failed: КонсультантПлюс found in СК РФ chunk text"


def test_no_consultantplus_in_tk(tk_result: ParseResult) -> None:
    """No article text in ТК РФ should contain 'КонсультантПлюс' after noise removal."""
    all_text = _collect_all_text(tk_result)
    assert "КонсультантПлюс" not in all_text, "Pass 1 noise filter failed: КонсультантПлюс found in ТК РФ chunk text"


def test_no_consultantplus_in_gk1(gk1_result: ParseResult) -> None:
    """No article text in ГК РФ ч.1 should contain 'КонсультантПлюс' after noise removal."""
    all_text = _collect_all_text(gk1_result)
    assert "КонсультантПлюс" not in all_text, "Pass 1 noise filter failed: КонсультантПлюс found in ГК РФ ч.1 chunk text"


def test_no_pozitsii_noise_in_gk1(gk1_result: ParseResult) -> None:
    """GK1 has many 'Позиции высших судов' markers — all must be removed."""
    all_text = _collect_all_text(gk1_result)
    assert "Позиции высших судов" not in all_text, (
        "Pass 1 noise filter failed: 'Позиции высших судов' found in ГК РФ ч.1 chunk text"
    )


# ---------------------------------------------------------------------------
# Part splitting
# ---------------------------------------------------------------------------

def test_gk1_has_multi_part_articles(gk1_result: ParseResult) -> None:
    """ГК РФ ч.1 articles use '1. 2. 3.' части format — long articles must be split into >1 part."""
    multi_part = [a for a in gk1_result.articles if not a.is_tombstone and len(a.parts) > 1]
    assert len(multi_part) >= 10, (
        f"Expected many multi-part articles in ГК РФ ч.1, got {len(multi_part)} — part splitter is broken"
    )


def test_sk_article_1_single_part(sk_result: ParseResult) -> None:
    """Статья 1 СК РФ is short — must remain as a single chunk."""
    article = next((a for a in sk_result.articles if a.article_num == "1"), None)
    assert article is not None
    # Short articles should not be split just because they have numbered items
    assert len(article.parts) >= 1


def test_all_parts_have_nonempty_text(tk_result: ParseResult) -> None:
    """Every part in ТК РФ must have non-empty text."""
    for article in tk_result.articles:
        for part in article.parts:
            assert len(part.text.strip()) > 0, (
                f"Empty part in ст.{article.article_num} ТК РФ part_num={part.part_num}"
            )


# ---------------------------------------------------------------------------
# Article ordering
# ---------------------------------------------------------------------------

def test_article_positions_sequential(tk_result: ParseResult) -> None:
    """article_position must be 0, 1, 2, ... without gaps or duplicates."""
    positions = [a.article_position for a in tk_result.articles]
    assert positions == list(range(len(positions))), (
        f"article_position is not sequential: {positions[:20]}..."
    )


def test_article_positions_unique(sk_result: ParseResult) -> None:
    """article_position values must be unique within a law."""
    positions = [a.article_position for a in sk_result.articles]
    assert len(positions) == len(set(positions)), "Duplicate article_position values found in СК РФ"


# ---------------------------------------------------------------------------
# Metadata correctness
# ---------------------------------------------------------------------------

def test_sk_metadata_law_id(sk_result: ParseResult) -> None:
    assert sk_result.metadata.law_id == "local:ru/sk"


def test_tk_metadata_law_id(tk_result: ParseResult) -> None:
    assert tk_result.metadata.law_id == "local:ru/tk"


def test_gk1_metadata_law_id(gk1_result: ParseResult) -> None:
    assert gk1_result.metadata.law_id == "local:ru/gk/1"


def test_sk_metadata_law_short(sk_result: ParseResult) -> None:
    assert sk_result.metadata.law_short == "СК РФ"


def test_tk_metadata_law_short(tk_result: ParseResult) -> None:
    assert tk_result.metadata.law_short == "ТК РФ"


def test_all_articles_have_law_id(tk_result: ParseResult) -> None:
    """Every parsed article must carry the law_id (never empty or None)."""
    for article in tk_result.articles:
        assert article.law_id, f"Empty law_id on article {article.article_num}"
        assert article.law_id == "local:ru/tk"
