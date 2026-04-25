"""Response caching for the Alpha Vantage client.

The cache key is the canonical query string with the ``apikey`` stripped. Supported
backends: in-memory LRU, sqlite file, or a pluggable Redis client (for sharing across
pods). Each endpoint category has a sensible default TTL (immutable history is cached
aggressively, realtime endpoints are bypassed by default).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional
from urllib.parse import urlencode


TTL_INFINITE = 10**9


@dataclass(frozen=True)
class CacheKey:
    """Normalized cache key: sorted params, ``apikey`` redacted."""

    function: str
    canonical: str
    digest: str

    @classmethod
    def from_params(cls, params: Mapping[str, Any]) -> "CacheKey":
        function = str(params.get("function", "")).upper()
        redacted = {k: v for k, v in params.items() if k != "apikey" and v is not None}
        canonical = urlencode(sorted(redacted.items()))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return cls(function=function, canonical=canonical, digest=digest)


class CacheBackend(ABC):
    """Abstract synchronous cache backend."""

    @abstractmethod
    def get(self, key: CacheKey) -> Optional[Any]:
        ...

    @abstractmethod
    def set(self, key: CacheKey, value: Any, ttl: float) -> None:
        ...

    def aget(self, key: CacheKey) -> Optional[Any]:
        return self.get(key)

    def aset(self, key: CacheKey, value: Any, ttl: float) -> None:
        self.set(key, value, ttl)


class NullCache(CacheBackend):
    def get(self, key: CacheKey) -> Optional[Any]:
        return None

    def set(self, key: CacheKey, value: Any, ttl: float) -> None:
        return None


class MemoryCache(CacheBackend):
    """Thread-safe bounded LRU with per-entry TTL."""

    def __init__(self, max_entries: int = 512) -> None:
        self._max = max_entries
        self._data: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: CacheKey) -> Optional[Any]:
        with self._lock:
            entry = self._data.get(key.digest)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at < time.time():
                self._data.pop(key.digest, None)
                return None
            self._data.move_to_end(key.digest)
            return value

    def set(self, key: CacheKey, value: Any, ttl: float) -> None:
        with self._lock:
            expires_at = time.time() + float(ttl)
            self._data[key.digest] = (expires_at, value)
            self._data.move_to_end(key.digest)
            while len(self._data) > self._max:
                self._data.popitem(last=False)


class SqliteCache(CacheBackend):
    """SQLite-backed cache; suitable for single-process batch workers."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), isolation_level=None, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS av_cache (
                    digest TEXT PRIMARY KEY,
                    function TEXT NOT NULL,
                    canonical TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    payload TEXT NOT NULL
                )
                """,
            )

    def get(self, key: CacheKey) -> Optional[Any]:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT expires_at, payload FROM av_cache WHERE digest = ?",
                (key.digest,),
            ).fetchone()
        if not row:
            return None
        expires_at, payload = row
        if expires_at < time.time():
            self._delete(key.digest)
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            self._delete(key.digest)
            return None

    def set(self, key: CacheKey, value: Any, ttl: float) -> None:
        expires_at = time.time() + float(ttl)
        payload = json.dumps(value)
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO av_cache
                    (digest, function, canonical, expires_at, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (key.digest, key.function, key.canonical, expires_at, payload),
            )

    def _delete(self, digest: str) -> None:
        with self._lock, self._conn() as conn:
            conn.execute("DELETE FROM av_cache WHERE digest = ?", (digest,))


class RedisCache(CacheBackend):
    """Cache backed by a ``redis.Redis``-compatible client."""

    def __init__(self, client: Any, *, prefix: str = "rpi:av:cache") -> None:
        self.client = client
        self.prefix = prefix.rstrip(":")
        self._aclient = getattr(client, "asyncio", None)

    def _key(self, key: CacheKey) -> str:
        return f"{self.prefix}:{key.function or 'unknown'}:{key.digest}"

    def get(self, key: CacheKey) -> Optional[Any]:
        try:
            raw = self.client.get(self._key(key))
        except Exception:
            return None
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    def set(self, key: CacheKey, value: Any, ttl: float) -> None:
        try:
            self.client.set(self._key(key), json.dumps(value), ex=int(max(ttl, 1)))
        except Exception:
            return None


# ---------------------------------------------------------------------------
# TTL policy
# ---------------------------------------------------------------------------


def _default_ttl_for(function: str, params: Mapping[str, Any]) -> float:
    """Return a sensible default TTL (seconds) for an AV endpoint call."""

    func = function.upper()
    # Historical slices are immutable once the month has closed.
    if func == "TIME_SERIES_INTRADAY" and params.get("month"):
        return TTL_INFINITE

    immutable_history = {
        "TIME_SERIES_DAILY",
        "TIME_SERIES_DAILY_ADJUSTED",
        "TIME_SERIES_WEEKLY",
        "TIME_SERIES_WEEKLY_ADJUSTED",
        "TIME_SERIES_MONTHLY",
        "TIME_SERIES_MONTHLY_ADJUSTED",
        "FX_DAILY",
        "FX_WEEKLY",
        "FX_MONTHLY",
        "DIGITAL_CURRENCY_DAILY",
        "DIGITAL_CURRENCY_WEEKLY",
        "DIGITAL_CURRENCY_MONTHLY",
        "HISTORICAL_OPTIONS",
        "HISTORICAL_PUT_CALL_RATIO",
        "HISTORICAL_VOI_RATIO",
        "EARNINGS",
        "EARNINGS_CALL_TRANSCRIPT",
        "SHARES_OUTSTANDING",
        "LISTING_STATUS",
        "IPO_CALENDAR",
    }
    if func in immutable_history:
        return 86400.0

    slow_changing = {
        "OVERVIEW",
        "ETF_PROFILE",
        "DIVIDENDS",
        "SPLITS",
        "INCOME_STATEMENT",
        "BALANCE_SHEET",
        "CASH_FLOW",
        "EARNINGS_ESTIMATES",
        "INSIDER_TRANSACTIONS",
        "INSTITUTIONAL_HOLDINGS",
        "EARNINGS_CALENDAR",
        "SYMBOL_SEARCH",
        "INDEX_CATALOG",
    }
    if func in slow_changing:
        return 21600.0  # 6h

    economics = {
        "REAL_GDP",
        "REAL_GDP_PER_CAPITA",
        "TREASURY_YIELD",
        "FEDERAL_FUNDS_RATE",
        "CPI",
        "INFLATION",
        "RETAIL_SALES",
        "DURABLES",
        "UNEMPLOYMENT",
        "NONFARM_PAYROLL",
        "WTI",
        "BRENT",
        "NATURAL_GAS",
        "COPPER",
        "ALUMINUM",
        "WHEAT",
        "CORN",
        "COTTON",
        "SUGAR",
        "COFFEE",
        "ALL_COMMODITIES",
    }
    if func in economics:
        return 43200.0  # 12h

    # Technical indicators share a bucket; re-running with the same params returns
    # the same series until a new bar closes.
    if func.startswith(("SMA", "EMA", "WMA", "DEMA", "TEMA", "TRIMA", "KAMA", "MAMA",
                        "MACD", "STOCH", "RSI", "WILLR", "ADX", "ADXR", "APO", "PPO",
                        "MOM", "BOP", "CCI", "CMO", "ROC", "AROON", "MFI", "TRIX",
                        "ULTOSC", "DX", "MINUS", "PLUS", "BBANDS", "MIDPOINT",
                        "MIDPRICE", "SAR", "TRANGE", "ATR", "NATR", "AD", "ADOSC",
                        "OBV", "HT_")):
        return 300.0

    # Default: fast-moving data (quotes, news, market status) only briefly cached.
    realtime_like = {
        "GLOBAL_QUOTE",
        "REALTIME_BULK_QUOTES",
        "TOP_GAINERS_LOSERS",
        "MARKET_STATUS",
        "REALTIME_OPTIONS",
        "REALTIME_PUT_CALL_RATIO",
        "REALTIME_VOI_RATIO",
        "NEWS_SENTIMENT",
        "CURRENCY_EXCHANGE_RATE",
    }
    if func in realtime_like:
        return 30.0
    return 60.0


def default_ttl(function: str, params: Mapping[str, Any] | None = None) -> float:
    return _default_ttl_for(function, params or {})


def make_cache(
    kind: str = "memory",
    *,
    redis_client: Any = None,
    sqlite_path: str | Path | None = None,
    max_entries: int = 512,
) -> CacheBackend:
    """Factory honoring the kind used by :class:`AlphaVantageSettings.cache_backend`."""

    normalized = (kind or "memory").strip().lower()
    if normalized in {"", "none", "null", "off", "disabled"}:
        return NullCache()
    if normalized == "memory":
        return MemoryCache(max_entries=max_entries)
    if normalized == "sqlite":
        if not sqlite_path:
            raise ValueError("sqlite_path is required for cache_backend='sqlite'")
        return SqliteCache(sqlite_path)
    if normalized == "redis":
        if redis_client is None:
            raise ValueError("redis_client is required for cache_backend='redis'")
        return RedisCache(redis_client)
    raise ValueError(f"Unknown cache_backend {kind!r}")


__all__ = [
    "CacheBackend",
    "CacheKey",
    "MemoryCache",
    "NullCache",
    "RedisCache",
    "SqliteCache",
    "TTL_INFINITE",
    "default_ttl",
    "make_cache",
]
