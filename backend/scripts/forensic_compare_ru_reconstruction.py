"""
Forensic end-to-end comparison:
canonical RU markdown vs reconstructed documents from Qdrant clean collection.

Outputs:
  - forensic_compare_report.json
  - forensic_compare_report.md
  - diffs/*.diff
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm


DOC_HEADER_RE = re.compile(
    r"^###\s+Dokument\s+(?P<doc_seq>\d+)\s+\(logicky index #(?P<logical_index>\d+)\s+\|\s+datum:\s*(?P<date>[^)]+)\)$"
)
PAGE_RE = re.compile(r"^STRANA\s+(?P<page>\d+)$")


@dataclass
class PageData:
    page_number: int
    text: str


@dataclass
class DocData:
    logical_index: int
    document_seq: int
    pages: dict[int, PageData]
    full_text: str


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_text(text: str) -> str:
    # Conservative normalization only:
    # 1) CRLF/CR -> LF
    # 2) trim trailing whitespace on each line
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in t.split("\n")]
    return "\n".join(lines)


def overlap_merge(base: str, nxt: str, max_overlap: int = 600) -> str:
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


def parse_canonical(md_path: Path) -> dict[int, DocData]:
    raw = md_path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    docs: dict[int, DocData] = {}
    current_doc_idx: int | None = None
    current_doc_seq: int | None = None
    current_pages: dict[int, PageData] = {}
    current_page_num: int | None = None
    current_page_lines: list[str] = []

    def flush_page() -> None:
        nonlocal current_page_num, current_page_lines, current_pages
        if current_page_num is None:
            current_page_lines = []
            return
        current_pages[current_page_num] = PageData(
            page_number=current_page_num,
            text="\n".join(current_page_lines).rstrip("\n"),
        )
        current_page_num = None
        current_page_lines = []

    def flush_doc() -> None:
        nonlocal current_doc_idx, current_doc_seq, current_pages
        if current_doc_idx is None or current_doc_seq is None:
            return
        flush_page()
        full_text = "\n\n".join(current_pages[k].text for k in sorted(current_pages))
        docs[current_doc_idx] = DocData(
            logical_index=current_doc_idx,
            document_seq=current_doc_seq,
            pages=current_pages,
            full_text=full_text,
        )
        current_doc_idx = None
        current_doc_seq = None
        current_pages = {}

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        m = DOC_HEADER_RE.match(line.strip())
        if m:
            flush_doc()
            current_doc_idx = int(m.group("logical_index"))
            current_doc_seq = int(m.group("doc_seq"))
            continue

        if current_doc_idx is None:
            continue

        pm = PAGE_RE.match(line.strip())
        if pm:
            flush_page()
            current_page_num = int(pm.group("page"))
            continue

        if line.strip() == "---":
            flush_doc()
            continue

        if current_page_num is not None:
            current_page_lines.append(line)

    flush_doc()
    return docs


def reconstruct_from_qdrant(case_id: str, qdrant_url: str, collection: str, api_key: str | None) -> dict[int, DocData]:
    client = QdrantClient(url=qdrant_url, api_key=api_key, timeout=60)
    filt = qm.Filter(must=[qm.FieldCondition(key="case_id", match=qm.MatchValue(value=case_id))])
    chunks: list[dict[str, Any]] = []
    offset = None
    while True:
        points, next_offset = client.scroll(
            collection_name=collection,
            scroll_filter=filt,
            with_payload=True,
            with_vectors=False,
            limit=1024,
            offset=offset,
        )
        chunks.extend([p.payload for p in points if p.payload])
        if next_offset is None:
            break
        offset = next_offset

    by_doc: dict[int, list[dict[str, Any]]] = {}
    for ch in chunks:
        raw_idx = ch.get("logical_index")
        if raw_idx is None:
            continue
        try:
            idx = int(raw_idx)
        except Exception:
            continue
        by_doc.setdefault(idx, []).append(ch)

    out: dict[int, DocData] = {}
    for idx, rows in by_doc.items():
        # page-level grouping and ordering
        by_page: dict[int, list[dict[str, Any]]] = {}
        for r in rows:
            page = int(r.get("page_from") or 0)
            if page <= 0:
                continue
            by_page.setdefault(page, []).append(r)

        pages: dict[int, PageData] = {}
        for page_num, page_rows in by_page.items():
            page_rows.sort(key=lambda r: (int(r.get("page_from") or 0), int(r.get("page_to") or 0), int(r.get("chunk_index") or 0)))
            text = ""
            for pr in page_rows:
                text = overlap_merge(text, str(pr.get("text") or ""))
            pages[page_num] = PageData(page_number=page_num, text=text)

        full_text = "\n\n".join(pages[k].text for k in sorted(pages))
        seq = int(rows[0].get("document_seq") or 0)
        out[idx] = DocData(logical_index=idx, document_seq=seq, pages=pages, full_text=full_text)
    return out


def char_diff_count(a: str, b: str) -> int:
    sm = difflib.SequenceMatcher(None, a, b)
    total = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            total += max(i2 - i1, j2 - j1)
    return total


def write_diff(path: Path, a: str, b: str, from_name: str, to_name: str) -> None:
    diff = difflib.unified_diff(
        a.splitlines(keepends=True),
        b.splitlines(keepends=True),
        fromfile=from_name,
        tofile=to_name,
        n=3,
    )
    path.write_text("".join(diff), encoding="utf-8")


def reason_for_mismatch(canon: str, recon: str, canon_norm: str, recon_norm: str) -> str:
    if canon_norm == recon_norm and canon != recon:
        return "whitespace_normalization_only"
    if canon and recon and canon in recon and len(recon) > len(canon):
        return "duplication_or_addition"
    if canon and recon and recon in canon and len(canon) > len(recon):
        return "loss_or_missing_part"
    return "content_difference"


def main() -> int:
    parser = argparse.ArgumentParser(description="Forensic compare canonical RU source vs Qdrant reconstruction.")
    parser.add_argument("--canonical-md", type=Path, required=True)
    parser.add_argument("--case-id", type=str, required=True)
    parser.add_argument("--qdrant-url", type=str, default="http://localhost:6335")
    parser.add_argument("--qdrant-api-key", type=str, default="")
    parser.add_argument("--collection", type=str, default="legal_case_chunks_ru_clean")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/llm_synthesis/forensic_verify"),
    )
    args = parser.parse_args()

    canonical = parse_canonical(args.canonical_md)
    recon = reconstruct_from_qdrant(
        case_id=args.case_id,
        qdrant_url=args.qdrant_url,
        collection=args.collection,
        api_key=args.qdrant_api_key or None,
    )

    all_doc_ids = sorted(set(canonical.keys()) | set(recon.keys()))
    diffs_dir = args.output_dir / "diffs"
    diffs_dir.mkdir(parents=True, exist_ok=True)

    doc_raw_match = 0
    doc_norm_match = 0
    page_raw_match = 0
    page_norm_match = 0
    total_pages_canonical = sum(len(d.pages) for d in canonical.values())
    total_pages_recon = sum(len(d.pages) for d in recon.values())

    mismatches: list[dict[str, Any]] = []

    for doc_idx in all_doc_ids:
        cdoc = canonical.get(doc_idx)
        rdoc = recon.get(doc_idx)
        if cdoc is None or rdoc is None:
            mismatches.append(
                {
                    "level": "document",
                    "logical_index": doc_idx,
                    "raw_mismatch": True,
                    "normalized_mismatch": True,
                    "char_diff_count": None,
                    "reason": "missing_document_in_one_side",
                }
            )
            continue

        c_raw = cdoc.full_text
        r_raw = rdoc.full_text
        c_norm = normalize_text(c_raw)
        r_norm = normalize_text(r_raw)
        if sha256(c_raw) == sha256(r_raw):
            doc_raw_match += 1
        if sha256(c_norm) == sha256(r_norm):
            doc_norm_match += 1
        if sha256(c_raw) != sha256(r_raw) or sha256(c_norm) != sha256(r_norm):
            diff_path = diffs_dir / f"doc_{doc_idx}.diff"
            write_diff(diff_path, c_raw, r_raw, f"canonical_doc_{doc_idx}", f"reconstructed_doc_{doc_idx}")
            mismatches.append(
                {
                    "level": "document",
                    "logical_index": doc_idx,
                    "raw_mismatch": sha256(c_raw) != sha256(r_raw),
                    "normalized_mismatch": sha256(c_norm) != sha256(r_norm),
                    "char_diff_count": char_diff_count(c_raw, r_raw),
                    "reason": reason_for_mismatch(c_raw, r_raw, c_norm, r_norm),
                    "diff_file": str(diff_path),
                    "canonical_raw_sha256": sha256(c_raw),
                    "reconstructed_raw_sha256": sha256(r_raw),
                    "canonical_norm_sha256": sha256(c_norm),
                    "reconstructed_norm_sha256": sha256(r_norm),
                }
            )

        all_pages = sorted(set(cdoc.pages.keys()) | set(rdoc.pages.keys()))
        for page in all_pages:
            cp = cdoc.pages.get(page)
            rp = rdoc.pages.get(page)
            if cp is None or rp is None:
                mismatches.append(
                    {
                        "level": "page",
                        "logical_index": doc_idx,
                        "page_number": page,
                        "raw_mismatch": True,
                        "normalized_mismatch": True,
                        "char_diff_count": None,
                        "reason": "missing_page_in_one_side",
                    }
                )
                continue
            cpr = cp.text
            rpr = rp.text
            cpn = normalize_text(cpr)
            rpn = normalize_text(rpr)
            if sha256(cpr) == sha256(rpr):
                page_raw_match += 1
            if sha256(cpn) == sha256(rpn):
                page_norm_match += 1
            if sha256(cpr) != sha256(rpr) or sha256(cpn) != sha256(rpn):
                diff_path = diffs_dir / f"doc_{doc_idx}_page_{page}.diff"
                write_diff(
                    diff_path,
                    cpr,
                    rpr,
                    f"canonical_doc_{doc_idx}_page_{page}",
                    f"reconstructed_doc_{doc_idx}_page_{page}",
                )
                mismatches.append(
                    {
                        "level": "page",
                        "logical_index": doc_idx,
                        "page_number": page,
                        "raw_mismatch": sha256(cpr) != sha256(rpr),
                        "normalized_mismatch": sha256(cpn) != sha256(rpn),
                        "char_diff_count": char_diff_count(cpr, rpr),
                        "reason": reason_for_mismatch(cpr, rpr, cpn, rpn),
                        "diff_file": str(diff_path),
                        "canonical_raw_sha256": sha256(cpr),
                        "reconstructed_raw_sha256": sha256(rpr),
                        "canonical_norm_sha256": sha256(cpn),
                        "reconstructed_norm_sha256": sha256(rpn),
                    }
                )

    total_docs_canonical = len(canonical)
    total_docs_recon = len(recon)
    total_pages_compared = sum(
        1
        for d in set(canonical.keys()) & set(recon.keys())
        for _ in (set(canonical[d].pages.keys()) & set(recon[d].pages.keys()))
    )
    verdict = (
        "ANO — reconstructed dataset je 100% shodný s canonical RU source"
        if (
            total_docs_canonical == total_docs_recon
            and total_pages_canonical == total_pages_recon
            and doc_raw_match == total_docs_canonical
            and doc_norm_match == total_docs_canonical
            and page_raw_match == total_pages_canonical
            and page_norm_match == total_pages_canonical
            and not mismatches
        )
        else "NE — reconstructed dataset není 100% shodný s canonical RU source"
    )

    report = {
        "verdict": verdict,
        "summary": {
            "canonical_documents": total_docs_canonical,
            "reconstructed_documents": total_docs_recon,
            "canonical_pages": total_pages_canonical,
            "reconstructed_pages": total_pages_recon,
            "exact_raw_hash_doc_matches": f"{doc_raw_match} / {total_docs_canonical}",
            "exact_normalized_hash_doc_matches": f"{doc_norm_match} / {total_docs_canonical}",
            "exact_raw_hash_page_matches": f"{page_raw_match} / {total_pages_canonical}",
            "exact_normalized_hash_page_matches": f"{page_norm_match} / {total_pages_canonical}",
            "pages_compared_intersection": total_pages_compared,
        },
        "normalization": {
            "rules": [
                "CRLF/CR normalized to LF",
                "Trailing whitespace trimmed per line",
            ]
        },
        "mismatches": mismatches,
    }

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "forensic_compare_report.json"
    md_path = out_dir / "forensic_compare_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        f"# Forensic Compare Report",
        "",
        f"**Verdikt:** {verdict}",
        "",
        "## Souhrn",
        "",
        f"- canonical documents: {total_docs_canonical}",
        f"- reconstructed documents: {total_docs_recon}",
        f"- canonical pages: {total_pages_canonical}",
        f"- reconstructed pages: {total_pages_recon}",
        f"- exact raw hash doc matches: {doc_raw_match} / {total_docs_canonical}",
        f"- exact normalized hash doc matches: {doc_norm_match} / {total_docs_canonical}",
        f"- exact raw hash page matches: {page_raw_match} / {total_pages_canonical}",
        f"- exact normalized hash page matches: {page_norm_match} / {total_pages_canonical}",
        "",
        "## Normalization",
        "",
        "- CRLF/CR -> LF",
        "- trim trailing whitespace per line",
        "",
        f"## Mismatches ({len(mismatches)})",
        "",
    ]
    if not mismatches:
        md_lines.append("No mismatches found.")
    else:
        for m in mismatches:
            if m["level"] == "document":
                md_lines.append(
                    f"- DOC logical_index={m.get('logical_index')} "
                    f"raw_mismatch={m.get('raw_mismatch')} "
                    f"norm_mismatch={m.get('normalized_mismatch')} "
                    f"char_diff={m.get('char_diff_count')} "
                    f"reason={m.get('reason')} "
                    f"diff={m.get('diff_file','')}"
                )
            else:
                md_lines.append(
                    f"- PAGE doc={m.get('logical_index')} page={m.get('page_number')} "
                    f"raw_mismatch={m.get('raw_mismatch')} "
                    f"norm_mismatch={m.get('normalized_mismatch')} "
                    f"char_diff={m.get('char_diff_count')} "
                    f"reason={m.get('reason')} "
                    f"diff={m.get('diff_file','')}"
                )
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    print(json.dumps({"report_json": str(json_path), "report_md": str(md_path), "verdict": verdict, "mismatch_count": len(mismatches)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

