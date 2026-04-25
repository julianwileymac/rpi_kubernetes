"""Commodity response models (WTI, Brent, Natural Gas, metals, ags, global index)."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CommodityPoint(BaseModel):
    model_config = ConfigDict(extra="allow")

    date: str
    value: Optional[float] = None


class CommoditySeries(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: Optional[str] = None
    interval: Optional[str] = None
    unit: Optional[str] = None
    data: List[CommodityPoint] = []


__all__ = ["CommodityPoint", "CommoditySeries"]
