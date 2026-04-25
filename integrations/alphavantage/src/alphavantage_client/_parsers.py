"""Helpers that translate Alpha Vantage JSON bodies into structured Python values.

These helpers keep the endpoint modules small: each endpoint returns either the raw
dict (``output_format='raw'`` or ``'json'``) or a Pydantic model built from the
dict.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from ._errors import AlphaVantagePayloadError


_NUMERIC_FIELDS = {"open", "high", "low", "close", "volume", "adjusted close",
                   "dividend amount", "split coefficient", "vwap"}


def extract_series(
    payload: Mapping[str, Any],
    series_key: str,
    *,
    numeric_strip: bool = True,
) -> list[dict[str, Any]]:
    """Convert a keyed ``{"timestamp": {"1. open": "..."}}`` mapping into rows."""

    raw = payload.get(series_key)
    if raw is None:
        raise AlphaVantagePayloadError(f"missing series key {series_key!r} in AV payload")
    if not isinstance(raw, Mapping):
        raise AlphaVantagePayloadError(f"series key {series_key!r} is not a mapping")

    rows: list[dict[str, Any]] = []
    for timestamp, attrs in raw.items():
        if not isinstance(attrs, Mapping):
            continue
        row: dict[str, Any] = {"timestamp": timestamp}
        for key, value in attrs.items():
            normalized = _normalize_field(key)
            if numeric_strip and normalized in _NUMERIC_FIELDS and isinstance(value, str):
                row[normalized] = _try_float(value)
            else:
                row[normalized] = value
        rows.append(row)
    return rows


def iter_list_of_records(
    payload: Mapping[str, Any],
    key: str,
    *,
    required: bool = True,
) -> list[dict[str, Any]]:
    """Return ``payload[key]`` coerced into a list of dicts."""

    raw = payload.get(key)
    if raw is None:
        if required:
            raise AlphaVantagePayloadError(f"missing list key {key!r} in AV payload")
        return []
    if not isinstance(raw, Iterable):
        raise AlphaVantagePayloadError(f"AV payload {key!r} is not iterable")
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def coerce_meta(payload: Mapping[str, Any], meta_key: str = "Meta Data") -> dict[str, Any]:
    raw = payload.get(meta_key) or {}
    if not isinstance(raw, Mapping):
        return {}
    return {_normalize_field(k): v for k, v in raw.items()}


def _normalize_field(key: str) -> str:
    """Strip numeric prefixes (e.g. ``"1. open"`` -> ``"open"``)."""

    if "." in key:
        _, _, tail = key.partition(".")
        return tail.strip().lower()
    return key.strip().lower()


def _try_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_timestamp(ts: str) -> datetime | None:
    """Parse common AV timestamp shapes into UTC-aware ``datetime`` objects."""

    if not ts:
        return None
    cleaned = ts.strip()
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y%m%dT%H%M%S",
        "%Y%m%dT%H%M",
    )
    for fmt in formats:
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(cleaned).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def to_epoch_ns(ts: str | datetime | None) -> int | None:
    if ts is None:
        return None
    dt = ts if isinstance(ts, datetime) else parse_timestamp(ts)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1_000_000_000)


__all__ = [
    "coerce_meta",
    "extract_series",
    "iter_list_of_records",
    "parse_timestamp",
    "to_epoch_ns",
]
