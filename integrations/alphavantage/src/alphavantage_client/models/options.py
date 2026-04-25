"""Options response models."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class OptionContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    contractID: Optional[str] = None
    symbol: Optional[str] = None
    expiration: Optional[str] = None
    strike: Optional[float] = None
    type: Optional[str] = None
    last: Optional[float] = None
    mark: Optional[float] = None
    bid: Optional[float] = None
    bid_size: Optional[int] = None
    ask: Optional[float] = None
    ask_size: Optional[int] = None
    volume: Optional[int] = None
    open_interest: Optional[int] = None
    date: Optional[str] = None
    implied_volatility: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    rho: Optional[float] = None


class OptionChain(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: Optional[str] = None
    endpoint: Optional[str] = None
    message: Optional[str] = None
    data: List[OptionContract] = []


class OptionsRatioPoint(BaseModel):
    model_config = ConfigDict(extra="allow")

    date: str
    symbol: Optional[str] = None
    value: Optional[float] = None


__all__ = ["OptionChain", "OptionContract", "OptionsRatioPoint"]
