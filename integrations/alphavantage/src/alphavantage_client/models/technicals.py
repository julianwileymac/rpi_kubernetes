"""Technical indicator response models.

All 52 indicators share a common point+series shape; the ``values`` dict carries
the indicator-specific fields (e.g. ``{"SMA": 123.45}`` or ``{"MACD": ..., "MACD_Signal": ..., "MACD_Hist": ...}``).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class IndicatorPoint(BaseModel):
    model_config = ConfigDict(extra="allow")

    timestamp: str
    values: Dict[str, Optional[float]] = {}


class IndicatorSeries(BaseModel):
    model_config = ConfigDict(extra="allow")

    function: str
    symbol: str
    interval: Optional[str] = None
    time_period: Optional[int] = None
    series_type: Optional[str] = None
    indicator_name: Optional[str] = None
    points: List[IndicatorPoint] = []
    metadata: Dict[str, Any] = {}


__all__ = ["IndicatorPoint", "IndicatorSeries"]
