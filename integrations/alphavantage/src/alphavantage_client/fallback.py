"""Optional bridge into the community ``alpha_vantage`` package.

``RomelTorres/alpha_vantage`` is unmaintained but still useful for a handful of
niche parsers. When the optional ``alpha_vantage>=3.0`` dependency is installed,
the helpers below let callers reuse its parsing while still benefiting from our
rate limiter and credentials loader.

Import guarded - we never raise at import time if the community library is
missing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from ._credentials import load_api_key
from ._errors import AlphaVantageError

try:
    from alpha_vantage.timeseries import TimeSeries as _LegacyTimeSeries  # type: ignore[import-not-found]
    from alpha_vantage.techindicators import (  # type: ignore[import-not-found]
        TechIndicators as _LegacyTechIndicators,
    )
    from alpha_vantage.fundamentaldata import (  # type: ignore[import-not-found]
        FundamentalData as _LegacyFundamentals,
    )
    from alpha_vantage.cryptocurrencies import (  # type: ignore[import-not-found]
        CryptoCurrencies as _LegacyCrypto,
    )
    from alpha_vantage.foreignexchange import (  # type: ignore[import-not-found]
        ForeignExchange as _LegacyForex,
    )

    _AVAILABLE = True
except ImportError:  # pragma: no cover - optional dep
    _LegacyTimeSeries = None  # type: ignore[assignment]
    _LegacyTechIndicators = None  # type: ignore[assignment]
    _LegacyFundamentals = None  # type: ignore[assignment]
    _LegacyCrypto = None  # type: ignore[assignment]
    _LegacyForex = None  # type: ignore[assignment]
    _AVAILABLE = False


def legacy_available() -> bool:
    return _AVAILABLE


def _require(cls: Optional[Any]) -> Any:
    if not _AVAILABLE or cls is None:
        raise AlphaVantageError(
            "Optional 'alpha_vantage' package not installed. "
            "Install with: pip install alphavantage-client[fallback]"
        )
    return cls


def legacy_timeseries(api_key: Optional[str] = None, **kwargs: Any) -> Any:
    key = api_key or load_api_key(strict=True)
    return _require(_LegacyTimeSeries)(key=key, **kwargs)


def legacy_techindicators(api_key: Optional[str] = None, **kwargs: Any) -> Any:
    key = api_key or load_api_key(strict=True)
    return _require(_LegacyTechIndicators)(key=key, **kwargs)


def legacy_fundamentals(api_key: Optional[str] = None, **kwargs: Any) -> Any:
    key = api_key or load_api_key(strict=True)
    return _require(_LegacyFundamentals)(key=key, **kwargs)


def legacy_crypto(api_key: Optional[str] = None, **kwargs: Any) -> Any:
    key = api_key or load_api_key(strict=True)
    return _require(_LegacyCrypto)(key=key, **kwargs)


def legacy_forex(api_key: Optional[str] = None, **kwargs: Any) -> Any:
    key = api_key or load_api_key(strict=True)
    return _require(_LegacyForex)(key=key, **kwargs)


__all__ = [
    "legacy_available",
    "legacy_crypto",
    "legacy_forex",
    "legacy_fundamentals",
    "legacy_techindicators",
    "legacy_timeseries",
]
