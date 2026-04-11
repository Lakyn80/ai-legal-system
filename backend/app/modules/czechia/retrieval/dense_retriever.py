from __future__ import annotations

import logging
import re

from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.modules.czechia.retrieval.text_utils import extract_paragraphs_from_payload

# ── sort helpers for exact_lookup ─────────────────────────────────────────────
#
# Problem: paragraph=N is a *context* tag set by local_loader, not a "belongs to"
# tag.  All fragments between §52 and §53 in the source document get paragraph=52,
# including structural headings ("Díl 4", "HLAVA III"), section titles that precede
# the next Paragraf node, and fragments from other provisions that cross-reference
# §52 in their text.
#
# Fix: sort by chunk rank so substantive §N text rises to the top.
#
#   rank 0 — primary: substantive text that belongs to §N
#             (does not contain "§ N" as a cross-reference, has enough substance)
#   rank 1 — structural: short heading/title text without legal content
#             (inherited paragraph context, not actual §N text)
#   rank 2 — cross-reference: text from another provision that cites §N inline
#             (contains "§ N" but is not the heading "§ N")
#
# Lower rank = higher sort priority (ascending).

_SECTION_HEADING_RANK_RE = re.compile(
    r"^(?:část|hlava|díl|oddíl|pododdíl|kapitola)\b",
    re.IGNORECASE | re.UNICODE,
)


_FRAGMENT_ID_SUFFIX_RE = re.compile(r"/(\d+)$")


def _fragment_id_numeric(payload: dict) -> int | None:
    """Extract the trailing numeric component from a fragment_id like 'local:sb/2006/262/6661131'."""
    m = _FRAGMENT_ID_SUFFIX_RE.search(str(payload.get("fragment_id", "")))
    return int(m.group(1)) if m else None


def _heading_fragment_id(results: list[dict]) -> int | None:
    """Return the numeric fragment_id of the exact-heading-match chunk, if any."""
    for payload in results:
        if payload.get("_exact_heading_match"):
            return _fragment_id_numeric(payload)
    return None


def _paragraph_chunk_rank(payload: dict, paragraph_set: set[str], heading_fid: int | None = None) -> int:
    """
    Return sort rank for exact_lookup ordering.  Lower = higher priority.

    rank 0  primary text   — substantive content that IS this paragraph
    rank 1  structural     — heading/title with inherited paragraph context, or a
                             fragment that physically precedes the §N heading in the
                             document (got paragraph=N via context inheritance from
                             the prior section, not because it belongs to §N)
    rank 2  cross-ref      — text from another provision citing §N inline
    """
    text = (payload.get("text") or "").strip()
    if not text:
        return 1

    # Cross-reference: text contains "§ N" but is not the bare heading "§ N"
    # (the bare heading is handled by _exact_heading_match, rank 0 via that path)
    for paragraph in paragraph_set:
        ref = f"§ {paragraph}"
        if ref in text and not (text == ref or text.startswith(ref + " ")):
            return 2

    # Structural heading: matches section-level keywords OR is short with no
    # digits and no sentence-ending punctuation (title-like text).
    if _SECTION_HEADING_RANK_RE.match(text):
        return 1
    words = re.findall(r"\w+", text, flags=re.UNICODE)
    if (
        len(text) < 60
        and len(words) <= 7
        and not re.search(r"\d", text)
        and not re.search(r"[.;]", text)
    ):
        return 1

    # Pre-paragraph inherited context: fragment physically precedes the §N heading
    # in the source document (numerically lower fragment_id).  local_loader sets
    # paragraph=N on ALL fragments between §N-1 and §N, so fragments that belonged
    # to the previous section carry paragraph=N incorrectly.
    if heading_fid is not None:
        fid = _fragment_id_numeric(payload)
        if fid is not None and fid < heading_fid:
            return 1

    return 0  # primary substantive text

_COLLECTION = "czech_laws_v2"
_QDRANT_TIMEOUT = 30
_SCROLL_BATCH = 256

log = logging.getLogger(__name__)


