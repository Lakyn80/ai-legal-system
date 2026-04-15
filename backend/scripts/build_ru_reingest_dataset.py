"""
Transform RU-only case synthesis markdown into canonical re-ingest datasets.

Input:
  case_synthesis_ru_only_<case_short>_<timestamp>.md

Output (under backend/artifacts/llm_synthesis/reingest/):
  - case_ru_documents_<case_short>_<timestamp>.jsonl
  - case_ru_documents_<case_short>_<timestamp>.parquet
  - case_ru_chunks_<case_short>_<timestamp>.jsonl
  - case_ru_chunks_<case_short>_<timestamp>.parquet
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


DOC_HEADER_RE = re.compile(
    r"^###\s+Dokument\s+(?P<doc_seq>\d+)\s+\(logicky index #(?P<logical_index>\d+)\s+\|\s+datum:\s*(?P<date>[^)]+)\)$"
)
PAGE_RE = re.compile(r"^STRANA\s+(?P<page>\d+)$")
CASE_RE = re.compile(r"^#\s*Pripad:\s*(?P<case_id>[a-f0-9-]+)\s*$", re.IGNORECASE)
ARTIFACT_RE = re.compile(
    r"case_synthesis_ru_only_(?P<case_short>[a-f0-9]+)_(?P<timestamp>\d{8}T\d{6}Z)\.md$",
    re.IGNORECASE,
)

CHUNK_MAX_CHARS = 2200
CHUNK_OVERLAP_CHARS = 250
CHUNK_UUID_NAMESPACE = uuid.NAMESPACE_URL


@dataclass
class PageRecord:
    page_number: int
    text: str


@dataclass
class DocBuilder:
    document_seq: int
    logical_index: int
    document_date: str | None
    document_title: str
    pages: list[PageRecord]


def _guess_document_type(title: str, full_text: str) -> str:
    t = f"{title}\n{full_text}".lower()
    if any(k in t for k in ("решение суда", "судья", "определение суда", "постановил")):
        return "judgment"
    if any(k in t for k in ("апелляцион", "кассацион", "жалоб")):
        return "appeal"
    if any(k in t for k in ("исковое заявление", "иск ", "истец")):
        return "claim"
    if any(k in t for k in ("дополнения к исковому", "возражени", "объяснения сторон", "ходатайств")):
        return "party_submission"
    if any(k in t for k in ("протокол", "почтов", "извещени", "повестк", "уведомлен")):
        return "procedural_document"
    if any(k in t for k in ("квитанц", "справк", "доказательств", "приложени")):
        return "evidence"
    if any(k in t for k in ("приказ", "определил", "распоряжени")):
        return "order"
    return "other_relevant_document"


def _guess_document_role(document_type: str, full_text: str) -> str:
    if document_type in {"judgment", "order"}:
        return "court"
    txt = full_text.lower()
    if "истец" in txt:
        return "plaintiff"
    if "ответчик" in txt:
        return "defendant"
    return "other"


def _extract_case_id(lines: list[str]) -> str:
    for line in lines[:100]:
        m = CASE_RE.match(line.strip())
        if m:
            return m.group("case_id")
    raise ValueError("Case ID not found in markdown header (# Pripad: ...).")


def _extract_artifact_parts(path: Path) -> tuple[str, str]:
    m = ARTIFACT_RE.search(path.name)
    if not m:
        raise ValueError(
            "Input filename must match case_synthesis_ru_only_<case_short>_<timestamp>.md"
        )
    return m.group("case_short"), m.group("timestamp")


def _parse_documents(raw_text: str) -> list[DocBuilder]:
    lines = raw_text.splitlines()
    docs: list[DocBuilder] = []
    current_doc: DocBuilder | None = None
    current_page_number: int | None = None
    current_page_lines: list[str] = []

    def flush_page() -> None:
        nonlocal current_page_lines, current_page_number, current_doc
        if current_doc is None or current_page_number is None:
            current_page_lines = []
            return
        text = "\n".join(current_page_lines).rstrip("\n")
        current_doc.pages.append(PageRecord(page_number=current_page_number, text=text))
        current_page_lines = []
        current_page_number = None

    def flush_doc() -> None:
        nonlocal current_doc
        if current_doc is None:
            return
        flush_page()
        docs.append(current_doc)
        current_doc = None

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        header = DOC_HEADER_RE.match(line.strip())
        if header:
            flush_doc()
            d_raw = header.group("date").strip()
            doc_date = d_raw if d_raw and d_raw.lower() != "null" else None
            current_doc = DocBuilder(
                document_seq=int(header.group("doc_seq")),
                logical_index=int(header.group("logical_index")),
                document_date=doc_date,
                document_title=f"Dokument {int(header.group('doc_seq')):03d}",
                pages=[],
            )
            current_page_number = None
            current_page_lines = []
            continue

        if current_doc is None:
            continue

        page_match = PAGE_RE.match(line.strip())
        if page_match:
            flush_page()
            current_page_number = int(page_match.group("page"))
            current_page_lines = []
            continue

        if line.strip() == "---":
            flush_doc()
            continue

        if current_page_number is not None:
            current_page_lines.append(line)

    flush_doc()
    return docs


def _document_row(
    *,
    case_id: str,
    source_artifact: str,
    doc: DocBuilder,
) -> dict[str, Any]:
    pages = [{"page_number": p.page_number, "text": p.text} for p in doc.pages]
    full_text = "\n\n".join(p.text for p in doc.pages)
    document_type = _guess_document_type(doc.document_title, full_text)
    document_role = _guess_document_role(document_type, full_text)
    return {
        "case_id": case_id,
        "doc_id": f"case::{case_id}::doc::{doc.logical_index}",
        "primary_document_id": "",
        "logical_index": doc.logical_index,
        "document_seq": doc.document_seq,
        "document_date": doc.document_date,
        "document_title": doc.document_title,
        "document_type": document_type,
        "document_role": document_role,
        "source_artifact": source_artifact,
        "language": "ru",
        "pages": pages,
        "full_text": full_text,
    }


def _split_page_text(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        window = text[start:end]
        if end < len(text):
            split_at = max(window.rfind("\n\n"), window.rfind("\n"))
            if split_at > int(max_chars * 0.45):
                end = start + split_at
                window = text[start:end]
        parts.append(window)
        if end >= len(text):
            break
        start = max(end - overlap_chars, start + 1)
    return parts


def _build_chunks(document_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for doc in document_rows:
        chunk_index = 0
        for page in doc["pages"]:
            page_number = int(page["page_number"])
            page_text = page["text"] or ""
            for part in _split_page_text(page_text, CHUNK_MAX_CHARS, CHUNK_OVERLAP_CHARS):
                chunk_key = f"{doc['doc_id']}::{page_number}::{chunk_index}"
                chunk_id = str(uuid.uuid5(CHUNK_UUID_NAMESPACE, chunk_key))
                chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "chunk_key": chunk_key,
                        "chunk_index": chunk_index,
                        "case_id": doc["case_id"],
                        "doc_id": doc["doc_id"],
                        "logical_index": doc["logical_index"],
                        "document_seq": doc["document_seq"],
                        "primary_document_id": doc.get("primary_document_id", ""),
                        "document_type": doc.get("document_type", "other_relevant_document"),
                        "document_date": doc.get("document_date"),
                        "document_role": doc.get("document_role", ""),
                        "document_title": doc.get("document_title", ""),
                        "page_from": page_number,
                        "page_to": page_number,
                        "language": "ru",
                        "source_artifact": doc["source_artifact"],
                        "text": part,
                    }
                )
                chunk_index += 1
    return chunks


def _write_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_parquet(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build RU case re-ingest datasets from markdown artifact.")
    parser.add_argument("--input-md", type=Path, required=True, help="Path to case_synthesis_ru_only_*.md")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/llm_synthesis/reingest"),
        help="Output directory for documents/chunks datasets",
    )
    parser.add_argument(
        "--case-id",
        type=str,
        default="",
        help="Optional explicit case_id override (otherwise extracted from markdown header).",
    )
    args = parser.parse_args()

    md_path = args.input_md
    if not md_path.exists():
        raise FileNotFoundError(f"Input file not found: {md_path}")

    raw_text = md_path.read_text(encoding="utf-8")
    lines = raw_text.splitlines()
    case_id = args.case_id.strip() or _extract_case_id(lines)
    case_short, timestamp = _extract_artifact_parts(md_path)
    source_artifact = md_path.name

    docs = _parse_documents(raw_text)
    document_rows = [_document_row(case_id=case_id, source_artifact=source_artifact, doc=doc) for doc in docs]
    chunk_rows = _build_chunks(document_rows)

    docs_jsonl = args.output_dir / f"case_ru_documents_{case_short}_{timestamp}.jsonl"
    docs_parquet = args.output_dir / f"case_ru_documents_{case_short}_{timestamp}.parquet"
    chunks_jsonl = args.output_dir / f"case_ru_chunks_{case_short}_{timestamp}.jsonl"
    chunks_parquet = args.output_dir / f"case_ru_chunks_{case_short}_{timestamp}.parquet"

    _write_jsonl(document_rows, docs_jsonl)
    _write_parquet(document_rows, docs_parquet)
    _write_jsonl(chunk_rows, chunks_jsonl)
    _write_parquet(chunk_rows, chunks_parquet)

    print("RU re-ingest dataset created:")
    print(f"  case_id: {case_id}")
    print(f"  documents: {len(document_rows)}")
    print(f"  chunks: {len(chunk_rows)}")
    print(f"  docs jsonl: {docs_jsonl}")
    print(f"  docs parquet: {docs_parquet}")
    print(f"  chunks jsonl: {chunks_jsonl}")
    print(f"  chunks parquet: {chunks_parquet}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())

