"""Quote, search, and market-status models."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class GlobalQuote(BaseModel):
    """Shape of the ``Global Quote`` block from the GLOBAL_QUOTE endpoint."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    symbol: str = Field(alias="01. symbol")
    open: Optional[float] = Field(default=None, alias="02. open")
    high: Optional[float] = Field(default=None, alias="03. high")
    low: Optional[float] = Field(default=None, alias="04. low")
    price: Optional[float] = Field(default=None, alias="05. price")
    volume: Optional[float] = Field(default=None, alias="06. volume")
    latest_trading_day: Optional[str] = Field(default=None, alias="07. latest trading day")
    previous_close: Optional[float] = Field(default=None, alias="08. previous close")
    change: Optional[float] = Field(default=None, alias="09. change")
    change_percent: Optional[str] = Field(default=None, alias="10. change percent")


class SymbolSearchMatch(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    symbol: str = Field(alias="1. symbol")
    name: Optional[str] = Field(default=None, alias="2. name")
    type: Optional[str] = Field(default=None, alias="3. type")
    region: Optional[str] = Field(default=None, alias="4. region")
    market_open: Optional[str] = Field(default=None, alias="5. marketOpen")
    market_close: Optional[str] = Field(default=None, alias="6. marketClose")
    timezone: Optional[str] = Field(default=None, alias="7. timezone")
    currency: Optional[str] = Field(default=None, alias="8. currency")
    match_score: Optional[float] = Field(default=None, alias="9. matchScore")


class MarketStatusEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    market_type: Optional[str] = None
    region: Optional[str] = None
    primary_exchanges: Optional[str] = None
    local_open: Optional[str] = None
    local_close: Optional[str] = None
    current_status: Optional[str] = None
    notes: Optional[str] = None


class MarketStatusPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    endpoint: Optional[str] = None
    markets: List[MarketStatusEntry] = []


__all__ = [
    "GlobalQuote",
    "MarketStatusEntry",
    "MarketStatusPayload",
    "SymbolSearchMatch",
]
