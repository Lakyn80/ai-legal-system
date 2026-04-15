"""
Index RU re-ingest chunk dataset into a dedicated clean Qdrant collection.

Input:
  - Parquet or JSONL produced by build_ru_reingest_dataset.py

Output:
  - Upserted points in Qdrant collection (default: legal_case_chunks_ru_clean)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pyarrow.parquet as pq
from qdrant_client import QdrantClient
from qdrant_client.http import models

# Allow running as a standalone script from backend/
if __name__ == "__main__":
    _root = Path(__file__).resolve().parents[1]
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from app.core.config import get_settings
from app.modules.common.embeddings.provider import EmbeddingService


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows


def _load_parquet(path: Path) -> list[dict]:
    table = pq.read_table(path)
    return table.to_pylist()


def _load_rows(path: Path) -> list[dict]:
    if path.suffix.lower() == ".jsonl":
        return _load_jsonl(path)
    if path.suffix.lower() == ".parquet":
        return _load_parquet(path)
    raise ValueError(f"Unsupported input format: {path.suffix}")


def _ensure_collection(client: QdrantClient, collection: str, dim: int) -> None:
    if client.collection_exists(collection):
        return
    client.create_collection(
        collection_name=collection,
        vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Index RU chunk dataset to dedicated clean Qdrant collection.")
    parser.add_argument("--chunks", type=Path, required=True, help="Path to chunks .jsonl or .parquet")
    parser.add_argument("--collection", type=str, default="legal_case_chunks_ru_clean")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--qdrant-url", type=str, default="")
    parser.add_argument("--qdrant-api-key", type=str, default="")
    args = parser.parse_args()

    settings = get_settings()
    qdrant_url = args.qdrant_url or settings.qdrant_url
    qdrant_api_key = args.qdrant_api_key or (settings.qdrant_api_key or None)

    rows = _load_rows(args.chunks)
    if not rows:
        raise ValueError("Chunk dataset is empty.")

    embedding_service = EmbeddingService(
        model_name=settings.embedding_model,
        provider_name=settings.embedding_provider,
        fallback_provider_name=settings.embedding_fallback_provider,
        hash_dimension=settings.embedding_hash_dimension,
    )
    dim = embedding_service.dimension

    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key, timeout=120)
    _ensure_collection(client, args.collection, dim)

    total = 0
    for i in range(0, len(rows), args.batch_size):
        batch = rows[i : i + args.batch_size]
        texts = [str(row.get("text", "")) for row in batch]
        vectors = embedding_service.embed_documents(texts)
        points: list[models.PointStruct] = []
        for row, vec in zip(batch, vectors, strict=True):
            chunk_id = str(row["chunk_id"])
            payload = {
                "chunk_id": chunk_id,
                "chunk_key": row.get("chunk_key"),
                "chunk_index": row.get("chunk_index"),
                "case_id": row.get("case_id"),
                "doc_id": row.get("doc_id"),
                "logical_index": row.get("logical_index"),
                "document_seq": row.get("document_seq"),
                "primary_document_id": row.get("primary_document_id", ""),
                "document_type": row.get("document_type", "other_relevant_document"),
                "document_date": row.get("document_date"),
                "document_role": row.get("document_role", ""),
                "document_title": row.get("document_title", ""),
                "page_from": row.get("page_from"),
                "page_to": row.get("page_to"),
                "language": row.get("language", "ru"),
                "source_artifact": row.get("source_artifact"),
                "text": row.get("text", ""),
            }
            points.append(models.PointStruct(id=chunk_id, vector=vec, payload=payload))

        client.upsert(collection_name=args.collection, points=points)
        total += len(points)

    print("Qdrant indexing complete:")
    print(f"  collection: {args.collection}")
    print(f"  qdrant_url: {qdrant_url}")
    print(f"  points_upserted: {total}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())

