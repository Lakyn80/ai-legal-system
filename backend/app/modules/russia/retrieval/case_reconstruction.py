"""
Full-case reconstruction from RU clean Qdrant chunks.

Loads all chunks for a case_id, groups them by doc_id, sorts deterministically,
merges overlap artifacts, and produces CaseDocumentInput[] for Agent 2 extraction.
"""
from __future__ import annotations

import re
from collections import defaultdict

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
from qdrant_client.http.exceptions import UnexpectedResponse

from app.modules.common.agents.agent2_legal_strategy.input_schemas import (
    CaseDocumentInput,
    LegalEvidencePack,
    RetrievedArticleExcerpt,
)
from app.modules.common.agents.agent2_legal_strategy.schemas import SourceRef


_CORE_TYPES = {"judgment", "appeal", "claim", "party_submission", "evidence", "procedural_document"}
_DOC_ID_RE = re.compile(r"^case::(?P<case_id>[^:]+)::doc::(?P<logical>.+)$")


def _overlap_merge(base: str, nxt: str, max_overlap: int = 600) -> str:
    """
    Merge two text fragments while removing direct suffix/prefix overlap.
    """
    if not base:
        return nxt
    if not nxt:
        return base

    b = base.rstrip()
    n = nxt.lstrip()
    max_k = min(len(b), len(n), max_overlap)
    overlap = 0
    for k in range(max_k, 24, -1):
        if b[-k:] == n[:k]:
            overlap = k
            break
    if overlap:
        return b + n[overlap:]
    return b + "\n\n" + n


def _as_int(v, fallback: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return fallback


def _normalize_document_type(v: str) -> str:
    raw = (v or "").strip().lower()
    allowed = {
        "judgment",
        "appeal",
        "claim",
        "party_submission",
        "order",
        "evidence",
        "procedural_document",
        "translation",
        "service_document",
        "other_relevant_document",
    }
    return raw if raw in allowed else "other_relevant_document"


class RussianCaseReconstructionService:
    def __init__(
        self,
        *,
        qdrant_url: str,
        qdrant_api_key: str | None,
        collection_name: str,
    ) -> None:
        self._client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key, timeout=60)
        self._collection_name = collection_name

    def load_case_chunks(self, case_id: str) -> list[dict]:
        chunks: list[dict] = []
        offset = None
        query_filter = qm.Filter(
            must=[qm.FieldCondition(key="case_id", match=qm.MatchValue(value=case_id))]
        )
        try:
            while True:
                points, next_offset = self._client.scroll(
                    collection_name=self._collection_name,
                    scroll_filter=query_filter,
                    with_payload=True,
                    with_vectors=False,
                    limit=512,
                    offset=offset,
                )
                for p in points:
                    if p.payload:
                        chunks.append(p.payload)
                if next_offset is None:
                    break
                offset = next_offset
        except UnexpectedResponse as exc:
            is_missing_collection = exc.status_code == 404 and (
                "doesn't exist" in exc.content.decode("utf-8", errors="ignore").lower()
                or "not found: collection" in exc.content.decode("utf-8", errors="ignore").lower()
            )
            if is_missing_collection:
                raise ValueError(
                    f"Qdrant collection '{self._collection_name}' was not found. "
                    "Run RU case chunk indexing for legal_case_chunks_ru_clean or override "
                    "RUSSIA_QDRANT_COLLECTION to a compatible case-chunk collection."
                ) from exc
            raise
        return chunks

    def reconstruct_case_documents(self, case_id: str) -> list[CaseDocumentInput]:
        chunks = self.load_case_chunks(case_id)
        if not chunks:
            raise ValueError(
                f"No chunks found for case_id={case_id} in collection={self._collection_name}"
            )

        by_doc: dict[str, list[dict]] = defaultdict(list)
        for ch in chunks:
            doc_id = str(ch.get("doc_id") or "").strip()
            if not doc_id:
                continue
            by_doc[doc_id].append(ch)
        if not by_doc:
            raise ValueError(f"No doc_id metadata found for case_id={case_id}")

        docs: list[CaseDocumentInput] = []
        for doc_id, rows in sorted(by_doc.items(), key=lambda kv: min(_as_int(r.get("logical_index"), 10**9) for r in kv[1])):
            rows_sorted = sorted(
                rows,
                key=lambda r: (
                    _as_int(r.get("page_from"), 0),
                    _as_int(r.get("page_to"), 0),
                    _as_int(r.get("chunk_index"), 0),
                ),
            )
            text = ""
            page_labels: list[str] = []
            seen_pages: set[str] = set()
            for row in rows_sorted:
                frag = str(row.get("text") or "")
                text = _overlap_merge(text, frag)
                pf = _as_int(row.get("page_from"), 0)
                pt = _as_int(row.get("page_to"), pf)
                label = f"p.{pf}" if pf == pt else f"p.{pf}-{pt}"
                if label not in seen_pages and pf > 0:
                    seen_pages.add(label)
                    page_labels.append(label)

            m = _DOC_ID_RE.match(doc_id)
            logical_raw = m.group("logical") if m else ""
            primary_document_id = str(rows_sorted[0].get("primary_document_id") or "").strip()
            logical_index = _as_int(logical_raw, -1)
            if logical_index < 0 and not primary_document_id:
                primary_document_id = logical_raw or doc_id.rsplit("::", 1)[-1]

            meta0 = rows_sorted[0]
            document_type = _normalize_document_type(str(meta0.get("document_type") or ""))
            document_date = str(meta0.get("document_date") or "")
            document_role = str(meta0.get("document_role") or "")
            title = str(meta0.get("document_title") or meta0.get("title") or "")
            full_text_reference = f"qdrant://{self._collection_name}/{case_id}/{doc_id}"

            if not text.strip() and document_type in _CORE_TYPES:
                raise ValueError(f"Core legal document reconstructed empty: doc_id={doc_id}")

            docs.append(
                CaseDocumentInput(
                    primary_document_id=primary_document_id,
                    document_type=document_type,
                    document_date=document_date,
                    document_role=document_role,
                    title=title,
                    content=text,
                    source_pages=page_labels,
                    full_text_reference=full_text_reference,
                )
            )
        return docs

    def build_evidence_pack_from_chunks(self, case_id: str) -> LegalEvidencePack:
        chunks = self.load_case_chunks(case_id)
        refs: list[SourceRef] = []
        seen: set[tuple[str, str]] = set()
        excerpts: list[RetrievedArticleExcerpt] = []
        ex_seen: set[tuple[str, str]] = set()
        for ch in chunks:
            law = str(ch.get("law_short") or ch.get("law") or "").strip()
            article = str(ch.get("article_num") or ch.get("provision") or "").strip()
            txt = str(ch.get("text") or "")
            if law and article:
                key = (law, article)
                if key not in seen:
                    seen.add(key)
                    refs.append(SourceRef(law=law, article=article))
                if key not in ex_seen:
                    ex_seen.add(key)
                    excerpts.append(RetrievedArticleExcerpt(law=law, article=article, excerpt=txt[:1200]))
        return LegalEvidencePack(
            primary_sources=refs,
            supporting_sources=[],
            retrieved_articles=excerpts,
            matched_issues=[],
            retrieval_notes=[f"reconstructed_from_qdrant:{self._collection_name}"],
        )

