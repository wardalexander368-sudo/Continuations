"""Small JSON-over-HTTP client with rate limiting and retries."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from .. import __version__


class ApiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class NotFound(ApiError):
    pass


class JsonClient:
    def __init__(
        self,
        base_url: str,
        min_interval: float = 0.0,
        retries: int = 3,
        backoff: float = 1.0,
        timeout: float = 15.0,
        client: httpx.AsyncClient | None = None,
        headers: dict[str, str] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._min_interval = min_interval
        self._retries = retries
        self._backoff = backoff
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": f"tartar/{__version__}", "Accept": "application/json", **(headers or {})},
        )
        self._lock = asyncio.Lock()
        self._next_at = 0.0

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        error: ApiError | None = None
        for attempt in range(self._retries + 1):
            if attempt:
                await asyncio.sleep(min(self._backoff * 2 ** (attempt - 1), 20.0))
            async with self._lock:
                wait = self._next_at - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                self._next_at = time.monotonic() + self._min_interval
            try:
                response = await self._client.get(url, params=params)
            except httpx.HTTPError as exc:
                error = ApiError(f"{url}: {exc.__class__.__name__}: {exc}")
                continue
            if response.status_code == 404:
                raise NotFound(f"{url}: not found", 404)
            if response.status_code == 429 or response.status_code >= 500:
                error = ApiError(f"{url}: HTTP {response.status_code}", response.status_code)
                retry_after = response.headers.get("Retry-After", "")
                if attempt == self._retries:
                    break  # no retry left: don't wait for nothing
                if retry_after.isdigit():
                    await asyncio.sleep(min(float(retry_after), 60.0))
                elif response.status_code == 429:
                    # Per-minute quotas: wait out a good part of the window, not a few seconds.
                    await asyncio.sleep(min(self._backoff * 10 * 2**attempt, 60.0))
                continue
            if response.status_code >= 400:
                raise ApiError(f"{url}: HTTP {response.status_code}: {response.text[:200]}", response.status_code)
            try:
                return response.json()
            except ValueError as exc:
                raise ApiError(f"{url}: invalid JSON") from exc
        assert error is not None
        raise error

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
