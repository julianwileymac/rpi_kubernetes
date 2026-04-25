"""Forex (FX) endpoints."""

from __future__ import annotations

from typing import Any, Optional

from .._parsers import extract_series
from .._types import Interval, OutputSize
from ..models.forex import FxBar, FxIntradaySeries, FxRate, FxSeries
from ._base import BaseEndpoint


_SERIES_KEYS = {
    "FX_INTRADAY": lambda interval: f"Time Series FX ({interval})",
    "FX_DAILY": lambda _: "Time Series FX (Daily)",
    "FX_WEEKLY": lambda _: "Time Series FX (Weekly)",
    "FX_MONTHLY": lambda _: "Time Series FX (Monthly)",
}


def _value(v: Any) -> str:
    return v.value if hasattr(v, "value") else str(v)


class Forex(BaseEndpoint):
    """FX exchange rates + intraday/daily/weekly/monthly FX bars."""

    def exchange_rate(self, from_currency: str, to_currency: str) -> FxRate:
        params = {
            "function": "CURRENCY_EXCHANGE_RATE",
            "from_currency": from_currency,
            "to_currency": to_currency,
        }
        payload = self._sync_request(params)
        return FxRate.model_validate(payload.get("Realtime Currency Exchange Rate") or {})

    async def aexchange_rate(self, from_currency: str, to_currency: str) -> FxRate:
        params = {
            "function": "CURRENCY_EXCHANGE_RATE",
            "from_currency": from_currency,
            "to_currency": to_currency,
        }
        payload = await self._async_request(params)
        return FxRate.model_validate(payload.get("Realtime Currency Exchange Rate") or {})

    def _series_params(
        self,
        function: str,
        *,
        from_symbol: str,
        to_symbol: str,
        interval: Optional[Interval | str] = None,
        outputsize: Optional[OutputSize | str] = None,
        datatype: Optional[str] = None,
    ) -> dict:
        params: dict[str, Any] = {
            "function": function,
            "from_symbol": from_symbol,
            "to_symbol": to_symbol,
        }
        if interval:
            params["interval"] = _value(interval)
        if outputsize:
            params["outputsize"] = _value(outputsize)
        if datatype:
            params["datatype"] = datatype
        return params

    def _build_series(
        self,
        function: str,
        from_symbol: str,
        to_symbol: str,
        payload: dict,
        *,
        interval: Optional[str],
    ) -> FxSeries:
        key_fn = _SERIES_KEYS.get(function)
        series_key = key_fn(interval) if key_fn else ""
        rows = extract_series(payload, series_key)
        bars = [FxBar.model_validate(row) for row in rows]
        cls = FxIntradaySeries if function == "FX_INTRADAY" else FxSeries
        return cls(
            function=function,
            from_symbol=from_symbol,
            to_symbol=to_symbol,
            interval=interval,
            bars=bars,
        )

    def intraday(self, **kwargs: Any) -> FxIntradaySeries:
        params = self._series_params("FX_INTRADAY", **kwargs)
        payload = self._sync_request(params)
        return self._build_series(
            "FX_INTRADAY",
            kwargs["from_symbol"],
            kwargs["to_symbol"],
            payload,
            interval=params.get("interval"),
        )

    async def aintraday(self, **kwargs: Any) -> FxIntradaySeries:
        params = self._series_params("FX_INTRADAY", **kwargs)
        payload = await self._async_request(params)
        return self._build_series(
            "FX_INTRADAY",
            kwargs["from_symbol"],
            kwargs["to_symbol"],
            payload,
            interval=params.get("interval"),
        )

    def daily(self, **kwargs: Any) -> FxSeries:
        params = self._series_params("FX_DAILY", **kwargs)
        payload = self._sync_request(params)
        return self._build_series(
            "FX_DAILY", kwargs["from_symbol"], kwargs["to_symbol"], payload, interval=None
        )

    async def adaily(self, **kwargs: Any) -> FxSeries:
        params = self._series_params("FX_DAILY", **kwargs)
        payload = await self._async_request(params)
        return self._build_series(
            "FX_DAILY", kwargs["from_symbol"], kwargs["to_symbol"], payload, interval=None
        )

    def weekly(self, **kwargs: Any) -> FxSeries:
        params = self._series_params("FX_WEEKLY", **kwargs)
        payload = self._sync_request(params)
        return self._build_series(
            "FX_WEEKLY", kwargs["from_symbol"], kwargs["to_symbol"], payload, interval=None
        )

    async def aweekly(self, **kwargs: Any) -> FxSeries:
        params = self._series_params("FX_WEEKLY", **kwargs)
        payload = await self._async_request(params)
        return self._build_series(
            "FX_WEEKLY", kwargs["from_symbol"], kwargs["to_symbol"], payload, interval=None
        )

    def monthly(self, **kwargs: Any) -> FxSeries:
        params = self._series_params("FX_MONTHLY", **kwargs)
        payload = self._sync_request(params)
        return self._build_series(
            "FX_MONTHLY", kwargs["from_symbol"], kwargs["to_symbol"], payload, interval=None
        )

    async def amonthly(self, **kwargs: Any) -> FxSeries:
        params = self._series_params("FX_MONTHLY", **kwargs)
        payload = await self._async_request(params)
        return self._build_series(
            "FX_MONTHLY", kwargs["from_symbol"], kwargs["to_symbol"], payload, interval=None
        )


__all__ = ["Forex"]
