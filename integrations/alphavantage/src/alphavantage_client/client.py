"""High-level Alpha Vantage client facade.

Constructs a :class:`~._transport.Transport` (and an :class:`AsyncTransport`) under
the hood and hangs each endpoint group off it. The facade is usable as both a
regular object and an ``async with`` context manager.

Example:

    client = AlphaVantageClient()  # loads key from env/file/k8s mount
    quote = client.timeseries.global_quote("IBM")
    # or, async:
    async with AlphaVantageClient() as client:
        series = await client.timeseries.aintraday("IBM", interval="5min")
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

import httpx

from ._cache import CacheBackend, MemoryCache, make_cache
from ._credentials import load_api_key
from ._rate_limiter import RateLimiter
from ._transport import AsyncTransport, Transport, TransportConfig
from .endpoints import (
    Commodities,
    Crypto,
    Economics,
    Forex,
    Fundamentals,
    Indices,
    Intelligence,
    Options,
    Technicals,
    TimeSeries,
)


class AlphaVantageClient:
    """Unified sync + async facade."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        api_key_file: Optional[str] = None,
        extra_api_key_paths: Optional[Iterable[str]] = None,
        base_url: str = "https://www.alphavantage.co/query",
        rate_limit_rpm: int = 75,
        daily_limit: int = 0,
        timeout_seconds: float = 15.0,
        max_retries: int = 5,
        backoff_base: float = 1.0,
        backoff_cap: float = 60.0,
        headers: Optional[dict] = None,
        cache: Optional[CacheBackend] = None,
        cache_backend: str = "memory",
        cache_redis_client: Any = None,
        cache_sqlite_path: Optional[str] = None,
        cache_max_entries: int = 512,
        rapidapi: bool = False,
        rapidapi_host: str = "alpha-vantage.p.rapidapi.com",
        sync_client: Optional[httpx.Client] = None,
        async_client: Optional[httpx.AsyncClient] = None,
        rate_limiter: Optional[RateLimiter] = None,
    ) -> None:
        resolved_key = load_api_key(
            api_key,
            file_path=api_key_file,
            extra_paths=extra_api_key_paths,
            strict=True,
        )

        config = TransportConfig(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            backoff_base=backoff_base,
            backoff_cap=backoff_cap,
            headers=headers or {},
            rapidapi=rapidapi,
            rapidapi_host=rapidapi_host,
        )

        if cache is None:
            if cache_backend == "memory" and cache_redis_client is None and cache_sqlite_path is None:
                cache = MemoryCache(max_entries=cache_max_entries)
            else:
                cache = make_cache(
                    cache_backend,
                    redis_client=cache_redis_client,
                    sqlite_path=cache_sqlite_path,
                    max_entries=cache_max_entries,
                )

        self._rate_limiter = rate_limiter or RateLimiter(rpm=rate_limit_rpm, daily=daily_limit)

        self._sync = Transport(
            resolved_key,
            rate_limiter=self._rate_limiter,
            cache=cache,
            config=config,
            client=sync_client,
        )
        self._async = AsyncTransport(
            resolved_key,
            rate_limiter=self._rate_limiter,
            cache=cache,
            config=config,
            client=async_client,
        )

        # Endpoint groups share both transports, exposing both ``method`` and ``amethod``.
        self.timeseries = TimeSeries(transport=self._sync, async_transport=self._async)
        self.indices = Indices(transport=self._sync, async_transport=self._async)
        self.options = Options(transport=self._sync, async_transport=self._async)
        self.intelligence = Intelligence(transport=self._sync, async_transport=self._async)
        self.fundamentals = Fundamentals(transport=self._sync, async_transport=self._async)
        self.forex = Forex(transport=self._sync, async_transport=self._async)
        self.crypto = Crypto(transport=self._sync, async_transport=self._async)
        self.commodities = Commodities(transport=self._sync, async_transport=self._async)
        self.economics = Economics(transport=self._sync, async_transport=self._async)
        self.technicals = Technicals(transport=self._sync, async_transport=self._async)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._sync.close()

    async def aclose(self) -> None:
        await self._async.aclose()

    def __enter__(self) -> "AlphaVantageClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    async def __aenter__(self) -> "AlphaVantageClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def rate_limiter(self) -> RateLimiter:
        return self._rate_limiter


__all__ = ["AlphaVantageClient"]
