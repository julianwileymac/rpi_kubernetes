"""Economic indicator response models."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class EconIndicatorPoint(BaseModel):
    model_config = ConfigDict(extra="allow")

    date: str
    value: Optional[float] = None


class EconIndicatorSeries(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: Optional[str] = None
    interval: Optional[str] = None
    unit: Optional[str] = None
    data: List[EconIndicatorPoint] = []


__all__ = ["EconIndicatorPoint", "EconIndicatorSeries"]
