"""Time series Pydantic models (intraday / daily / weekly / monthly OHLCV)."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .common import AVMetadata


class OhlcvBar(BaseModel):
    """Single OHLCV bar."""

    model_config = ConfigDict(extra="allow")

    timestamp: str
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    adjusted_close: Optional[float] = Field(default=None, alias="adjusted close")
    volume: Optional[float] = None
    dividend_amount: Optional[float] = Field(default=None, alias="dividend amount")
    split_coefficient: Optional[float] = Field(default=None, alias="split coefficient")


class TimeSeriesPayload(BaseModel):
    """Container for any of the TIME_SERIES_* endpoints."""

    model_config = ConfigDict(extra="allow")

    function: str
    symbol: str
    interval: Optional[str] = None
    output_size: Optional[str] = None
    entitlement: Optional[str] = None
    metadata: Optional[AVMetadata] = None
    bars: List[OhlcvBar] = Field(default_factory=list)


__all__ = ["OhlcvBar", "TimeSeriesPayload"]
