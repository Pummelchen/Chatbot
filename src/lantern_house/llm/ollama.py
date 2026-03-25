# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from time import perf_counter

import httpx

from lantern_house.config import OllamaConfig

logger = logging.getLogger(__name__)


class OllamaClientError(RuntimeError):
    """Raised when Ollama interaction fails."""


@dataclass(slots=True)
class InvocationStats:
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    raw_duration_ns: int | None = None


class OllamaClient:
    def __init__(self, config: OllamaConfig) -> None:
        self.config = config
        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=config.request_timeout_seconds,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def healthcheck(self) -> dict:
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise OllamaClientError(
                f"Ollama healthcheck failed for {self.config.base_url}: {exc}"
            ) from exc

    async def ensure_models(self, models: list[str]) -> None:
        available = await self.healthcheck()
        tags = {item["name"] for item in available.get("models", [])}
        for model in models:
            if model in tags:
                continue
            if not self.config.auto_pull:
                raise OllamaClientError(f"Required Ollama model is missing: {model}")
            await self._pull_model(model)

        if self.config.warm_on_start:
            for model in models:
                await self.warm_model(model)

    async def warm_model(self, model: str) -> None:
        try:
            response = await self._client.post(
                "/api/generate",
                json={
                    "model": model,
                    "prompt": "Reply with OK.",
                    "stream": False,
                    "keep_alive": self.config.keep_alive,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("ollama warmup failed for %s: %s", model, exc)

    async def generate_json(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.8,
        max_output_tokens: int | None = None,
        max_retries: int | None = None,
    ) -> tuple[dict, InvocationStats]:
        last_error: Exception | None = None
        retry_budget = max(1, max_retries or self.config.max_retries)
        for attempt in range(1, retry_budget + 1):
            started = perf_counter()
            try:
                response = await self._client.post(
                    "/api/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "system": system or "",
                        "stream": False,
                        "format": "json",
                        "keep_alive": self.config.keep_alive,
                        "options": {
                            "temperature": temperature,
                            **(
                                {"num_predict": max_output_tokens}
                                if max_output_tokens is not None
                                else {}
                            ),
                        },
                    },
                )
                response.raise_for_status()
                payload = response.json()
                data = self._extract_json(payload.get("response", ""))
                latency_ms = int((perf_counter() - started) * 1000)
                stats = InvocationStats(
                    latency_ms=latency_ms,
                    prompt_tokens=payload.get("prompt_eval_count"),
                    completion_tokens=payload.get("eval_count"),
                    raw_duration_ns=payload.get("total_duration"),
                )
                logger.info(
                    (
                        "ollama generate ok model=%s latency_ms=%s "
                        "prompt_tokens=%s completion_tokens=%s"
                    ),
                    model,
                    stats.latency_ms,
                    stats.prompt_tokens,
                    stats.completion_tokens,
                )
                return data, stats
            except (httpx.HTTPError, json.JSONDecodeError, OllamaClientError) as exc:
                last_error = exc
                logger.warning("ollama generate attempt %s failed for %s: %s", attempt, model, exc)
                await asyncio.sleep(min(2**attempt, 8))

        raise OllamaClientError(f"Ollama generation failed for {model}: {last_error}")

    async def _pull_model(self, model: str) -> None:
        try:
            response = await self._client.post(
                "/api/pull",
                json={"name": model, "stream": False},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaClientError(
                f"Ollama model pull failed for {model} at {self.config.base_url}: {exc}"
            ) from exc

    def _extract_json(self, raw: str) -> dict:
        cleaned = raw.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise OllamaClientError(f"Model returned non-JSON output: {cleaned[:200]}")
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise OllamaClientError(
                f"Unable to recover JSON from model output: {cleaned[:200]}"
            ) from exc
