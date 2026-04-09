"""
BM25 Sparse Encoder for Czech law chunks.

Produces Qdrant-compatible sparse vectors:
  indices: list[int]    — deterministic token hashes (SHA-256 → uint32)
  values:  list[float]  — BM25 weights (Robertson IDF × normalized TF)

Usage — two-pass workflow
─────────────────────────
  # Pass 1: build IDF table from corpus
  builder = IDFTableBuilder()
  for text in corpus:
      builder.add_document(text)
  idf_table = builder.build()

  # (optional) persist
  idf_table.save(path)
  idf_table = IDFTable.load(path)

  # Pass 2: encode individual documents
  encoder = CzechBM25Encoder(idf_table)
  indices, values = encoder.encode(text)

Design principles
─────────────────
  - No external ML dependencies (pure Python + stdlib).
  - Tokenizer is identical to CzechLawSparseRetriever so query and
    document tokens are always in the same space.
  - IDFTable is immutable after build() — thread-safe for parallel encode.
  - Serialization uses JSON (human-readable, no pickle security issues).
  - Token index = first 4 bytes of SHA-256(token) as unsigned int.
    Collision probability for a ~100 k-token Czech legal vocabulary:
    P ≈ 1 - exp(-n²/(2·2³²)) ≈ 0.001  — negligible.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Iterator

log = logging.getLogger(__name__)

# ── Tokenizer ─────────────────────────────────────────────────────────────────
# Matches ASCII-folded alphanumeric tokens (min 2 chars).
# Numbers are kept because Czech law text has many significant numbers
# (§ numbers, year references, article numbers).
_TOKEN_RE = re.compile(r"[0-9]{1,6}|[a-z]{2,}", re.ASCII)

# BM25 hyper-parameters (standard values)
_K1: float = 1.5
_B:  float = 0.75

# Minimum token document-frequency to be included in IDF table.
# Tokens appearing in only 1 document are noisy and inflate index size.
_MIN_DF: int = 2


# ── Token utilities ────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """
    Unicode NFKD → strip combining marks → lowercase.
    Converts accented Czech characters to their ASCII base forms:
      á→a, č→c, ď→d, é→e, ě→e, í→i, ň→n, ó→o, ř→r, š→s, ť→t, ú→u, ů→u, ý→y, ž→z
    """
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def tokenize(text: str) -> list[str]:
    """Normalize and extract tokens from a document text."""
    return _TOKEN_RE.findall(_normalize(text or ""))


def token_to_index(token: str) -> int:
    """
    Deterministic, collision-resistant mapping: token → uint32 index.
    Uses first 4 bytes of SHA-256(token).
    Must be identical in encoder AND retriever query path.
    """
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big", signed=False)


# ── IDF Table ─────────────────────────────────────────────────────────────────

class IDFTable:
    """
    Immutable IDF lookup table built from a corpus.

    Stores:
      _n_docs     — total number of documents in corpus
      _idf        — {token_index: idf_score}
      _avg_dl     — average document length (tokens) for BM25 norm
    """

    def __init__(
        self,
        n_docs: int,
        idf: dict[int, float],
        avg_dl: float,
    ) -> None:
        self._n_docs = n_docs
        self._idf: dict[int, float] = idf
        self._avg_dl: float = avg_dl

    # ── public ────────────────────────────────────────────────────────────────

    @property
    def n_docs(self) -> int:
        return self._n_docs

    @property
    def avg_dl(self) -> float:
        return self._avg_dl

    @property
    def vocab_size(self) -> int:
        return len(self._idf)

    def get_idf(self, token_index: int) -> float:
        """Return IDF score for a token index. 0.0 if not in vocabulary."""
        return self._idf.get(token_index, 0.0)

    # ── serialization ─────────────────────────────────────────────────────────

    def save(self, path: str | Path) -> None:
        """Persist to JSON. Keys are string-encoded ints (JSON requirement)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "n_docs": self._n_docs,
            "avg_dl": self._avg_dl,
            "vocab_size": len(self._idf),
            "idf": {str(k): v for k, v in self._idf.items()},
        }
        path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        log.info(
            "IDFTable saved: path=%s n_docs=%d vocab=%d avg_dl=%.1f",
            path, self._n_docs, len(self._idf), self._avg_dl,
        )

    @classmethod
    def load(cls, path: str | Path) -> IDFTable:
        """Load from JSON checkpoint."""
        path = Path(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        idf = {int(k): float(v) for k, v in payload["idf"].items()}
        table = cls(
            n_docs=int(payload["n_docs"]),
            idf=idf,
            avg_dl=float(payload["avg_dl"]),
        )
        log.info(
            "IDFTable loaded: path=%s n_docs=%d vocab=%d avg_dl=%.1f",
            path, table._n_docs, len(idf), table._avg_dl,
        )
        return table

    @classmethod
    def empty(cls) -> IDFTable:
        """Sentinel used when no IDF table is available (degrades to TF-only)."""
        return cls(n_docs=1, idf={}, avg_dl=100.0)


# ── IDF Table Builder ─────────────────────────────────────────────────────────

class IDFTableBuilder:
    """
    Streaming IDF table builder — add documents one at a time (Pass 1).
    Memory cost: O(vocabulary_size) — typically ~500 KB for Czech legal corpus.
    """

    def __init__(self) -> None:
        self._n_docs: int = 0
        self._df: Counter[int] = Counter()   # {token_index: document_frequency}
        self._total_tokens: int = 0

    def add_document(self, text: str) -> None:
        """
        Register a single document.
        Thread-safety: NOT thread-safe — call from a single thread during Pass 1.
        """
        tokens = tokenize(text)
        if not tokens:
            return
        self._n_docs += 1
        self._total_tokens += len(tokens)
        # Count each unique token once per document (document frequency)
        for idx in set(token_to_index(t) for t in tokens):
            self._df[idx] += 1

    def add_documents(self, texts: Iterator[str]) -> None:
        """Convenience wrapper for streaming iterators."""
        for text in texts:
            self.add_document(text)

    def build(self, min_df: int = _MIN_DF) -> IDFTable:
        """
        Finalize IDF table.

        Robertson IDF (with +1 smoothing to avoid negatives for common tokens):
          IDF(t) = log( (N - df(t) + 0.5) / (df(t) + 0.5) + 1 )

        Tokens with df < min_df are excluded (noise reduction + index size).
        """
        if self._n_docs == 0:
            log.warning("IDFTableBuilder.build() called with 0 documents — returning empty table")
            return IDFTable.empty()

        avg_dl = self._total_tokens / self._n_docs
        idf: dict[int, float] = {}

        for token_idx, df in self._df.items():
            if df < min_df:
                continue
            score = math.log((self._n_docs - df + 0.5) / (df + 0.5) + 1.0)
            if score > 0.0:
                idf[token_idx] = score

        log.info(
            "IDFTable built: n_docs=%d raw_vocab=%d filtered_vocab=%d avg_dl=%.1f min_df=%d",
            self._n_docs, len(self._df), len(idf), avg_dl, min_df,
        )
        return IDFTable(n_docs=self._n_docs, idf=idf, avg_dl=avg_dl)

    @property
    def n_docs(self) -> int:
        return self._n_docs


# ── BM25 Encoder ──────────────────────────────────────────────────────────────

class CzechBM25Encoder:
    """
    Encodes a single document text into a BM25 sparse vector.

    Thread-safe: IDFTable is immutable; encoder holds no mutable state.

    Parameters
    ----------
    idf_table : IDFTable
        Pre-built IDF table from Pass 1. Use IDFTable.empty() for TF-only mode.
    k1 : float
        BM25 term saturation parameter (default 1.5).
    b : float
        BM25 length normalization parameter (default 0.75).
    """

    def __init__(
        self,
        idf_table: IDFTable,
        k1: float = _K1,
        b: float = _B,
    ) -> None:
        self._idf = idf_table
        self._k1 = k1
        self._b = b

    def encode(self, text: str) -> tuple[list[int], list[float]]:
        """
        Encode text into BM25 sparse vector.

        Returns
        -------
        indices : list[int]   — token hashes, sorted ascending (Qdrant requirement)
        values  : list[float] — corresponding BM25 weights, all > 0

        Returns ([], []) for empty or unparseable text.
        """
        tokens = tokenize(text)
        if not tokens:
            return [], []

        dl = len(tokens)
        avg_dl = max(self._idf.avg_dl, 1.0)
        tf_map = Counter(tokens)

        result: dict[int, float] = {}
        for token, tf in tf_map.items():
            idx = token_to_index(token)
            idf = self._idf.get_idf(idx)
            if idf == 0.0:
                # Token not in IDF table → use minimal IDF (1 doc corpus assumption)
                # This handles out-of-vocabulary tokens gracefully instead of dropping them.
                idf = math.log((self._idf.n_docs + 0.5) / 1.5 + 1.0)

            norm_tf = (tf * (self._k1 + 1.0)) / (
                tf + self._k1 * (1.0 - self._b + self._b * dl / avg_dl)
            )
            weight = idf * norm_tf
            if weight > 0.0:
                # Sum weights for colliding hashes (extremely rare)
                result[idx] = result.get(idx, 0.0) + weight

        if not result:
            return [], []

        # Sort by index — Qdrant requires sorted indices for sparse vectors
        sorted_pairs = sorted(result.items())
        indices = [idx for idx, _ in sorted_pairs]
        values  = [val for _, val in sorted_pairs]
        return indices, values

    def encode_query(self, text: str) -> tuple[list[int], list[float]]:
        """
        Encode a search query.

        For queries we use pure IDF (no TF normalization) because queries
        are short and term frequency carries no signal.
        Returns ([], []) for empty queries.
        """
        tokens = tokenize(text)
        if not tokens:
            return [], []

        result: dict[int, float] = {}
        for token in set(tokens):   # deduplicate
            idx = token_to_index(token)
            idf = self._idf.get_idf(idx)
            if idf == 0.0:
                idf = math.log((self._idf.n_docs + 0.5) / 1.5 + 1.0)
            if idf > 0.0:
                result[idx] = result.get(idx, 0.0) + idf

        if not result:
            return [], []

        sorted_pairs = sorted(result.items())
        return [i for i, _ in sorted_pairs], [v for _, v in sorted_pairs]
