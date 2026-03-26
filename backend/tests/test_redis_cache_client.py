from redis.exceptions import ResponseError

from app.modules.common.cache.client import RedisCacheClient


def test_missing_index_error_detection_accepts_multiple_redisearch_messages():
    assert RedisCacheClient._is_missing_index_error(ResponseError("Unknown Index name"))
    assert RedisCacheClient._is_missing_index_error(ResponseError("idx: no such index"))
    assert RedisCacheClient._is_missing_index_error(ResponseError("No such index"))
