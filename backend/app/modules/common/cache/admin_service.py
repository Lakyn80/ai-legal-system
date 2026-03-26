from pydantic import BaseModel

from app.modules.common.cache.client import RedisCacheClient


class CacheResetResult(BaseModel):
    exact_entries_deleted: int = 0
    semantic_entries_deleted: int = 0


class CacheAdminService:
    EXACT_PATTERN = "ai-legal:exact:*"
    SEMANTIC_PATTERN = "ai-legal:semantic:*"

    def __init__(self, client: RedisCacheClient | None) -> None:
        self.client = client

    def reset(self) -> CacheResetResult:
        if self.client is None or not self.client.enabled:
            return CacheResetResult()
        return CacheResetResult(
            exact_entries_deleted=self.client.delete_by_pattern(self.EXACT_PATTERN),
            semantic_entries_deleted=self.client.delete_by_pattern(self.SEMANTIC_PATTERN),
        )

