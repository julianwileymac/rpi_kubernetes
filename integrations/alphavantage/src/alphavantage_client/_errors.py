"""Typed exception hierarchy for Alpha Vantage responses.

Alpha Vantage signals rate limiting and various error conditions via HTTP 200
responses containing known JSON keys (``Note``, ``Information``, ``Error Message``).
This module normalizes those signals into a typed error hierarchy so callers can
react appropriately (fail fast on daily cap, retry on per-minute cap, etc.).
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping


class RateLimitKind(str, Enum):
    """Differentiates transient RPM throttling from hard daily caps."""

    RPM = "rpm"
    DAILY = "daily"
    UNKNOWN = "unknown"


class AlphaVantageError(Exception):
    """Base class for all Alpha Vantage client errors."""

    def __init__(self, message: str, *, payload: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.payload: Mapping[str, Any] = dict(payload or {})


class InvalidApiKeyError(AlphaVantageError):
    """Raised when no API key can be resolved from env/file/k8s mount."""


class InvalidSymbolError(AlphaVantageError):
    """Raised when Alpha Vantage reports an unknown symbol/ticker."""


class PremiumEndpointError(AlphaVantageError):
    """Raised when a premium endpoint is accessed without an entitled key."""


class RateLimitError(AlphaVantageError):
    """Raised when Alpha Vantage throttles the caller."""

    def __init__(
        self,
        message: str,
        *,
        kind: RateLimitKind = RateLimitKind.UNKNOWN,
        retry_after_seconds: float | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message, payload=payload)
        self.kind = kind
        self.retry_after_seconds = retry_after_seconds


class TransientError(AlphaVantageError):
    """Retriable transport/5xx/timeout error."""


class AlphaVantagePayloadError(AlphaVantageError):
    """The response parsed as JSON but did not match the expected schema."""


_RATE_LIMIT_DAILY_MARKERS = (
    "standard api rate limit is",
    "exceeded the rate limit",
    "25 requests per day",
    "25 calls per day",
    "daily rate limit",
)
_RATE_LIMIT_RPM_MARKERS = (
    "calls per minute",
    "api call frequency",
    "5 calls per minute",
    "please visit https://www.alphavantage.co/premium/",
)
_PREMIUM_MARKERS = (
    "is a premium endpoint",
    "premium membership plan",
    "premium api key",
)
_INVALID_KEY_MARKERS = (
    "invalid api key",
    "please claim your free api key",
    "missing/invalid api key",
)
_INVALID_SYMBOL_MARKERS = (
    "invalid api call",
    "invalid symbol",
    "no matching symbol",
)


def classify_payload(payload: Mapping[str, Any]) -> AlphaVantageError | None:
    """Inspect a decoded JSON body and return a typed error if it signals failure.

    Returns ``None`` when the payload looks like a successful response.
    """

    if not isinstance(payload, Mapping):
        return None

    def _get_text(key: str) -> str:
        value = payload.get(key)
        return value.strip() if isinstance(value, str) else ""

    note = _get_text("Note")
    info = _get_text("Information")
    err = _get_text("Error Message")

    blob = " ".join(filter(None, (note, info, err))).lower()
    if not blob:
        return None

    if any(marker in blob for marker in _INVALID_KEY_MARKERS):
        return InvalidApiKeyError(err or info or note, payload=payload)

    if any(marker in blob for marker in _PREMIUM_MARKERS):
        return PremiumEndpointError(info or note or err, payload=payload)

    if any(marker in blob for marker in _RATE_LIMIT_DAILY_MARKERS):
        return RateLimitError(
            info or note or err,
            kind=RateLimitKind.DAILY,
            payload=payload,
        )

    if any(marker in blob for marker in _RATE_LIMIT_RPM_MARKERS):
        return RateLimitError(
            info or note or err,
            kind=RateLimitKind.RPM,
            payload=payload,
        )

    if err:
        if any(marker in err.lower() for marker in _INVALID_SYMBOL_MARKERS):
            return InvalidSymbolError(err, payload=payload)
        return AlphaVantagePayloadError(err, payload=payload)

    if note or info:
        return RateLimitError(
            note or info,
            kind=RateLimitKind.UNKNOWN,
            payload=payload,
        )

    return None


__all__ = [
    "AlphaVantageError",
    "AlphaVantagePayloadError",
    "InvalidApiKeyError",
    "InvalidSymbolError",
    "PremiumEndpointError",
    "RateLimitError",
    "RateLimitKind",
    "TransientError",
    "classify_payload",
]
