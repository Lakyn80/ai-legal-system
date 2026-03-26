import argparse
import json
from pathlib import Path

from app.core.dependencies import get_document_service, get_ingestion_service
from app.core.enums import CountryEnum, DomainEnum


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import a local legal document into storage and Qdrant.")
    parser.add_argument("file_path", type=Path, help="Path to the local file inside the runtime environment.")
    parser.add_argument("--country", type=CountryEnum, choices=list(CountryEnum), required=True)
    parser.add_argument("--domain", type=DomainEnum, choices=list(DomainEnum), required=True)
    parser.add_argument("--document-type", required=True)
    parser.add_argument("--source")
    parser.add_argument("--case-id")
    parser.add_argument("--tags", default="", help="Comma-separated tags.")
    parser.add_argument("--skip-ingest", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    tags = [item.strip() for item in args.tags.split(",") if item.strip()]

    document_service = get_document_service()
    ingestion_service = get_ingestion_service()

    record = document_service.import_local_document(
        file_path=args.file_path,
        country=args.country,
        domain=args.domain,
        document_type=args.document_type,
        source=args.source,
        case_id=args.case_id,
        tags=tags,
    )

    output: dict[str, object] = {"document": record.model_dump(mode="json")}
    if not args.skip_ingest:
        [result] = ingestion_service.ingest_documents([record.id])
        output["ingestion"] = result.model_dump(mode="json")

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
