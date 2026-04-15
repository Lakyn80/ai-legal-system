from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as standalone script from backend/
if __name__ == "__main__":
    _root = Path(__file__).resolve().parents[1]
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from app.core.config import get_settings
from app.modules.common.embeddings.provider import EmbeddingService
from app.modules.russia.indexing.case_indexing import (
    CaseIndexingError,
    _canonical_doc_filename,
    _load_jsonl,
    _safe_case_id,
    build_validated_from_legacy_ru_jsonl,
    ensure_case_layout,
    run_case_indexing,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Production case indexing pipeline: validated case JSON -> RU/CZ chunking -> "
            "Qdrant collections -> indexing manifest."
        )
    )
    parser.add_argument("--case-id", required=True, help="Stable case UUID.")
    parser.add_argument(
        "--storage-root",
        type=Path,
        default=Path("storage/cases"),
        help="Root for stable case storage layout (default: backend/storage/cases).",
    )
    parser.add_argument(
        "--source-json",
        type=Path,
        default=None,
        help=(
            "Path to canonical validated case JSON. "
            "Default resolution: <storage-root>/<case_id>/synthesis/case_<case_id>_validated.json"
        ),
    )
    parser.add_argument(
        "--legacy-ru-docs-jsonl",
        type=Path,
        default=None,
        help=(
            "Optional migration helper: build canonical validated JSON from legacy RU docs JSONL "
            "(for bootstrap only)."
        ),
    )
    parser.add_argument(
        "--write-bootstrap-validated",
        action="store_true",
        help="Write/overwrite canonical validated JSON when --legacy-ru-docs-jsonl is provided.",
    )
    parser.add_argument(
        "--allow-cz-fallback-from-ru",
        action="store_true",
        help=(
            "SMOKE-ONLY MODE: if CZ translation text is missing in source JSON, "
            "mirror RU text into CZ layer."
        ),
    )
    parser.add_argument("--collection-ru", default="legal_case_chunks_ru_clean")
    parser.add_argument("--collection-cs", default="legal_case_chunks_cs_clean")
    parser.add_argument("--qdrant-url", default="")
    parser.add_argument("--qdrant-api-key", default="")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument(
        "--exclude-logical-indexes",
        default="",
        help=(
            "Comma-separated logical_index list to exclude from indexing "
            "(used for deterministic decontamination when audit confirms foreign docs)."
        ),
    )
    args = parser.parse_args()

    case_id = _safe_case_id(args.case_id)
    case_root = args.storage_root / case_id
    layout = ensure_case_layout(case_root)
    validated_path = args.source_json or (layout["synthesis"] / _canonical_doc_filename(case_id))

    if args.legacy_ru_docs_jsonl:
        legacy_rows = _load_jsonl(args.legacy_ru_docs_jsonl)
        canonical_payload = build_validated_from_legacy_ru_jsonl(case_id, legacy_rows)
        if args.write_bootstrap_validated:
            validated_path.write_text(
                json.dumps(canonical_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    settings = get_settings()
    qdrant_url = args.qdrant_url or settings.qdrant_url
    qdrant_api_key = args.qdrant_api_key or (settings.qdrant_api_key or None)
    embedding_service = EmbeddingService(
        model_name=settings.embedding_model,
        provider_name=settings.embedding_provider,
        fallback_provider_name=settings.embedding_fallback_provider,
        hash_dimension=settings.embedding_hash_dimension,
    )

    exclude_logical_indexes: set[int] = set()
    if args.exclude_logical_indexes.strip():
        try:
            exclude_logical_indexes = {
                int(token.strip())
                for token in args.exclude_logical_indexes.split(",")
                if token.strip()
            }
        except Exception as exc:  # noqa: BLE001
            print("[index_case_to_qdrant] ERROR: --exclude-logical-indexes must be comma-separated integers.")
            return 2

    try:
        report = run_case_indexing(
            case_id=case_id,
            case_root=case_root,
            validated_source=validated_path,
            qdrant_url=qdrant_url,
            qdrant_api_key=qdrant_api_key,
            collection_ru=args.collection_ru,
            collection_cs=args.collection_cs,
            embedding_service=embedding_service,
            batch_size=args.batch_size,
            allow_cz_fallback_from_ru=args.allow_cz_fallback_from_ru,
            exclude_logical_indexes=exclude_logical_indexes,
        )
    except CaseIndexingError as exc:
        print(f"[index_case_to_qdrant] ERROR: {exc}")
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"[index_case_to_qdrant] UNEXPECTED ERROR: {exc}")
        return 3

    print("Case indexing completed.")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
