import json
import logging
from datetime import UTC, datetime

import numpy as np
from redis import Redis
from redis.commands.search.field import NumericField, TagField, TextField, VectorField
from redis.commands.search.query import Query
from redis.exceptions import RedisError, ResponseError

from app.modules.common.cache.schemas import ExactCacheKeyContext, SemanticCacheEntry, SemanticCacheMatch

try:
    from redis.commands.search.indexDefinition import IndexDefinition, IndexType
except ModuleNotFoundError:
    from redis.commands.search.index_definition import IndexDefinition, IndexType


logger = logging.getLogger(__name__)


class RedisCacheClient:
    def __init__(self, url: str, enabled: bool) -> None:
        self.enabled = enabled
        self.url = url
        self._client = Redis.from_url(url, decode_responses=False) if enabled else None
        self._semantic_support_known: bool | None = None

    @property
    def semantic_support_known(self) -> bool | None:
        return self._semantic_support_known

    def get_json(self, key: str) -> dict | None:
        if not self._client:
            return None
        try:
            value = self._client.get(key)
        except RedisError as exc:
            logger.warning("Redis get failed for key %s: %s", key, exc)
            return None
        if value is None:
            return None
        return json.loads(self._decode_value(value))

    def set_json(self, key: str, payload: dict, ttl_seconds: int | None = None) -> bool:
        if not self._client:
            return False
        try:
            self._client.set(
                name=key,
                value=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                ex=ttl_seconds,
            )
            return True
        except RedisError as exc:
            logger.warning("Redis set failed for key %s: %s", key, exc)
            return False

    def ping(self) -> bool:
        if not self._client:
            return False
        try:
            return bool(self._client.ping())
        except RedisError:
            return False

    def delete_by_pattern(self, pattern: str, batch_size: int = 200) -> int:
        if not self._client:
            return 0
        total_deleted = 0
        cursor = 0
        try:
            while True:
                cursor, keys = self._client.scan(cursor=cursor, match=pattern, count=batch_size)
                if keys:
                    total_deleted += int(self._client.delete(*keys))
                if cursor == 0:
                    break
        except RedisError as exc:
            logger.warning("Redis delete by pattern failed for pattern %s: %s", pattern, exc)
            return total_deleted
        return total_deleted

    def semantic_search_supported(self) -> bool | None:
        if not self._client:
            return None
        if self._semantic_support_known is not None:
            return self._semantic_support_known
        try:
            self._client.execute_command("FT._LIST")
            self._semantic_support_known = True
            return True
        except ResponseError:
            self._semantic_support_known = False
            return False
        except RedisError:
            return None

    def ensure_semantic_index(self, index_name: str, prefix: str, vector_dim: int) -> bool:
        if not self._client:
            return False
        if self._semantic_support_known is False:
            return False
        try:
            self._client.ft(index_name).info()
            self._semantic_support_known = True
            return True
        except ResponseError as exc:
            if not self._is_missing_index_error(exc):
                return self._handle_semantic_error("Redis semantic index info failed", exc)
        except RedisError as exc:
            return self._handle_semantic_error("Redis semantic index info failed", exc)

        try:
            self._client.ft(index_name).create_index(
                fields=[
                    TextField("normalized_query"),
                    TagField("jurisdiction"),
                    TagField("domain"),
                    TagField("query_type"),
                    TagField("active_collection"),
                    TagField("corpus_fingerprint"),
                    TagField("embedding_fingerprint"),
                    TagField("response_schema_version"),
                    TagField("prompt_version"),
                    NumericField("created_at_ts"),
                    VectorField(
                        "embedding",
                        "HNSW",
                        {
                            "TYPE": "FLOAT32",
                            "DIM": vector_dim,
                            "DISTANCE_METRIC": "COSINE",
                            "INITIAL_CAP": 1000,
                            "M": 16,
                            "EF_CONSTRUCTION": 200,
                        },
                    ),
                ],
                definition=IndexDefinition(prefix=[prefix], index_type=IndexType.HASH),
            )
            self._semantic_support_known = True
            return True
        except ResponseError as exc:
            if "Index already exists" in str(exc):
                self._semantic_support_known = True
                return True
            return self._handle_semantic_error("Redis semantic index creation failed", exc)
        except RedisError as exc:
            return self._handle_semantic_error("Redis semantic index creation failed", exc)

    def search_semantic_entries(
        self,
        index_name: str,
        key_context: ExactCacheKeyContext,
        query_vector: list[float],
        top_k: int,
    ) -> list[SemanticCacheMatch]:
        if not self._client or self._semantic_support_known is False:
            return []
        try:
            filters = " ".join(
                [
                    f"@jurisdiction:{{{self._escape_tag(key_context.jurisdiction)}}}",
                    f"@domain:{{{self._escape_tag(key_context.domain)}}}",
                    f"@query_type:{{{self._escape_tag(key_context.query_type)}}}",
                    f"@active_collection:{{{self._escape_tag(key_context.active_collection)}}}",
                    f"@corpus_fingerprint:{{{self._escape_tag(key_context.corpus_fingerprint)}}}",
                    f"@embedding_fingerprint:{{{self._escape_tag(key_context.embedding_fingerprint)}}}",
                    f"@response_schema_version:{{{self._escape_tag(key_context.response_schema_version)}}}",
                    f"@prompt_version:{{{self._escape_tag(key_context.prompt_version or '__none__')}}}",
                ]
            )
            query = (
                Query(f"({filters})=>[KNN {top_k} @embedding $vector AS vector_score]")
                .sort_by("vector_score")
                .paging(0, top_k)
                .dialect(2)
                .return_fields(
                    "cache_key",
                    "normalized_query",
                    "jurisdiction",
                    "domain",
                    "query_type",
                    "active_collection",
                    "corpus_fingerprint",
                    "embedding_fingerprint",
                    "response_schema_version",
                    "prompt_version",
                    "document_ids",
                    "chunk_ids",
                    "response_payload",
                    "created_at",
                    "expires_at",
                    "vector_score",
                )
            )
            result = self._client.ft(index_name).search(
                query,
                query_params={"vector": np.asarray(query_vector, dtype=np.float32).tobytes()},
            )
        except ResponseError as exc:
            if self._is_missing_index_error(exc):
                return []
            self._handle_semantic_error("Redis semantic search failed", exc)
            return []
        except RedisError as exc:
            self._handle_semantic_error("Redis semantic search failed", exc)
            return []

        matches: list[SemanticCacheMatch] = []
        for document in getattr(result, "docs", []):
            payload = self._document_to_dict(document.__dict__)
            entry = SemanticCacheEntry(
                cache_key=self._decode_value(payload["cache_key"]),
                normalized_query=self._decode_value(payload["normalized_query"]),
                jurisdiction=self._decode_value(payload["jurisdiction"]),
                domain=self._decode_value(payload["domain"]),
                query_type=self._decode_value(payload["query_type"]),
                active_collection=self._decode_value(payload["active_collection"]),
                corpus_fingerprint=self._decode_value(payload["corpus_fingerprint"]),
                embedding_fingerprint=self._decode_value(payload["embedding_fingerprint"]),
                response_schema_version=self._decode_value(payload["response_schema_version"]),
                prompt_version=self._normalize_optional(payload.get("prompt_version")),
                document_ids=json.loads(self._decode_value(payload["document_ids"])),
                chunk_ids=json.loads(self._decode_value(payload["chunk_ids"])),
                response_payload=json.loads(self._decode_value(payload["response_payload"])),
                created_at=datetime.fromisoformat(self._decode_value(payload["created_at"])),
                expires_at=self._parse_optional_datetime(payload.get("expires_at")),
            )
            distance = float(self._decode_value(payload["vector_score"]))
            matches.append(
                SemanticCacheMatch(
                    entry=entry,
                    distance=distance,
                    similarity=max(0.0, 1.0 - distance),
                )
            )
        return matches

    def upsert_semantic_entry(
        self,
        index_name: str,
        entry_key: str,
        entry: SemanticCacheEntry,
        query_vector: list[float],
        ttl_seconds: int | None = None,
    ) -> bool:
        if not self._client or self._semantic_support_known is False:
            return False
        if not self.ensure_semantic_index(
            index_name=index_name,
            prefix=entry_key.rsplit(":", 2)[0] + ":",
            vector_dim=len(query_vector),
        ):
            return False
        prompt_value = entry.prompt_version or "__none__"
        mapping = {
            "cache_key": entry.cache_key,
            "normalized_query": entry.normalized_query,
            "jurisdiction": entry.jurisdiction,
            "domain": entry.domain,
            "query_type": entry.query_type,
            "active_collection": entry.active_collection,
            "corpus_fingerprint": entry.corpus_fingerprint,
            "embedding_fingerprint": entry.embedding_fingerprint,
            "response_schema_version": entry.response_schema_version,
            "prompt_version": prompt_value,
            "document_ids": json.dumps(entry.document_ids, ensure_ascii=False),
            "chunk_ids": json.dumps(entry.chunk_ids, ensure_ascii=False),
            "response_payload": json.dumps(entry.response_payload, ensure_ascii=False),
            "created_at": entry.created_at.isoformat(),
            "expires_at": entry.expires_at.isoformat() if entry.expires_at else "",
            "created_at_ts": int(entry.created_at.timestamp()),
            "embedding": np.asarray(query_vector, dtype=np.float32).tobytes(),
        }
        try:
            self._client.hset(entry_key, mapping=mapping)
            if ttl_seconds:
                self._client.expire(entry_key, ttl_seconds)
            return True
        except RedisError as exc:
            logger.warning("Redis semantic upsert failed for key %s: %s", entry_key, exc)
            return False

    def _handle_semantic_error(self, message: str, exc: Exception) -> bool:
        logger.warning("%s: %s", message, exc)
        self._semantic_support_known = False
        return False

    @staticmethod
    def _decode_value(value) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8")
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _normalize_optional(value) -> str | None:
        normalized = RedisCacheClient._decode_value(value)
        return None if normalized in {"", "__none__"} else normalized

    @staticmethod
    def _parse_optional_datetime(value) -> datetime | None:
        normalized = RedisCacheClient._decode_value(value)
        if not normalized:
            return None
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed

    @staticmethod
    def _escape_tag(value: str) -> str:
        escaped = value.replace("\\", "\\\\")
        for character in {":", "-", "{", "}", "|", " ", "."}:
            escaped = escaped.replace(character, f"\\{character}")
        return escaped

    @staticmethod
    def _document_to_dict(payload: dict) -> dict:
        return {
            key: value
            for key, value in payload.items()
            if key != "payload" and not key.startswith("_")
        }

    @staticmethod
    def _is_missing_index_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return "unknown index name" in message or "no such index" in message
