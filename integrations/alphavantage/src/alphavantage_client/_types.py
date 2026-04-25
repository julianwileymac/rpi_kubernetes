"""Shared enums and type aliases for the Alpha Vantage client."""

from __future__ import annotations

from enum import Enum


class Interval(str, Enum):
    """Intraday / periodic intervals."""

    MIN_1 = "1min"
    MIN_5 = "5min"
    MIN_15 = "15min"
    MIN_30 = "30min"
    MIN_60 = "60min"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMIANNUAL = "semiannual"
    ANNUAL = "annual"


class OutputSize(str, Enum):
    COMPACT = "compact"
    FULL = "full"


class SeriesType(str, Enum):
    CLOSE = "close"
    OPEN = "open"
    HIGH = "high"
    LOW = "low"


class Entitlement(str, Enum):
    """Freshness tier on supported premium endpoints."""

    REALTIME = "realtime"
    DELAYED = "delayed"


class OutputFormat(str, Enum):
    JSON = "json"
    PANDAS = "pandas"
    CSV = "csv"
    RAW = "raw"


class NewsSort(str, Enum):
    LATEST = "LATEST"
    EARLIEST = "EARLIEST"
    RELEVANCE = "RELEVANCE"


class AnalyticsCalculation(str, Enum):
    MIN = "MIN"
    MAX = "MAX"
    MEAN = "MEAN"
    MEDIAN = "MEDIAN"
    STDDEV = "STDDEV"
    CUMULATIVE_RETURN = "CUMULATIVE_RETURN"
    VARIANCE = "VARIANCE"
    MAX_DRAWDOWN = "MAX_DRAWDOWN"
    HISTOGRAM = "HISTOGRAM"
    AUTOCORRELATION = "AUTOCORRELATION"
    COVARIANCE = "COVARIANCE"
    CORRELATION = "CORRELATION"


class MaType(int, Enum):
    """Moving-average type enum used by MACDEXT, STOCH*, BBANDS, etc."""

    SMA = 0
    EMA = 1
    WMA = 2
    DEMA = 3
    TEMA = 4
    TRIMA = 5
    T3 = 6
    KAMA = 7
    MAMA = 8


__all__ = [
    "AnalyticsCalculation",
    "Entitlement",
    "Interval",
    "MaType",
    "NewsSort",
    "OutputFormat",
    "OutputSize",
    "SeriesType",
]
