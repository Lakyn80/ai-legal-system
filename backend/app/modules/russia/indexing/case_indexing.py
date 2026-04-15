from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.modules.common.embeddings.provider import EmbeddingService

_DOC_TYPE_ALLOWED = {
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
_DOC_TYPE_FALLBACK = "other_relevant_document"
_CHUNK_UUID_NAMESPACE = uuid.NAMESPACE_URL
_MAX_CHARS = 2200
_OVERLAP_CHARS = 250


class CaseIndexingError(RuntimeError):
    pass


@dataclass
class PageText:
    page_number: int
    text_ru: str
    text_cs: str | None


@dataclass
class CaseDoc:
    case_id: str
    doc_id: str
    logical_index: int
    primary_document_id: str
    document_title: str
    document_type: str
    document_date: str
    document_role: str
    document_number: str
    case_number: str
    document_kind: str
    pages: list[PageText]


def _now_utc() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _safe_case_id(case_id: str) -> str:
    clean = case_id.strip()
    if not clean:
        raise CaseIndexingError("case_id must not be empty.")
    return clean


def _normalize_doc_type(value: str) -> str:
    norm = (value or "").strip().lower()
    if norm in _DOC_TYPE_ALLOWED:
        return norm
    return _DOC_TYPE_FALLBACK


def _as_int(value: Any, *, field_name: str) -> int:
    try:
        return int(value)
    except Exception as exc:
        raise CaseIndexingError(f"Field '{field_name}' must be an integer, got: {value!r}") from exc


def _extract_page_text_fields(page: dict[str, Any]) -> tuple[str, str | None]:
    # Preferred canonical shape:
    # {"text": {"ru": "...", "cs": "..."}}
    text_obj = page.get("text")
    if isinstance(text_obj, dict):
        ru = str(text_obj.get("ru") or "").strip()
        cs = str(text_obj.get("cs") or "").strip() or None
        if ru:
            return ru, cs

    # Common aliases:
    ru = str(page.get("text_ru") or page.get("ru_text") or page.get("content_ru") or "").strip()
    cs = str(page.get("text_cs") or page.get("cs_text") or page.get("content_cs") or "").strip() or None
    if ru:
        return ru, cs

    # Legacy RU-only shape:
    legacy = str(page.get("text") or "").strip()
    if legacy:
        return legacy, None

    raise CaseIndexingError("Each page must include RU text (text.ru or text_ru or text).")


def _normalize_ws(v: str) -> str:
    return re.sub(r"\s+", " ", (v or "")).strip()


def _infer_case_number(text: str) -> str:
    m = re.search(r"дело\s*№\s*([A-Za-zА-Яа-я0-9\-/]+)", text, flags=re.IGNORECASE)
    if m:
        return _normalize_ws(m.group(1))
    m2 = re.search(r"\b\d{1,3}\s*-\s*\d{1,6}/\d{2,4}\b", text)
    return _normalize_ws(m2.group(0)) if m2 else ""


def _infer_document_number(text: str) -> str:
    m = re.search(r"\b№\s*([A-Za-zА-Яа-я0-9\-/]+)", text)
    return _normalize_ws(m.group(1)) if m else ""


def _infer_document_kind(text: str, document_type: str) -> str:
    low = text.lower()
    if "определение" in low:
        return "determination"
    if "решение" in low:
        return "judgment"
    if "постановление" in low:
        return "ruling"
    if "апелляцион" in low:
        return "appeal"
    if "жалоб" in low:
        return "appeal"
    if "исков" in low:
        return "claim"
    return document_type or "other"


def _infer_title(text: str, logical_index: int, document_type: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    preferred = None
    for ln in lines[:24]:
        n = _normalize_ws(ln)
        if len(n) < 4:
            continue
        if not re.search(r"[A-Za-zА-Яа-яЁё]", n):
            continue
        preferred = n
        if re.search(r"(определение|решение|постановление|апелляцион|жалоб)", n, flags=re.IGNORECASE):
            break
    if preferred:
        return preferred[:180]
    label = {
        "judgment": "Решение",
        "appeal": "Апелляция",
        "claim": "Иск",
        "order": "Определение",
        "evidence": "Доказательство",
        "procedural_document": "Процессуальный документ",
    }.get(document_type, "Документ")
    return f"{label} #{logical_index}"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CaseIndexingError(f"Validated case JSON not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CaseIndexingError(f"Invalid JSON in validated case file: {path} ({exc})") from exc


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if raw:
                    rows.append(json.loads(raw))
    except FileNotFoundError as exc:
        raise CaseIndexingError(f"Legacy RU docs JSONL not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CaseIndexingError(f"Invalid JSONL row in {path}: {exc}") from exc
    if not rows:
        raise CaseIndexingError(f"Legacy RU docs JSONL is empty: {path}")
    return rows


def _canonical_doc_filename(case_id: str) -> str:
    return f"case_{case_id}_validated.json"


def _canonical_manifest_filename(case_id: str) -> str:
    return f"case_{case_id}_manifest.json"


def _canonical_report_filename(case_id: str) -> str:
    return f"case_{case_id}_indexing_report.json"


def ensure_case_layout(case_root: Path) -> dict[str, Path]:
    paths = {
        "case_root": case_root,
        "source": case_root / "source",
        "synthesis": case_root / "synthesis",
        "exports": case_root / "exports",
        "indexing": case_root / "indexing",
        "logs": case_root / "logs",
        "manifests": case_root / "manifests",
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    return paths


def build_validated_from_legacy_ru_jsonl(case_id: str, legacy_rows: list[dict[str, Any]]) -> dict[str, Any]:
    documents: list[dict[str, Any]] = []
    for row in legacy_rows:
        row_case_id = str(row.get("case_id") or "").strip()
        if row_case_id and row_case_id != case_id:
            continue
        pages_raw = row.get("pages") or []
        if not isinstance(pages_raw, list):
            raise CaseIndexingError("Legacy row field 'pages' must be a list.")
        pages: list[dict[str, Any]] = []
        for page in pages_raw:
            if not isinstance(page, dict):
                raise CaseIndexingError("Legacy page must be an object.")
            page_number = _as_int(page.get("page_number"), field_name="page_number")
            pages.append(
                {
                    "page_number": page_number,
                    "text": {
                        "ru": str(page.get("text") or ""),
                        "cs": None,
                    },
                }
            )
        full_text = "\n\n".join(str(p.get("text", "")) for p in pages_raw if isinstance(p, dict))
        document_type = _normalize_doc_type(str(row.get("document_type") or ""))
        case_number = _infer_case_number(full_text)
        document_number = _infer_document_number(full_text)
        document_kind = _infer_document_kind(full_text, document_type)
        inferred_title = _infer_title(full_text, int(row.get("logical_index") or 0), document_type)
        documents.append(
            {
                "doc_id": row.get("doc_id"),
                "logical_index": row.get("logical_index"),
                "primary_document_id": row.get("primary_document_id", ""),
                "document_title": inferred_title,
                "document_type": document_type,
                "document_date": row.get("document_date") or "",
                "document_role": row.get("document_role") or "",
                "document_number": document_number,
                "case_number": case_number,
                "document_kind": document_kind,
                "pages": pages,
            }
        )
    if not documents:
        raise CaseIndexingError(f"No legacy rows found for case_id={case_id}")

    # Auto-decontamination gate: keep dominant case number, drop foreign dockets.
    case_freq: dict[str, int] = {}
    for doc in documents:
        cn = _normalize_ws(str(doc.get("case_number") or ""))
        if cn:
            case_freq[cn] = case_freq.get(cn, 0) + 1
    dominant_case_number = max(case_freq, key=case_freq.get) if case_freq else ""
    if dominant_case_number:
        filtered_docs: list[dict[str, Any]] = []
        for doc in documents:
            cn = _normalize_ws(str(doc.get("case_number") or ""))
            if cn and cn != dominant_case_number:
                continue
            filtered_docs.append(doc)
        documents = filtered_docs

    # Optional deterministic compaction for fragmented court artifacts.
    # Many OCR-derived rows represent slices of the same court act. We merge
    # those by strong legal identity key to reduce FE noise.
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for doc in documents:
        primary_document_id = _normalize_ws(str(doc.get("primary_document_id") or ""))
        document_seq = _normalize_ws(str(doc.get("document_seq") or ""))
        if primary_document_id:
            key = (f"pid::{primary_document_id}", document_seq, str(doc.get("document_date") or ""))
            can_merge = True
        else:
            can_merge = (
                bool(doc.get("case_number"))
                and doc.get("document_type") in {"judgment", "appeal", "order"}
                and bool(doc.get("document_date"))
            )
            if not can_merge:
                key = (str(doc["logical_index"]), "", "")
            else:
                key = (
                    str(doc.get("case_number") or ""),
                    str(doc.get("document_kind") or doc.get("document_type") or ""),
                    str(doc.get("document_date") or ""),
                )
        if key not in grouped:
            grouped[key] = {
                **doc,
                "pages": list(doc.get("pages") or []),
            }
            continue
        target = grouped[key]
        existing = {(int(p["page_number"]), _normalize_ws(str((p.get("text") or {}).get("ru") or ""))) for p in target["pages"]}
        for p in doc.get("pages") or []:
            sig = (int(p["page_number"]), _normalize_ws(str((p.get("text") or {}).get("ru") or "")))
            if sig not in existing:
                target["pages"].append(p)
                existing.add(sig)
        # Keep minimum logical index for stable ordering.
        target["logical_index"] = min(int(target["logical_index"]), int(doc["logical_index"]))

    documents = list(grouped.values())
    documents.sort(key=lambda d: int(d["logical_index"]))
    for idx, doc in enumerate(documents):
        logical_index = int(doc["logical_index"])
        doc["doc_id"] = f"case::{case_id}::doc::{logical_index}"
        doc["pages"] = sorted(doc["pages"], key=lambda p: int(p["page_number"]))

    return {
        "schema_version": "case_validated.v1",
        "case_id": case_id,
        "documents": documents,
    }


def load_case_documents(validated_payload: dict[str, Any], expected_case_id: str) -> list[CaseDoc]:
    payload_case_id = str(validated_payload.get("case_id") or "").strip()
    if payload_case_id != expected_case_id:
        raise CaseIndexingError(
            f"Validated JSON case_id mismatch: expected={expected_case_id} got={payload_case_id!r}"
        )
    raw_docs = validated_payload.get("documents")
    if not isinstance(raw_docs, list) or not raw_docs:
        raise CaseIndexingError("Validated JSON must contain non-empty 'documents' list.")

    out: list[CaseDoc] = []
    for d in raw_docs:
        if not isinstance(d, dict):
            raise CaseIndexingError("Each document in validated JSON must be an object.")
        logical_index = _as_int(d.get("logical_index"), field_name="logical_index")
        doc_id = str(d.get("doc_id") or f"case::{expected_case_id}::doc::{logical_index}").strip()
        pages_raw = d.get("pages")
        if not isinstance(pages_raw, list) or not pages_raw:
            raise CaseIndexingError(f"Document {doc_id} must contain non-empty pages list.")
        pages: list[PageText] = []
        for p in pages_raw:
            if not isinstance(p, dict):
                raise CaseIndexingError(f"Document {doc_id}: each page must be an object.")
            page_number = _as_int(p.get("page_number"), field_name="page_number")
            ru, cs = _extract_page_text_fields(p)
            pages.append(PageText(page_number=page_number, text_ru=ru, text_cs=cs))
        pages.sort(key=lambda x: x.page_number)
        out.append(
            CaseDoc(
                case_id=expected_case_id,
                doc_id=doc_id,
                logical_index=logical_index,
                primary_document_id=str(d.get("primary_document_id") or ""),
                document_title=str(d.get("document_title") or d.get("title") or f"Document {logical_index}"),
                document_type=_normalize_doc_type(str(d.get("document_type") or "")),
                document_date=str(d.get("document_date") or ""),
                document_role=str(d.get("document_role") or ""),
                document_number=str(d.get("document_number") or ""),
                case_number=str(d.get("case_number") or ""),
                document_kind=str(d.get("document_kind") or ""),
                pages=pages,
            )
        )
    out.sort(key=lambda x: x.logical_index)
    return out


def _split_text_for_retrieval(text: str) -> list[str]:
    source = text.strip()
    if not source:
        return []
    if len(source) <= _MAX_CHARS:
        return [source]

    paragraphs = [p.strip() for p in source.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for paragraph in paragraphs:
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= _MAX_CHARS:
            current = candidate
            continue
        flush()
        if len(paragraph) <= _MAX_CHARS:
            current = paragraph
            continue

        # Oversized paragraph: split by sentence-like boundaries.
        sentence_parts = re.split(r"(?<=[\.\!\?\;\:])\s+", paragraph)
        sub = ""
        for part in sentence_parts:
            cand = part if not sub else f"{sub} {part}"
            if len(cand) <= _MAX_CHARS:
                sub = cand
            else:
                if sub:
                    chunks.append(sub.strip())
                    overlap = sub[-_OVERLAP_CHARS :]
                    sub = f"{overlap} {part}".strip()
                else:
                    hard = part[:_MAX_CHARS]
                    chunks.append(hard.strip())
                    sub = part[max(1, _MAX_CHARS - _OVERLAP_CHARS) :].strip()
        if sub.strip():
            current = sub.strip()
    flush()

    if len(chunks) < 2:
        return chunks
    # Add overlap between adjacent chunks for better retrieval continuity.
    out = [chunks[0]]
    for idx in range(1, len(chunks)):
        prev_tail = out[-1][-_OVERLAP_CHARS :]
        out.append(f"{prev_tail}\n{chunks[idx]}".strip())
    return out


def _make_point_id(*, case_id: str, doc_id: str, language: str, page: int, chunk_index: int) -> str:
    key = f"case::{case_id}::doc::{doc_id}::lang::{language}::p::{page}::chunk::{chunk_index}"
    return str(uuid.uuid5(_CHUNK_UUID_NAMESPACE, key))


def build_chunk_rows(
    docs: list[CaseDoc],
    *,
    allow_cz_fallback_from_ru: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    ru_rows: list[dict[str, Any]] = []
    cs_rows: list[dict[str, Any]] = []
    fallback_pages = 0
    for doc in docs:
        for page in doc.pages:
            ru_chunks = _split_text_for_retrieval(page.text_ru)
            if not ru_chunks:
                continue
            cs_source = page.text_cs
            if not cs_source:
                if allow_cz_fallback_from_ru:
                    cs_source = page.text_ru
                    fallback_pages += 1
                else:
                    raise CaseIndexingError(
                        f"Missing CZ translation text for doc={doc.doc_id} page={page.page_number}. "
                        "Provide cs text in validated JSON or use --allow-cz-fallback-from-ru for smoke-only mode."
                    )
            cs_chunks = _split_text_for_retrieval(cs_source)
            pair_count = max(len(ru_chunks), len(cs_chunks))
            for idx in range(pair_count):
                ru_text = ru_chunks[idx] if idx < len(ru_chunks) else ru_chunks[-1]
                cs_text = cs_chunks[idx] if idx < len(cs_chunks) else cs_chunks[-1]
                pair_key = f"{doc.case_id}|{doc.doc_id}|{page.page_number}|{idx}"
                ru_id = _make_point_id(
                    case_id=doc.case_id, doc_id=doc.doc_id, language="ru", page=page.page_number, chunk_index=idx
                )
                cs_id = _make_point_id(
                    case_id=doc.case_id, doc_id=doc.doc_id, language="cs", page=page.page_number, chunk_index=idx
                )
                base_payload = {
                    "case_id": doc.case_id,
                    "doc_id": doc.doc_id,
                    "primary_document_id": doc.primary_document_id,
                    "document_title": doc.document_title,
                    "document_type": doc.document_type,
                    "document_date": doc.document_date,
                    "document_role": doc.document_role,
                    "document_number": doc.document_number,
                    "case_number": doc.case_number,
                    "document_kind": doc.document_kind,
                    "logical_index": doc.logical_index,
                    "chunk_index": idx,
                    "page_from": page.page_number,
                    "page_to": page.page_number,
                    "pair_key": pair_key,
                }
                ru_rows.append(
                    {
                        "point_id": ru_id,
                        "payload": {
                            **base_payload,
                            "language": "ru",
                            "sibling_point_id": cs_id,
                            "translation_source": "original_ru",
                            "text": ru_text,
                        },
                    }
                )
                cs_rows.append(
                    {
                        "point_id": cs_id,
                        "payload": {
                            **base_payload,
                            "language": "cs",
                            "sibling_point_id": ru_id,
                            "translation_source": "fallback_ru" if not page.text_cs else "validated_cs",
                            "text": cs_text,
                        },
                    }
                )
    return ru_rows, cs_rows, fallback_pages


def _ensure_collection(client: QdrantClient, collection: str, vector_size: int) -> None:
    if client.collection_exists(collection):
        info = client.get_collection(collection)
        vectors = info.config.params.vectors
        actual_size = None
        if isinstance(vectors, dict):
            v = next(iter(vectors.values()))
            actual_size = int(v.size)
        elif hasattr(vectors, "size"):
            actual_size = int(vectors.size)
        if actual_size is not None and actual_size != vector_size:
            raise CaseIndexingError(
                f"Collection '{collection}' exists with vector size {actual_size}, "
                f"but embedding size is {vector_size}."
            )
        return
    client.create_collection(
        collection_name=collection,
        vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
    )


def _delete_case_points(client: QdrantClient, collection: str, case_id: str) -> None:
    filt = models.Filter(must=[models.FieldCondition(key="case_id", match=models.MatchValue(value=case_id))])
    client.delete(collection_name=collection, points_selector=models.FilterSelector(filter=filt), wait=True)


def _upsert_rows(
    client: QdrantClient,
    embedding_service: EmbeddingService,
    collection: str,
    rows: list[dict[str, Any]],
    batch_size: int,
) -> int:
    total = 0
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        vectors = embedding_service.embed_documents([str(r["payload"]["text"]) for r in batch])
        points = [
            models.PointStruct(id=r["point_id"], vector=v, payload=r["payload"])
            for r, v in zip(batch, vectors, strict=True)
        ]
        client.upsert(collection_name=collection, points=points, wait=True)
        total += len(points)
    return total


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_case_indexing(
    *,
    case_id: str,
    case_root: Path,
    validated_source: Path,
    qdrant_url: str,
    qdrant_api_key: str | None,
    collection_ru: str,
    collection_cs: str,
    embedding_service: EmbeddingService,
    batch_size: int,
    allow_cz_fallback_from_ru: bool,
    exclude_logical_indexes: set[int] | None = None,
) -> dict[str, Any]:
    ts = _now_utc()
    layout = ensure_case_layout(case_root)
    payload = _load_json(validated_source)
    docs = load_case_documents(payload, case_id)
    excluded = sorted(exclude_logical_indexes or set())
    if excluded:
        docs_before = len(docs)
        docs = [d for d in docs if d.logical_index not in exclude_logical_indexes]
        removed = docs_before - len(docs)
        if not docs:
            raise CaseIndexingError("All documents were excluded by exclude_logical_indexes filter.")
    else:
        removed = 0
    ru_rows, cs_rows, fallback_pages = build_chunk_rows(
        docs,
        allow_cz_fallback_from_ru=allow_cz_fallback_from_ru,
    )
    if not ru_rows:
        raise CaseIndexingError("No RU chunks were generated from validated JSON.")
    if not cs_rows:
        raise CaseIndexingError("No CZ chunks were generated from validated JSON.")

    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key, timeout=120)
    _ensure_collection(client, collection_ru, embedding_service.dimension)
    _ensure_collection(client, collection_cs, embedding_service.dimension)
    _delete_case_points(client, collection_ru, case_id)
    _delete_case_points(client, collection_cs, case_id)
    ru_written = _upsert_rows(client, embedding_service, collection_ru, ru_rows, batch_size)
    cs_written = _upsert_rows(client, embedding_service, collection_cs, cs_rows, batch_size)

    page_count = sum(len(d.pages) for d in docs)
    manifest = {
        "schema_version": "case_index_manifest.v1",
        "case_id": case_id,
        "timestamp_utc": ts,
        "validated_source": str(validated_source),
        "collections": {"ru": collection_ru, "cs": collection_cs},
        "counts": {
            "document_count": len(docs),
            "page_count": page_count,
            "ru_chunks": ru_written,
            "cs_chunks": cs_written,
            "chunk_total": ru_written + cs_written,
        },
        "status": "ok",
        "excluded_logical_indexes": excluded,
        "excluded_document_count": removed,
        "warnings": (
            [f"CZ fallback from RU used on {fallback_pages} pages (smoke mode)."] if fallback_pages else []
        ),
        "sample_payload_preview": {
            "ru": ru_rows[0]["payload"],
            "cs": cs_rows[0]["payload"],
        },
    }
    report = {
        **manifest,
        "storage_layout": {k: str(v) for k, v in layout.items()},
        "naming": {
            "validated_json": _canonical_doc_filename(case_id),
            "manifest": _canonical_manifest_filename(case_id),
            "indexing_report": _canonical_report_filename(case_id),
        },
    }
    _write_json(layout["manifests"] / _canonical_manifest_filename(case_id), manifest)
    _write_json(layout["indexing"] / _canonical_report_filename(case_id), report)
    _write_json(
        layout["logs"] / f"case_{case_id}_indexing_log_{ts}.json",
        {"timestamp_utc": ts, "status": "ok", "manifest_file": _canonical_manifest_filename(case_id)},
    )
    return report
