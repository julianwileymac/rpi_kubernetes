"""Shared Pydantic building blocks."""

from __future__ import annotations

from enum import Enum
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field


T = TypeVar("T")


class ResponseStatus(str, Enum):
    OK = "ok"
    RATE_LIMITED = "rate_limited"
    PARTIAL = "partial"
    ERROR = "error"


class AVMetadata(BaseModel):
    """AV response metadata block (variously named ``Meta Data`` / ``meta``)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    information: Optional[str] = Field(default=None, alias="information")
    symbol: Optional[str] = Field(default=None, alias="symbol")
    last_refreshed: Optional[str] = Field(default=None, alias="last refreshed")
    interval: Optional[str] = Field(default=None, alias="interval")
    output_size: Optional[str] = Field(default=None, alias="output size")
    time_zone: Optional[str] = Field(default=None, alias="time zone")


class AVResponse(BaseModel, Generic[T]):
    """Wrapper returned by higher-level backend endpoints."""

    model_config = ConfigDict(extra="allow")

    function: str
    status: ResponseStatus = ResponseStatus.OK
    metadata: Optional[AVMetadata] = None
    data: T
    note: Optional[str] = None


__all__ = ["AVMetadata", "AVResponse", "ResponseStatus"]
