"""Commodities endpoints (WTI, Brent, Nat gas, metals, ags, gold/silver, global index)."""

from __future__ import annotations

from typing import Any, Optional

from ..models.commodities import CommodityPoint, CommoditySeries
from ._base import BaseEndpoint


_SUPPORTED_INTERVALS = {"daily", "weekly", "monthly", "quarterly", "annual"}


def _points(payload: dict) -> list[CommodityPoint]:
    return [CommodityPoint.model_validate(d) for d in (payload.get("data") or [])]


def _series(function: str, interval: Optional[str], payload: dict) -> CommoditySeries:
    return CommoditySeries(
        name=payload.get("name") or function,
        interval=interval,
        unit=payload.get("unit"),
        data=_points(payload),
    )


class Commodities(BaseEndpoint):
    """Commodity time series wrappers."""

    def _generic(
        self,
        function: str,
        *,
        interval: Optional[str] = None,
    ) -> CommoditySeries:
        params: dict[str, Any] = {"function": function}
        if interval:
            params["interval"] = interval
        payload = self._sync_request(params)
        return _series(function, interval, payload)

    async def _ageneric(
        self,
        function: str,
        *,
        interval: Optional[str] = None,
    ) -> CommoditySeries:
        params: dict[str, Any] = {"function": function}
        if interval:
            params["interval"] = interval
        payload = await self._async_request(params)
        return _series(function, interval, payload)

    # Individual commodities
    def wti(self, *, interval: str = "monthly") -> CommoditySeries:
        return self._generic("WTI", interval=interval)

    async def awti(self, *, interval: str = "monthly") -> CommoditySeries:
        return await self._ageneric("WTI", interval=interval)

    def brent(self, *, interval: str = "monthly") -> CommoditySeries:
        return self._generic("BRENT", interval=interval)

    async def abrent(self, *, interval: str = "monthly") -> CommoditySeries:
        return await self._ageneric("BRENT", interval=interval)

    def natural_gas(self, *, interval: str = "monthly") -> CommoditySeries:
        return self._generic("NATURAL_GAS", interval=interval)

    async def anatural_gas(self, *, interval: str = "monthly") -> CommoditySeries:
        return await self._ageneric("NATURAL_GAS", interval=interval)

    def copper(self, *, interval: str = "monthly") -> CommoditySeries:
        return self._generic("COPPER", interval=interval)

    async def acopper(self, *, interval: str = "monthly") -> CommoditySeries:
        return await self._ageneric("COPPER", interval=interval)

    def aluminum(self, *, interval: str = "monthly") -> CommoditySeries:
        return self._generic("ALUMINUM", interval=interval)

    async def aaluminum(self, *, interval: str = "monthly") -> CommoditySeries:
        return await self._ageneric("ALUMINUM", interval=interval)

    def wheat(self, *, interval: str = "monthly") -> CommoditySeries:
        return self._generic("WHEAT", interval=interval)

    async def awheat(self, *, interval: str = "monthly") -> CommoditySeries:
        return await self._ageneric("WHEAT", interval=interval)

    def corn(self, *, interval: str = "monthly") -> CommoditySeries:
        return self._generic("CORN", interval=interval)

    async def acorn(self, *, interval: str = "monthly") -> CommoditySeries:
        return await self._ageneric("CORN", interval=interval)

    def cotton(self, *, interval: str = "monthly") -> CommoditySeries:
        return self._generic("COTTON", interval=interval)

    async def acotton(self, *, interval: str = "monthly") -> CommoditySeries:
        return await self._ageneric("COTTON", interval=interval)

    def sugar(self, *, interval: str = "monthly") -> CommoditySeries:
        return self._generic("SUGAR", interval=interval)

    async def asugar(self, *, interval: str = "monthly") -> CommoditySeries:
        return await self._ageneric("SUGAR", interval=interval)

    def coffee(self, *, interval: str = "monthly") -> CommoditySeries:
        return self._generic("COFFEE", interval=interval)

    async def acoffee(self, *, interval: str = "monthly") -> CommoditySeries:
        return await self._ageneric("COFFEE", interval=interval)

    def global_index(self, *, interval: str = "monthly") -> CommoditySeries:
        return self._generic("ALL_COMMODITIES", interval=interval)

    async def aglobal_index(self, *, interval: str = "monthly") -> CommoditySeries:
        return await self._ageneric("ALL_COMMODITIES", interval=interval)

    # Gold / silver (spot + historical)
    def gold_silver_spot(self) -> dict:
        return self._sync_request({"function": "GOLD_SILVER_SPOT"})

    async def agold_silver_spot(self) -> dict:
        return await self._async_request({"function": "GOLD_SILVER_SPOT"})

    def gold_silver_history(self, *, interval: str = "monthly") -> CommoditySeries:
        return self._generic("GOLD_SILVER_HISTORY", interval=interval)

    async def agold_silver_history(self, *, interval: str = "monthly") -> CommoditySeries:
        return await self._ageneric("GOLD_SILVER_HISTORY", interval=interval)

    def by_name(self, name: str, *, interval: str = "monthly") -> CommoditySeries:
        """Fall-through accessor for any supported commodity function by name."""

        return self._generic(name.upper(), interval=interval)

    async def aby_name(self, name: str, *, interval: str = "monthly") -> CommoditySeries:
        return await self._ageneric(name.upper(), interval=interval)


__all__ = ["Commodities"]
