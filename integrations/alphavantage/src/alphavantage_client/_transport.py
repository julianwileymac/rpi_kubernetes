"""Thin sync+async transport layer.

Wraps :mod:`httpx` with:

* per-request rate-limiter acquisition,
* exponential backoff + jitter on transient failures and ``RateLimitError(kind=RPM)``,
* response caching via the pluggable :class:`~._cache.CacheBackend`,
* typed error classification.

Deliberately dumb with respect to Alpha Vantage semantics - endpoint modules are
responsible for building param dicts and parsing JSON into Pydantic models.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, MutableMapping, Optional

import httpx

from ._cache import CacheBackend, CacheKey, NullCache, default_ttl
from ._errors import (
    AlphaVantageError,
    AlphaVantagePayloadError,
    InvalidApiKeyError,
    RateLimitError,
    RateLimitKind,
    TransientError,
    classify_payload,
)
from ._rate_limiter import RateLimiter


logger = logging.getLogger(__name__)


@dataclass
class TransportConfig:
    """Tunables shared by sync and async transports."""

    base_url: str = "https://www.alphavantage.co/query"
    timeout_seconds: float = 15.0
    max_retries: int = 5
    backoff_base: float = 1.0
    backoff_cap: float = 60.0
    headers: Mapping[str, str] = field(default_factory=dict)
    user_agent: str = "rpi-k8s-alphavantage-client/0.1"
    trust_env: bool = True
    rapidapi: bool = False
    rapidapi_host: str = "alpha-vantage.p.rapidapi.com"


class Transport:
    """Synchronous transport."""

    def __init__(
        self,
        api_key: str,
        *,
        rate_limiter: Optional[RateLimiter] = None,
        cache: Optional[CacheBackend] = None,
        config: Optional[TransportConfig] = None,
        client: Optional[httpx.Client] = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise InvalidApiKeyError("api_key cannot be empty")
        self.api_key = api_key.strip()
        self.config = config or TransportConfig()
        self.rate_limiter = rate_limiter or RateLimiter()
        self.cache: CacheBackend = cache or NullCache()
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=self.config.timeout_seconds,
            headers=self._build_headers(),
            trust_env=self.config.trust_env,
        )

    def _build_headers(self) -> dict[str, str]:
        headers = {"User-Agent": self.config.user_agent, **dict(self.config.headers)}
        if self.config.rapidapi:
            headers.setdefault("x-rapidapi-host", self.config.rapidapi_host)
            headers.setdefault("x-rapidapi-key", self.api_key)
        return headers

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "Transport":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def request(
        self,
        params: Mapping[str, Any],
        *,
        cache: bool = True,
        cache_ttl: Optional[float] = None,
        datatype: Optional[str] = None,
    ) -> Any:
        """Issue a GET request to the AV query endpoint.

        Args:
            params: Pre-validated AV params (``function``, ``symbol``, etc.).
            cache: Whether to consult/populate the shared cache.
            cache_ttl: Explicit TTL override.
            datatype: Optional output format (``"json"``/``"csv"``). When ``csv``,
                returns the raw response text.
        """

        query = self._prepare_params(params, datatype=datatype)
        key = CacheKey.from_params(query)
        ttl = cache_ttl if cache_ttl is not None else default_ttl(key.function, query)

        if cache and ttl > 0:
            cached = self.cache.get(key)
            if cached is not None:
                logger.debug("av cache hit function=%s", key.function)
                return cached

        payload = self._retry_request(query, datatype=datatype)

        if cache and ttl > 0 and datatype != "csv":
            try:
                self.cache.set(key, payload, ttl)
            except Exception:  # noqa: BLE001
                logger.warning("av cache set failed", exc_info=True)

        return payload

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _prepare_params(
        self,
        params: Mapping[str, Any],
        *,
        datatype: Optional[str],
    ) -> dict[str, Any]:
        query: dict[str, Any] = {k: v for k, v in params.items() if v is not None and v != ""}
        if not self.config.rapidapi:
            query["apikey"] = self.api_key
        if datatype and "datatype" not in query:
            query["datatype"] = datatype
        return query

    def _retry_request(self, query: Mapping[str, Any], *, datatype: Optional[str]) -> Any:
        attempt = 0
        last_exc: Exception | None = None
        while attempt <= self.config.max_retries:
            attempt += 1
            try:
                self.rate_limiter.acquire()
            except RateLimitError:
                raise
            except TimeoutError as exc:
                raise TransientError(str(exc)) from exc

            try:
                response = self._client.get(self.config.base_url, params=query)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = TransientError(f"Transport error: {exc}")
                self._sleep_backoff(attempt)
                continue

            payload, err = self._process_response(response, datatype=datatype)
            if err is None:
                return payload

            if isinstance(err, RateLimitError) and err.kind == RateLimitKind.RPM:
                last_exc = err
                self._sleep_backoff(attempt, hint=err.retry_after_seconds)
                continue
            if isinstance(err, TransientError):
                last_exc = err
                self._sleep_backoff(attempt)
                continue
            raise err

        if last_exc is None:
            last_exc = TransientError("Unknown transport failure")
        raise last_exc

    def _process_response(
        self,
        response: httpx.Response,
        *,
        datatype: Optional[str],
    ) -> tuple[Any, Optional[Exception]]:
        status = response.status_code
        if status in (500, 502, 503, 504, 522, 524):
            return None, TransientError(f"Alpha Vantage HTTP {status}")
        if status == 429:
            retry_after = _parse_retry_after(response.headers)
            return None, RateLimitError(
                "HTTP 429 Too Many Requests",
                kind=RateLimitKind.RPM,
                retry_after_seconds=retry_after,
            )
        if status >= 400:
            return None, AlphaVantagePayloadError(
                f"Alpha Vantage HTTP {status}: {response.text[:200]}",
            )

        if datatype == "csv":
            return response.text, None

        try:
            payload = response.json()
        except ValueError as exc:
            return None, AlphaVantagePayloadError(f"Non-JSON response: {exc}")

        err = classify_payload(payload) if isinstance(payload, Mapping) else None
        return (payload, None) if err is None else (None, err)

    def _sleep_backoff(self, attempt: int, *, hint: float | None = None) -> None:
        if hint is not None and hint > 0:
            time.sleep(min(hint, self.config.backoff_cap))
            return
        delay = min(
            self.config.backoff_cap,
            self.config.backoff_base * (2 ** (attempt - 1)),
        )
        delay = delay * (0.5 + random.random() * 0.5)
        time.sleep(delay)


class AsyncTransport(Transport):
    """Asyncio variant: overrides ``arequest`` while reusing validation logic."""

    def __init__(
        self,
        api_key: str,
        *,
        rate_limiter: Optional[RateLimiter] = None,
        cache: Optional[CacheBackend] = None,
        config: Optional[TransportConfig] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise InvalidApiKeyError("api_key cannot be empty")
        self.api_key = api_key.strip()
        self.config = config or TransportConfig()
        self.rate_limiter = rate_limiter or RateLimiter()
        self.cache: CacheBackend = cache or NullCache()
        self._owns_client = client is None
        self._aclient: httpx.AsyncClient = client or httpx.AsyncClient(
            timeout=self.config.timeout_seconds,
            headers=self._build_headers(),
            trust_env=self.config.trust_env,
        )
        # Keep a sync client around for callers that want fallback sync requests.
        self._client = httpx.Client(
            timeout=self.config.timeout_seconds,
            headers=self._build_headers(),
            trust_env=self.config.trust_env,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._aclient.aclose()
        self._client.close()

    async def __aenter__(self) -> "AsyncTransport":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def arequest(
        self,
        params: Mapping[str, Any],
        *,
        cache: bool = True,
        cache_ttl: Optional[float] = None,
        datatype: Optional[str] = None,
    ) -> Any:
        query = self._prepare_params(params, datatype=datatype)
        key = CacheKey.from_params(query)
        ttl = cache_ttl if cache_ttl is not None else default_ttl(key.function, query)

        if cache and ttl > 0:
            cached = self.cache.get(key)
            if cached is not None:
                return cached

        payload = await self._aretry_request(query, datatype=datatype)

        if cache and ttl > 0 and datatype != "csv":
            try:
                self.cache.set(key, payload, ttl)
            except Exception:  # noqa: BLE001
                logger.warning("av cache set failed", exc_info=True)
        return payload

    async def _aretry_request(
        self,
        query: Mapping[str, Any],
        *,
        datatype: Optional[str],
    ) -> Any:
        attempt = 0
        last_exc: Exception | None = None
        while attempt <= self.config.max_retries:
            attempt += 1
            try:
                await self.rate_limiter.aacquire()
            except RateLimitError:
                raise
            except TimeoutError as exc:
                raise TransientError(str(exc)) from exc

            try:
                response = await self._aclient.get(self.config.base_url, params=query)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = TransientError(f"Transport error: {exc}")
                await self._asleep_backoff(attempt)
                continue

            payload, err = self._process_response(response, datatype=datatype)
            if err is None:
                return payload

            if isinstance(err, RateLimitError) and err.kind == RateLimitKind.RPM:
                last_exc = err
                await self._asleep_backoff(attempt, hint=err.retry_after_seconds)
                continue
            if isinstance(err, TransientError):
                last_exc = err
                await self._asleep_backoff(attempt)
                continue
            raise err

        if last_exc is None:
            last_exc = TransientError("Unknown transport failure")
        raise last_exc

    async def _asleep_backoff(self, attempt: int, *, hint: float | None = None) -> None:
        if hint is not None and hint > 0:
            await asyncio.sleep(min(hint, self.config.backoff_cap))
            return
        delay = min(
            self.config.backoff_cap,
            self.config.backoff_base * (2 ** (attempt - 1)),
        )
        delay = delay * (0.5 + random.random() * 0.5)
        await asyncio.sleep(delay)


def _parse_retry_after(headers: MutableMapping[str, str]) -> float | None:
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if not raw:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


__all__ = [
    "AsyncTransport",
    "Transport",
    "TransportConfig",
]