class CzechLawDenseRetriever:
    def __init__(self, url: str, api_key: str | None = None) -> None:
        self.url = url
        self.api_key = api_key
        self._client = QdrantClient(
            url=url,
            api_key=api_key,
            timeout=_QDRANT_TIMEOUT,
        )

    def retrieve(
        self,
        query_vector: list[float],
        law_iris: list[str] | None = None,
        top_k: int = 20,
    ) -> list[dict]:
        if not query_vector or top_k <= 0:
            return []

        try:
            response = self._client.query_points(
                collection_name=_COLLECTION,
                query=query_vector,
                using="dense",
                query_filter=_build_law_filter(law_iris),
                limit=top_k,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            log.error("czech dense retrieval failed: %s", exc)
            return []

        return [_point_to_payload(h, score_key="_dense_score") for h in response.points]

    def exact_lookup(
        self,
        law_iris: list[str] | None,
        paragraph_numbers: list[str],
        limit: int = 20,
    ) -> list[dict]:
        if not paragraph_numbers or limit <= 0:
            return []

        law_iris = law_iris or []
        paragraph_set = set(paragraph_numbers)
        results: list[dict] = []
        seen: set[str] = set()

        target_law_iris = law_iris if law_iris else [None]

        # Overscan cap: collect up to this many raw candidates before sort+truncate.
        # Must be > _SCROLL_BATCH so the inner loop always drains each Qdrant page
        # fully — the exact-heading chunk can appear anywhere in scroll order and
        # must not be skipped because we hit `limit` early.
        _OVERSCAN = _SCROLL_BATCH * 4

        for law_iri in target_law_iris:
            offset = None
            while len(results) < _OVERSCAN:
                must_conditions: list[models.FieldCondition] = [
                    models.FieldCondition(
                        key="paragraph",
                        match=models.MatchAny(any=list(paragraph_set)),
                    )
                ]
                if law_iri:
                    must_conditions.insert(
                        0,
                        models.FieldCondition(
                            key="law_iri",
                            match=models.MatchValue(value=law_iri),
                        ),
                    )
                try:
                    records, offset = self._client.scroll(
                        collection_name=_COLLECTION,
                        scroll_filter=models.Filter(
                            must=must_conditions
                        ),
                        limit=_SCROLL_BATCH,
                        offset=offset,
                        with_payload=True,
                        with_vectors=False,
                        timeout=_QDRANT_TIMEOUT,
                    )
                except Exception as exc:
                    log.error("czech exact lookup failed for %s: %s", law_iri or "<all-laws>", exc)
                    break

                if not records:
                    break

                for record in records:
                    payload = _record_to_payload(record)
                    chunk_id = payload.get("chunk_id")
                    if not chunk_id or chunk_id in seen:
                        continue
                    seen.add(chunk_id)
                    payload["_dense_score"] = 1.0
                    payload["_exact_match"] = True
                    payload["_exact_heading_match"] = _is_exact_heading_match(payload, paragraph_set)
                    results.append(payload)

                if offset is None:
                    break

        heading_fid = _heading_fragment_id(results)
        results.sort(
            key=lambda payload: (
                -int(bool(payload.get("_exact_heading_match"))),        # "§ 52" literal first
                _paragraph_chunk_rank(payload, paragraph_set, heading_fid),  # primary < structural < cross-ref
                int(payload.get("chunk_index", 0) or 0),                # within-fragment order
                str(payload.get("fragment_id", "")),
                str(payload.get("chunk_id", "")),
            )
        )
        return results[:limit]

    def expand_neighbors(
        self,
        anchors: list[dict],
        window: int = 1,
        limit: int = 20,
    ) -> list[dict]:
        if not anchors or limit <= 0 or window <= 0:
            return []

        expanded: dict[str, dict] = {}
        for anchor in anchors:
            fragment_id = anchor.get("fragment_id")
            anchor_chunk_id = anchor.get("chunk_id")
            if not fragment_id or anchor_chunk_id is None:
                continue
            try:
                anchor_index = int(anchor.get("chunk_index", 0))
            except (TypeError, ValueError):
                anchor_index = 0

            try:
                records, _ = self._client.scroll(
                    collection_name=_COLLECTION,
                    scroll_filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="fragment_id",
                                match=models.MatchValue(value=fragment_id),
                            )
                        ]
                    ),
                    limit=max(8, (window * 6) + 2),
                    with_payload=True,
                    with_vectors=False,
                    timeout=_QDRANT_TIMEOUT,
                )
            except Exception as exc:
                log.error("czech structural expansion failed for %s: %s", fragment_id, exc)
                continue

            for record in records:
                payload = _record_to_payload(record)
                chunk_id = payload.get("chunk_id")
                if not chunk_id or chunk_id == anchor_chunk_id:
                    continue
                try:
                    neighbor_index = int(payload.get("chunk_index", 0))
                except (TypeError, ValueError):
                    neighbor_index = 0
                if abs(neighbor_index - anchor_index) > window:
                    continue
                if chunk_id not in expanded:
                    payload["_dense_score"] = float(payload.get("_dense_score", 0.0))
                    payload["_structural_neighbor"] = True
                    payload["_neighbor_of_chunk_id"] = anchor_chunk_id
                    payload["_neighbor_of_exact_match"] = bool(anchor.get("_exact_match"))
                    expanded[chunk_id] = payload
                if len(expanded) >= limit:
                    return list(expanded.values())

        return list(expanded.values())

    def retrieve_by_keywords(
        self,
        query_vector: list[float],
        keywords: list[str],
        top_k: int = 10,
    ) -> list[dict]:
        if not query_vector or not keywords or top_k <= 0:
            return []

        try:
            response = self._client.query_points(
                collection_name=_COLLECTION,
                query=query_vector,
                using="dense",
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="text",
                            match=models.MatchText(text=keywords[0]),
                        )
                    ]
                ),
                limit=top_k,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            log.error("czech dense keyword retrieval failed: %s", exc)
            return []

        return [_point_to_payload(h, score_key="_dense_score") for h in response.points]


def _build_law_filter(law_iris: list[str] | None) -> models.Filter | None:
    if not law_iris:
        return None
    return models.Filter(
        must=[
            models.FieldCondition(
                key="law_iri",
                match=models.MatchAny(any=law_iris),
            )
        ]
    )


def _record_to_payload(record) -> dict:
    return dict(record.payload or {})


def _point_to_payload(point, score_key: str) -> dict:
    payload = dict(point.payload or {})
    payload[score_key] = float(point.score)
    return payload


def _is_exact_heading_match(payload: dict, paragraph_set: set[str]) -> bool:
    text = str(payload.get("text", "")).strip()
    paragraphs = set(extract_paragraphs_from_payload(payload))
    if not paragraph_set.intersection(paragraphs):
        return False
    return any(text == f"§ {paragraph}" or text.startswith(f"§ {paragraph} ") for paragraph in paragraph_set)
