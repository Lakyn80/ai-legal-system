from __future__ import annotations

import asyncio
import logging
import time

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)


async def wait_for_qdrant_ready(
    timeout_seconds: float = 45.0,
    initial_delay_seconds: float = 0.5,
    max_delay_seconds: float = 5.0,
) -> None:
    settings = get_settings()
    deadline = time.monotonic() + timeout_seconds
    delay = initial_delay_seconds
    attempt = 0
    last_error: Exception | None = None

    headers: dict[str, str] = {}
    if settings.qdrant_api_key:
        headers["api-key"] = settings.qdrant_api_key

    async with httpx.AsyncClient(
        base_url=settings.qdrant_url.rstrip("/"),
        headers=headers,
        timeout=5.0,
    ) as client:
        while True:
            attempt += 1
            try:
                log.info(
                    "Waiting for Qdrant readiness: attempt=%d url=%s/collections",
                    attempt,
                    settings.qdrant_url.rstrip("/"),
                )
                response = await client.get("/collections")
                response.raise_for_status()
                log.info("Qdrant is ready: url=%s", settings.qdrant_url.rstrip("/"))
                return
            except Exception as exc:
                last_error = exc
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                log.warning(
                    "Qdrant not ready yet: attempt=%d retry_in=%.1fs error=%s",
                    attempt,
                    min(delay, remaining),
                    exc,
                )
                await asyncio.sleep(min(delay, remaining))
                delay = min(delay * 2, max_delay_seconds)

    raise RuntimeError(
        f"Qdrant did not become ready within {timeout_seconds:.0f}s at {settings.qdrant_url}"
    ) from last_error
