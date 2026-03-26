import argparse
import json

from app.core.dependencies import get_reindex_service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reindex all stored documents into a new Qdrant collection.")
    parser.add_argument(
        "--delete-previous-collection",
        action="store_true",
        help="Delete the previously active collection after the alias switch succeeds.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service = get_reindex_service()
    result = service.reindex(delete_previous_collection=args.delete_previous_collection)
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
