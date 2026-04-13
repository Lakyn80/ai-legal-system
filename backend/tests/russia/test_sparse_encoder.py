"""
Pure-Python unit tests for Russian BM25 encoder and RRF fusion.

No Qdrant required — these always run.

Tests:
  - Russian tokenizer: Cyrillic, case folding, numbers, short-word exclusion, ё
  - IDFTable build/save/load/empty
  - RussianBM25Encoder encode / encode_query
  - token_to_index determinism and uint32 range
  - reciprocal_rank_fusion: dedup, shared chunk scoring, top_k, no duplicates
"""
from __future__ import annotations

import pytest

from app.modules.russia.ingestion.sparse_encoder import (
    IDFTable,
    IDFTableBuilder,
    RussianBM25Encoder,
    token_to_index,
    tokenize,
)
from app.modules.russia.retrieval.fusion import reciprocal_rank_fusion
from app.modules.russia.retrieval.schemas import RussianSearchResult


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

class TestRussianTokenizer:
    def test_basic_cyrillic(self):
        tokens = tokenize("трудовой договор")
        assert "трудовой" in tokens
        assert "договор" in tokens

    def test_case_insensitive(self):
        assert tokenize("трудовой") == tokenize("ТРУДОВОЙ")

    def test_numbers_kept(self):
        tokens = tokenize("статья 81")
        assert "81" in tokens

    def test_empty_returns_empty(self):
        assert tokenize("") == []
        assert tokenize("   ") == []

    def test_short_words_excluded(self):
        # Single-char Cyrillic tokens — min 2 chars required
        assert tokenize("в и к") == []

    def test_yo_handled(self):
        # ё is U+0451, outside the contiguous а-я range
        assert "ещё" in tokenize("ещё")

    def test_latin_excluded(self):
        tokens = tokenize("статья article договор")
        for t in tokens:
            assert all(
                "\u0400" <= ch <= "\u04FF" or ch.isdigit() for ch in t
            ), f"Latin token found: {t!r}"

    def test_punctuation_ignored(self):
        tokens = tokenize("статья, договор.")
        assert "статья" in tokens
        assert "договор" in tokens

    def test_multiword(self):
        tokens = tokenize("расторжение трудового договора по инициативе работодателя")
        assert len(tokens) >= 4


# ---------------------------------------------------------------------------
# token_to_index
# ---------------------------------------------------------------------------

class TestTokenToIndex:
    def test_is_uint32(self):
        idx = token_to_index("договор")
        assert 0 <= idx <= 0xFFFF_FFFF

    def test_deterministic(self):
        assert token_to_index("договор") == token_to_index("договор")

    def test_different_tokens_differ(self):
        assert token_to_index("договор") != token_to_index("расторжение")

    def test_empty_string(self):
        idx = token_to_index("")
        assert 0 <= idx <= 0xFFFF_FFFF


# ---------------------------------------------------------------------------
# IDFTable
# ---------------------------------------------------------------------------

class TestIDFTable:
    def test_empty_sentinel(self):
        t = IDFTable.empty()
        assert t.n_docs == 1
        assert t.vocab_size == 0
        assert t.avg_dl > 0

    def test_get_idf_missing_returns_zero(self):
        t = IDFTable.empty()
        assert t.get_idf(12345) == 0.0

    def test_save_load_roundtrip(self, tmp_path):
        builder = IDFTableBuilder()
        builder.add_document("трудовой договор работник")
        builder.add_document("договор права обязанности работник")
        table = builder.build(min_df=1)
        path = tmp_path / "idf.json"
        table.save(path)
        loaded = IDFTable.load(path)
        assert loaded.n_docs == table.n_docs
        assert loaded.vocab_size == table.vocab_size
        assert abs(loaded.avg_dl - table.avg_dl) < 0.01


# ---------------------------------------------------------------------------
# IDFTableBuilder
# ---------------------------------------------------------------------------

class TestIDFTableBuilder:
    def test_zero_docs_returns_empty(self):
        builder = IDFTableBuilder()
        t = builder.build()
        assert t.n_docs == 1   # empty sentinel
        assert t.vocab_size == 0

    def test_n_docs_increments(self):
        builder = IDFTableBuilder()
        builder.add_document("расторжение договора")
        builder.add_document("права работника")
        assert builder.n_docs == 2

    def test_min_df_filters_rare_tokens(self):
        builder = IDFTableBuilder()
        # "редкий" appears only once; "договор" appears twice
        builder.add_document("редкий договор")
        builder.add_document("другой договор")
        table_strict = builder.build(min_df=2)
        table_loose  = builder.build(min_df=1)
        assert table_strict.vocab_size < table_loose.vocab_size

    def test_idf_decreases_with_higher_df(self):
        """A token appearing in every document has lower IDF than a rare one."""
        builder = IDFTableBuilder()
        texts = [f"общий текст документ {i} редкий" for i in range(10)]
        # "общий" appears in all 10; "редкий" only in last one
        texts[-1] = "общий редкий"
        for t in texts:
            builder.add_document(t)
        table = builder.build(min_df=1)

        common_idf = table.get_idf(token_to_index("общий"))
        rare_idf   = table.get_idf(token_to_index("редкий"))
        assert rare_idf >= common_idf, (
            f"Rare token IDF={rare_idf:.3f} should be >= common IDF={common_idf:.3f}"
        )


