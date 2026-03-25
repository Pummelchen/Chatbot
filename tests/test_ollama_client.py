# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

import httpx
import pytest

from lantern_house.config import OllamaConfig
from lantern_house.llm.ollama import OllamaClient, OllamaClientError


@pytest.mark.asyncio
async def test_healthcheck_wraps_transport_error_with_base_url() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    client = OllamaClient(OllamaConfig(base_url="http://127.0.0.1:11434"))
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url=client.config.base_url,
        timeout=client.config.request_timeout_seconds,
    )
    try:
        with pytest.raises(OllamaClientError, match=r"127\.0\.0\.1:11434"):
            await client.healthcheck()
    finally:
        await client.close()
