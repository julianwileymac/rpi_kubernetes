"""Cryptocurrency response models."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CryptoQuote(BaseModel):
    """Realtime digital currency exchange rate block."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    from_currency_code: Optional[str] = Field(
        default=None, alias="1. From_Currency Code"
    )
    from_currency_name: Optional[str] = Field(
        default=None, alias="2. From_Currency Name"
    )
    to_currency_code: Optional[str] = Field(default=None, alias="3. To_Currency Code")
    to_currency_name: Optional[str] = Field(default=None, alias="4. To_Currency Name")
    exchange_rate: Optional[float] = Field(default=None, alias="5. Exchange Rate")
    last_refreshed: Optional[str] = Field(default=None, alias="6. Last Refreshed")
    time_zone: Optional[str] = Field(default=None, alias="7. Time Zone")
    bid_price: Optional[float] = Field(default=None, alias="8. Bid Price")
    ask_price: Optional[float] = Field(default=None, alias="9. Ask Price")


class CryptoBar(BaseModel):
    model_config = ConfigDict(extra="allow")

    timestamp: str
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None
    market_cap: Optional[float] = None


class CryptoSeries(BaseModel):
    model_config = ConfigDict(extra="allow")

    function: str
    symbol: str
    market: Optional[str] = None
    interval: Optional[str] = None
    bars: List[CryptoBar] = []


class CryptoIntradaySeries(CryptoSeries):
    pass


__all__ = ["CryptoBar", "CryptoIntradaySeries", "CryptoQuote", "CryptoSeries"]
