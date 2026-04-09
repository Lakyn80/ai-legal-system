from __future__ import annotations

import logging

from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.modules.czechia.retrieval.text_utils import extract_paragraphs_from_payload

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

        for law_iri in target_law_iris:
            offset = None
            while len(results) < limit:
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
                    if len(results) >= limit:
                        break

                if offset is None:
                    break

        results.sort(
            key=lambda payload: (
                -int(bool(payload.get("_exact_heading_match"))),
                -int(bool(payload.get("_exact_match"))),
                int(payload.get("chunk_index", 0) or 0),
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
