"""Economic indicator endpoints."""

from __future__ import annotations

from typing import Any, Optional

from ..models.economics import EconIndicatorPoint, EconIndicatorSeries
from ._base import BaseEndpoint


def _series(function: str, interval: Optional[str], payload: dict) -> EconIndicatorSeries:
    return EconIndicatorSeries(
        name=payload.get("name") or function,
        interval=interval,
        unit=payload.get("unit"),
        data=[EconIndicatorPoint.model_validate(d) for d in (payload.get("data") or [])],
    )


class Economics(BaseEndpoint):
    """US/global economic indicators from AV."""

    def _get(self, function: str, **params: Any) -> EconIndicatorSeries:
        query: dict[str, Any] = {"function": function, **params}
        payload = self._sync_request(query)
        return _series(function, params.get("interval"), payload)

    async def _aget(self, function: str, **params: Any) -> EconIndicatorSeries:
        query: dict[str, Any] = {"function": function, **params}
        payload = await self._async_request(query)
        return _series(function, params.get("interval"), payload)

    def real_gdp(self, *, interval: str = "annual") -> EconIndicatorSeries:
        return self._get("REAL_GDP", interval=interval)

    async def areal_gdp(self, *, interval: str = "annual") -> EconIndicatorSeries:
        return await self._aget("REAL_GDP", interval=interval)

    def real_gdp_per_capita(self) -> EconIndicatorSeries:
        return self._get("REAL_GDP_PER_CAPITA")

    async def areal_gdp_per_capita(self) -> EconIndicatorSeries:
        return await self._aget("REAL_GDP_PER_CAPITA")

    def treasury_yield(
        self,
        *,
        interval: str = "monthly",
        maturity: str = "10year",
    ) -> EconIndicatorSeries:
        return self._get("TREASURY_YIELD", interval=interval, maturity=maturity)

    async def atreasury_yield(
        self,
        *,
        interval: str = "monthly",
        maturity: str = "10year",
    ) -> EconIndicatorSeries:
        return await self._aget("TREASURY_YIELD", interval=interval, maturity=maturity)

    def federal_funds_rate(self, *, interval: str = "monthly") -> EconIndicatorSeries:
        return self._get("FEDERAL_FUNDS_RATE", interval=interval)

    async def afederal_funds_rate(self, *, interval: str = "monthly") -> EconIndicatorSeries:
        return await self._aget("FEDERAL_FUNDS_RATE", interval=interval)

    def cpi(self, *, interval: str = "monthly") -> EconIndicatorSeries:
        return self._get("CPI", interval=interval)

    async def acpi(self, *, interval: str = "monthly") -> EconIndicatorSeries:
        return await self._aget("CPI", interval=interval)

    def inflation(self) -> EconIndicatorSeries:
        return self._get("INFLATION")

    async def ainflation(self) -> EconIndicatorSeries:
        return await self._aget("INFLATION")

    def retail_sales(self) -> EconIndicatorSeries:
        return self._get("RETAIL_SALES")

    async def aretail_sales(self) -> EconIndicatorSeries:
        return await self._aget("RETAIL_SALES")

    def durable_goods(self) -> EconIndicatorSeries:
        return self._get("DURABLES")

    async def adurable_goods(self) -> EconIndicatorSeries:
        return await self._aget("DURABLES")

    def unemployment(self) -> EconIndicatorSeries:
        return self._get("UNEMPLOYMENT")

    async def aunemployment(self) -> EconIndicatorSeries:
        return await self._aget("UNEMPLOYMENT")

    def nonfarm_payroll(self) -> EconIndicatorSeries:
        return self._get("NONFARM_PAYROLL")

    async def anonfarm_payroll(self) -> EconIndicatorSeries:
        return await self._aget("NONFARM_PAYROLL")

    def by_name(self, name: str, **params: Any) -> EconIndicatorSeries:
        return self._get(name.upper(), **params)

    async def aby_name(self, name: str, **params: Any) -> EconIndicatorSeries:
        return await self._aget(name.upper(), **params)


__all__ = ["Economics"]
