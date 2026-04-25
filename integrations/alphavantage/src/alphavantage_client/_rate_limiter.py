"""Token-bucket rate limiter supporting sync and async consumers.

Alpha Vantage free tier caps callers at ~25 requests/day (and historically 5 req/min),
paid tiers scale between 75 and 1200 RPM. This limiter enforces both a per-minute
bucket and an optional daily cap, exposes usage counters for introspection, and is
safe to share across threads and asyncio tasks.
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class RateLimiterSnapshot:
    """Read-only view of the limiter's internal state."""

    rpm_limit: int
    daily_limit: int
    requests_this_minute: int
    requests_today: int
    tokens_available: float
    next_refill_seconds: float
    daily_reset_utc: str


class RateLimiter:
    """Token bucket with a rolling per-minute window and an optional daily cap."""

    def __init__(
        self,
        rpm: int = 75,
        daily: int = 0,
        *,
        clock: Optional[callable] = None,
    ) -> None:
        if rpm <= 0:
            raise ValueError("rpm must be positive")
        self.rpm = int(rpm)
        self.daily = max(int(daily), 0)  # 0 = no daily cap
        self._clock = clock or time.monotonic
        self._wall_clock = time.time
        self._tokens = float(rpm)
        self._last_refill = self._clock()
        self._rolling_requests: list[float] = []
        self._daily_count = 0
        self._daily_window_start = self._wall_clock()
        self._lock = threading.Lock()
        self._async_lock = asyncio.Lock()

    @property
    def tokens(self) -> float:
        return self._tokens

    def _refill_locked(self) -> None:
        now = self._clock()
        elapsed = now - self._last_refill
        if elapsed > 0:
            refill = elapsed * (self.rpm / 60.0)
            self._tokens = min(float(self.rpm), self._tokens + refill)
            self._last_refill = now
        cutoff = now - 60.0
        self._rolling_requests = [t for t in self._rolling_requests if t > cutoff]

    def _rotate_daily_locked(self) -> None:
        now_wall = self._wall_clock()
        now_utc = datetime.fromtimestamp(now_wall, tz=timezone.utc)
        window_utc = datetime.fromtimestamp(self._daily_window_start, tz=timezone.utc)
        if now_utc.date() != window_utc.date():
            self._daily_count = 0
            self._daily_window_start = now_wall

    def _time_to_next_token_locked(self) -> float:
        self._refill_locked()
        if self._tokens >= 1.0:
            return 0.0
        missing = 1.0 - self._tokens
        seconds_per_token = 60.0 / self.rpm
        return missing * seconds_per_token

    def acquire(self, *, timeout: float | None = None) -> None:
        deadline = None if timeout is None else self._clock() + timeout
        while True:
            with self._lock:
                self._rotate_daily_locked()
                if self.daily and self._daily_count >= self.daily:
                    raise _daily_exhausted(self.daily)
                self._refill_locked()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    self._rolling_requests.append(self._clock())
                    self._daily_count += 1
                    return
                wait = self._time_to_next_token_locked()
            if deadline is not None and self._clock() + wait > deadline:
                raise TimeoutError("Rate limiter timeout waiting for token")
            time.sleep(max(0.01, wait))

    async def aacquire(self, *, timeout: float | None = None) -> None:
        deadline = None if timeout is None else self._clock() + timeout
        while True:
            async with self._async_lock:
                with self._lock:
                    self._rotate_daily_locked()
                    if self.daily and self._daily_count >= self.daily:
                        raise _daily_exhausted(self.daily)
                    self._refill_locked()
                    if self._tokens >= 1.0:
                        self._tokens -= 1.0
                        self._rolling_requests.append(self._clock())
                        self._daily_count += 1
                        return
                    wait = self._time_to_next_token_locked()
            if deadline is not None and self._clock() + wait > deadline:
                raise TimeoutError("Rate limiter timeout waiting for token")
            await asyncio.sleep(max(0.01, wait))

    def snapshot(self) -> RateLimiterSnapshot:
        with self._lock:
            self._refill_locked()
            self._rotate_daily_locked()
            next_refill = self._time_to_next_token_locked()
            window_utc = datetime.fromtimestamp(self._daily_window_start, tz=timezone.utc)
            daily_reset = (
                window_utc.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            )
            return RateLimiterSnapshot(
                rpm_limit=self.rpm,
                daily_limit=self.daily,
                requests_this_minute=len(self._rolling_requests),
                requests_today=self._daily_count,
                tokens_available=self._tokens,
                next_refill_seconds=next_refill,
                daily_reset_utc=daily_reset,
            )


def _daily_exhausted(limit: int):
    from ._errors import RateLimitError, RateLimitKind

    return RateLimitError(
        f"Alpha Vantage daily cap of {limit} requests reached; retry after UTC midnight.",
        kind=RateLimitKind.DAILY,
    )


__all__ = ["RateLimiter", "RateLimiterSnapshot"]
