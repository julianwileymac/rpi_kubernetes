"""Index data response models."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from .timeseries import OhlcvBar


class IndexSeries(BaseModel):
    model_config = ConfigDict(extra="allow")

    function: str
    index_name: str
    interval: Optional[str] = None
    bars: List[OhlcvBar] = []


class IndexCatalogEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: Optional[str] = None
    name: Optional[str] = None
    region: Optional[str] = None
    currency: Optional[str] = None
    entitlement: Optional[str] = None


__all__ = ["IndexCatalogEntry", "IndexSeries"]
