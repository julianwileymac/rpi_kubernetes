"""Custom Alpha Vantage client engine.

Public API:

* :class:`AlphaVantageClient` - unified sync + async facade.
* Endpoint classes from :mod:`.endpoints`.
* Typed errors from :mod:`._errors`.
* Enums from :mod:`._types`.
* Pydantic response models from :mod:`.models`.
"""

from ._credentials import load_api_key
from ._errors import (
    AlphaVantageError,
    AlphaVantagePayloadError,
    InvalidApiKeyError,
    InvalidSymbolError,
    PremiumEndpointError,
    RateLimitError,
    RateLimitKind,
    TransientError,
)
from ._rate_limiter import RateLimiter, RateLimiterSnapshot
from ._types import (
    AnalyticsCalculation,
    Entitlement,
    Interval,
    MaType,
    NewsSort,
    OutputFormat,
    OutputSize,
    SeriesType,
)
from .client import AlphaVantageClient
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

__all__ = [
    "AlphaVantageClient",
    "AlphaVantageError",
    "AlphaVantagePayloadError",
    "AnalyticsCalculation",
    "Commodities",
    "Crypto",
    "Economics",
    "Entitlement",
    "Forex",
    "Fundamentals",
    "Indices",
    "Intelligence",
    "Interval",
    "InvalidApiKeyError",
    "InvalidSymbolError",
    "MaType",
    "NewsSort",
    "Options",
    "OutputFormat",
    "OutputSize",
    "PremiumEndpointError",
    "RateLimitError",
    "RateLimitKind",
    "RateLimiter",
    "RateLimiterSnapshot",
    "SeriesType",
    "Technicals",
    "TimeSeries",
    "TransientError",
    "load_api_key",
]

__version__ = "0.1.0"