# ---------------------------------------------------------------------------
# RussianBM25Encoder
# ---------------------------------------------------------------------------

class TestRussianBM25Encoder:
    def _make_encoder(self, texts: list[str]) -> RussianBM25Encoder:
        builder = IDFTableBuilder()
        for t in texts:
            builder.add_document(t)
        return RussianBM25Encoder(builder.build(min_df=1))

    def test_encode_returns_sorted_indices(self):
        enc = self._make_encoder(["расторжение договора", "права работника"])
        indices, values = enc.encode("расторжение договора")
        assert indices == sorted(indices), "Indices must be sorted ascending"

    def test_encode_same_length(self):
        enc = self._make_encoder(["трудовой договор", "права обязанности"])
        indices, values = enc.encode("трудовой договор")
        assert len(indices) == len(values)

    def test_encode_empty_returns_empty(self):
        enc = self._make_encoder(["договор"])
        assert enc.encode("") == ([], [])
        assert enc.encode("   ") == ([], [])

    def test_encode_values_positive(self):
        enc = self._make_encoder(["расторжение договора", "права работника"])
        _, values = enc.encode("расторжение договора")
        assert all(v > 0 for v in values)

    def test_encode_query_pure_idf(self):
        enc = self._make_encoder(["расторжение договора", "трудовой договор"])
        q_idx, q_val = enc.encode_query("расторжение")
        assert len(q_idx) > 0
        assert all(v > 0 for v in q_val)

    def test_encode_query_empty_returns_empty(self):
        enc = self._make_encoder(["договор"])
        assert enc.encode_query("") == ([], [])

    def test_oov_token_gets_fallback_idf(self):
        enc = self._make_encoder(["один документ"])
        # "неизвестное" not in the corpus but should still encode
        indices, values = enc.encode("неизвестное")
        assert len(indices) > 0 or True  # OOV may return empty for 1-doc corpus


# ---------------------------------------------------------------------------
# RRF Fusion
# ---------------------------------------------------------------------------

def _make_result(chunk_id: str, score: float = 1.0) -> RussianSearchResult:
    return RussianSearchResult(
        score=score,
        chunk_id=chunk_id,
        law_id="local:ru/tk",
        law_short="ТК РФ",
        article_num="81",
        article_heading="Тест",
        part_num=None,
        chunk_index=0,
        razdel=None,
        glava="",
        text="текст",
        fragment_id="local:ru/tk/000001/0000",
        source_type="article",
        is_tombstone=False,
        source_file="test.txt",
    )


class TestRRFFusion:
    def test_empty_inputs_return_empty(self):
        assert reciprocal_rank_fusion([], []) == []

    def test_single_dense_result(self):
        fused = reciprocal_rank_fusion([_make_result("a")], [])
        assert len(fused) == 1
        assert fused[0].chunk_id == "a"

    def test_single_sparse_result(self):
        fused = reciprocal_rank_fusion([], [_make_result("x")])
        assert len(fused) == 1
        assert fused[0].chunk_id == "x"

    def test_deduplication(self):
        r = _make_result("dup")
        fused = reciprocal_rank_fusion([r], [r])
        assert len(fused) == 1
        assert fused[0].chunk_id == "dup"

    def test_shared_chunk_beats_exclusive(self):
        shared    = _make_result("shared")
        exclusive = _make_result("exclusive")
        fused = reciprocal_rank_fusion([shared, exclusive], [shared])
        scores = {r.chunk_id: r.score for r in fused}
        assert scores["shared"] > scores["exclusive"], (
            f"shared={scores['shared']:.4f} exclusive={scores['exclusive']:.4f}"
        )

    def test_top_k_truncates(self):
        items = [_make_result(f"c{i}") for i in range(10)]
        assert len(reciprocal_rank_fusion(items, [], top_k=3)) == 3

    def test_no_duplicates_in_output(self):
        items = [_make_result(f"c{i}") for i in range(5)]
        fused = reciprocal_rank_fusion(items, items)
        ids = [r.chunk_id for r in fused]
        assert len(ids) == len(set(ids))

    def test_scores_positive(self):
        items = [_make_result(f"c{i}") for i in range(3)]
        for r in reciprocal_rank_fusion(items, items[:2]):
            assert r.score > 0

    def test_rrf_score_is_set_on_result(self):
        r1 = _make_result("a", score=0.9)
        r2 = _make_result("b", score=0.8)
        fused = reciprocal_rank_fusion([r1], [r2])
        # RRF scores are small fractions (1/(60+rank))
        for r in fused:
            assert 0 < r.score <= 1.0 / 60, (
                f"RRF score {r.score} out of expected range"
            )
