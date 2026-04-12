"""
Exact article lookup against russian_laws_v1.

Retrieval strategy: pure payload filter — no vector search.
  Filter: law_id == <law_id> AND article_num == <article_num>
            [ AND part_num == <part_num> if requested ]
  Order:  sort by chunk_index ASC in Python after fetch
          (Qdrant scroll does not guarantee order by payload field)

This is deterministic and cheaper than vector search for known article numbers.
The caller specifies the canonical law_id (e.g. 'local:ru/tk') and article_num
as a string (e.g. '81', '19.1').

Does NOT:
  - Perform any vector search
  - Perform any BM25 / sparse retrieval
  - Accept free-text queries
  - Import embedding modules
"""
from __future__ import annotations

import logging

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.modules.russia.retrieval.schemas import ArticleLookupResult, RussianChunkResult

log = logging.getLogger(__name__)

COLLECTION_NAME = "russian_laws_v1"
_SCROLL_BATCH = 100   # max chunks per article is ~30; 100 covers any realistic article


class RussianExactLookup:
    """
    Deterministic article lookup against the russian_laws_v1 Qdrant collection.

    Usage:
        lookup = RussianExactLookup(url="http://qdrant:6333")
        result = lookup.get_article(law_id="local:ru/tk", article_num="81")
        if result.hit:
            print(result.full_text)
    """

    def __init__(self, url: str, api_key: str | None = None) -> None:
        self._client = QdrantClient(url=url, api_key=api_key, timeout=30)

    def get_article(
        self,
        law_id: str,
        article_num: str,
        part_num: int | None = None,
    ) -> ArticleLookupResult:
        """
        Look up an article by law_id + article_num (+ optional part_num).

        Args:
            law_id:     Canonical IRI, e.g. 'local:ru/tk'
            article_num: Article number as string, e.g. '81', '19.1'
            part_num:   Optional — if given, return only chunks with this part_num

        Returns:
            ArticleLookupResult with hit=True and chunks in chunk_index order,
            or hit=False with empty chunks if the article is not found.
        """
        must_conditions: list[qm.FieldCondition] = [
            qm.FieldCondition(key="law_id",      match=qm.MatchValue(value=law_id)),
            qm.FieldCondition(key="article_num", match=qm.MatchValue(value=article_num)),
        ]
        if part_num is not None:
            must_conditions.append(
                qm.FieldCondition(key="part_num", match=qm.MatchValue(value=part_num))
            )

        scroll_filter = qm.Filter(must=must_conditions)

        try:
            scroll_result = self._client.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter=scroll_filter,
                limit=_SCROLL_BATCH,
                with_payload=True,
                with_vectors=False,
            )
            raw_points = scroll_result[0]
        except Exception as exc:
            log.error(
                "exact_lookup.scroll_failed law_id=%r article_num=%r err=%s",
                law_id, article_num, exc,
            )
            return self._no_hit(law_id, article_num)

        if not raw_points:
            log.debug("exact_lookup.no_hit law_id=%r article_num=%r", law_id, article_num)
            return self._no_hit(law_id, article_num)

        # Parse and sort by chunk_index (deterministic ordering)
        chunks = sorted(
            [self._point_to_chunk(p.payload) for p in raw_points],
            key=lambda c: c.chunk_index,
        )

        first = chunks[0]
        log.debug(
            "exact_lookup.hit law_id=%r article_num=%r chunks=%d tombstone=%s",
            law_id, article_num, len(chunks), first.is_tombstone,
        )

        return ArticleLookupResult(
            hit=True,
            law_id=law_id,
            article_num=article_num,
            chunks=chunks,
            is_tombstone=first.is_tombstone,
            article_heading=first.article_heading,
        )

    # ── Internals ─────────────────────────────────────────────────────────────

    @staticmethod
    def _no_hit(law_id: str, article_num: str) -> ArticleLookupResult:
        return ArticleLookupResult(
            hit=False,
            law_id=law_id,
            article_num=article_num,
            chunks=[],
            is_tombstone=False,
            article_heading="",
        )

    @staticmethod
    def _point_to_chunk(payload: dict) -> RussianChunkResult:
        """Convert a Qdrant payload dict to a RussianChunkResult."""
        return RussianChunkResult(
            chunk_id=str(payload.get("chunk_id", "")),
            law_id=str(payload.get("law_id", "")),
            law_short=str(payload.get("law_short", "")),
            article_num=str(payload.get("article_num", "")),
            article_heading=str(payload.get("article_heading", "")),
            part_num=payload.get("part_num"),          # int | None — stored natively
            chunk_index=int(payload.get("chunk_index", 0)),
            razdel=payload.get("razdel"),              # str | None
            glava=str(payload.get("glava", "")),
            text=str(payload.get("text", "")),
            fragment_id=str(payload.get("fragment_id", "")),
            source_type=str(payload.get("source_type", "article")),
            is_tombstone=bool(payload.get("is_tombstone", False)),
            source_file=str(payload.get("source_file", "")),
        )
