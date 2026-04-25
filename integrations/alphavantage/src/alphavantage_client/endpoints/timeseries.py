"""Time Series Stock Data endpoints."""

from __future__ import annotations

from typing import Any, List, Optional, Sequence

from .._parsers import coerce_meta, extract_series
from .._types import Entitlement, Interval, OutputSize
from ..models.quotes import GlobalQuote, MarketStatusEntry, MarketStatusPayload, SymbolSearchMatch
from ..models.timeseries import OhlcvBar, TimeSeriesPayload
from ._base import BaseEndpoint


_SERIES_KEY_MAP = {
    "TIME_SERIES_INTRADAY": None,
    "TIME_SERIES_DAILY": "Time Series (Daily)",
    "TIME_SERIES_DAILY_ADJUSTED": "Time Series (Daily)",
    "TIME_SERIES_WEEKLY": "Weekly Time Series",
    "TIME_SERIES_WEEKLY_ADJUSTED": "Weekly Adjusted Time Series",
    "TIME_SERIES_MONTHLY": "Monthly Time Series",
    "TIME_SERIES_MONTHLY_ADJUSTED": "Monthly Adjusted Time Series",
}


def _intraday_series_key(interval: str) -> str:
    return f"Time Series ({interval})"


def _find_series_key(payload: dict) -> Optional[str]:
    for key in payload.keys():
        low = key.lower()
        if "time series" in low or "weekly" in low or "monthly" in low:
            return key
    return None


def _build_payload(
    function: str,
    symbol: str,
    payload: dict,
    *,
    interval: Optional[str] = None,
    output_size: Optional[str] = None,
    entitlement: Optional[str] = None,
) -> TimeSeriesPayload:
    series_key = _SERIES_KEY_MAP.get(function)
    if function == "TIME_SERIES_INTRADAY" and interval:
        series_key = _intraday_series_key(interval)
    if series_key is None:
        series_key = _find_series_key(payload) or ""
    rows = extract_series(payload, series_key)
    bars = [OhlcvBar.model_validate(row) for row in rows]
    return TimeSeriesPayload(
        function=function,
        symbol=symbol,
        interval=interval,
        output_size=output_size,
        entitlement=entitlement,
        metadata=coerce_meta(payload) or None,
        bars=bars,
    )


class TimeSeries(BaseEndpoint):
    """Core time series endpoints (intraday, daily, weekly, monthly + utilities)."""

    # ------------------------------------------------------------------
    # Intraday
    # ------------------------------------------------------------------

    def _intraday_params(
        self,
        symbol: str,
        *,
        interval: Interval | str = Interval.MIN_5,
        outputsize: OutputSize | str = OutputSize.COMPACT,
        month: Optional[str] = None,
        adjusted: Optional[bool] = None,
        extended_hours: Optional[bool] = None,
        entitlement: Optional[Entitlement | str] = None,
        datatype: Optional[str] = None,
    ) -> dict:
        params: dict[str, Any] = {
            "function": "TIME_SERIES_INTRADAY",
            "symbol": symbol,
            "interval": _value(interval),
            "outputsize": _value(outputsize),
        }
        if month:
            params["month"] = month
        if adjusted is not None:
            params["adjusted"] = "true" if adjusted else "false"
        if extended_hours is not None:
            params["extended_hours"] = "true" if extended_hours else "false"
        if entitlement:
            params["entitlement"] = _value(entitlement)
        if datatype:
            params["datatype"] = datatype
        return params

    def intraday(self, symbol: str, **kwargs: Any) -> TimeSeriesPayload:
        params = self._intraday_params(symbol, **kwargs)
        payload = self._sync_request(params)
        return _build_payload(
            "TIME_SERIES_INTRADAY",
            symbol,
            payload,
            interval=params.get("interval"),
            output_size=params.get("outputsize"),
            entitlement=params.get("entitlement"),
        )

    async def aintraday(self, symbol: str, **kwargs: Any) -> TimeSeriesPayload:
        params = self._intraday_params(symbol, **kwargs)
        payload = await self._async_request(params)
        return _build_payload(
            "TIME_SERIES_INTRADAY",
            symbol,
            payload,
            interval=params.get("interval"),
            output_size=params.get("outputsize"),
            entitlement=params.get("entitlement"),
        )

    # ------------------------------------------------------------------
    # Daily / Weekly / Monthly
    # ------------------------------------------------------------------

    def _tseries_params(
        self,
        function: str,
        symbol: str,
        *,
        outputsize: OutputSize | str = OutputSize.COMPACT,
        entitlement: Optional[Entitlement | str] = None,
        datatype: Optional[str] = None,
    ) -> dict:
        params: dict[str, Any] = {
            "function": function,
            "symbol": symbol,
            "outputsize": _value(outputsize),
        }
        if entitlement:
            params["entitlement"] = _value(entitlement)
        if datatype:
            params["datatype"] = datatype
        return params

    def daily(self, symbol: str, **kwargs: Any) -> TimeSeriesPayload:
        params = self._tseries_params("TIME_SERIES_DAILY", symbol, **kwargs)
        payload = self._sync_request(params)
        return _build_payload("TIME_SERIES_DAILY", symbol, payload,
                              output_size=params.get("outputsize"))

    async def adaily(self, symbol: str, **kwargs: Any) -> TimeSeriesPayload:
        params = self._tseries_params("TIME_SERIES_DAILY", symbol, **kwargs)
        payload = await self._async_request(params)
        return _build_payload("TIME_SERIES_DAILY", symbol, payload,
                              output_size=params.get("outputsize"))

    def daily_adjusted(self, symbol: str, **kwargs: Any) -> TimeSeriesPayload:
        params = self._tseries_params("TIME_SERIES_DAILY_ADJUSTED", symbol, **kwargs)
        payload = self._sync_request(params)
        return _build_payload("TIME_SERIES_DAILY_ADJUSTED", symbol, payload,
                              output_size=params.get("outputsize"))

    async def adaily_adjusted(self, symbol: str, **kwargs: Any) -> TimeSeriesPayload:
        params = self._tseries_params("TIME_SERIES_DAILY_ADJUSTED", symbol, **kwargs)
        payload = await self._async_request(params)
        return _build_payload("TIME_SERIES_DAILY_ADJUSTED", symbol, payload,
                              output_size=params.get("outputsize"))

    def weekly(self, symbol: str, *, datatype: Optional[str] = None) -> TimeSeriesPayload:
        params = {"function": "TIME_SERIES_WEEKLY", "symbol": symbol}
        if datatype:
            params["datatype"] = datatype
        payload = self._sync_request(params)
        return _build_payload("TIME_SERIES_WEEKLY", symbol, payload)

    async def aweekly(self, symbol: str, *, datatype: Optional[str] = None) -> TimeSeriesPayload:
        params = {"function": "TIME_SERIES_WEEKLY", "symbol": symbol}
        if datatype:
            params["datatype"] = datatype
        payload = await self._async_request(params)
        return _build_payload("TIME_SERIES_WEEKLY", symbol, payload)

    def weekly_adjusted(self, symbol: str, *, datatype: Optional[str] = None) -> TimeSeriesPayload:
        params = {"function": "TIME_SERIES_WEEKLY_ADJUSTED", "symbol": symbol}
        if datatype:
            params["datatype"] = datatype
        payload = self._sync_request(params)
        return _build_payload("TIME_SERIES_WEEKLY_ADJUSTED", symbol, payload)

    async def aweekly_adjusted(self, symbol: str, *, datatype: Optional[str] = None) -> TimeSeriesPayload:
        params = {"function": "TIME_SERIES_WEEKLY_ADJUSTED", "symbol": symbol}
        if datatype:
            params["datatype"] = datatype
        payload = await self._async_request(params)
        return _build_payload("TIME_SERIES_WEEKLY_ADJUSTED", symbol, payload)

    def monthly(self, symbol: str, *, datatype: Optional[str] = None) -> TimeSeriesPayload:
        params = {"function": "TIME_SERIES_MONTHLY", "symbol": symbol}
        if datatype:
            params["datatype"] = datatype
        payload = self._sync_request(params)
        return _build_payload("TIME_SERIES_MONTHLY", symbol, payload)

    async def amonthly(self, symbol: str, *, datatype: Optional[str] = None) -> TimeSeriesPayload:
        params = {"function": "TIME_SERIES_MONTHLY", "symbol": symbol}
        if datatype:
            params["datatype"] = datatype
        payload = await self._async_request(params)
        return _build_payload("TIME_SERIES_MONTHLY", symbol, payload)

    def monthly_adjusted(self, symbol: str, *, datatype: Optional[str] = None) -> TimeSeriesPayload:
        params = {"function": "TIME_SERIES_MONTHLY_ADJUSTED", "symbol": symbol}
        if datatype:
            params["datatype"] = datatype
        payload = self._sync_request(params)
        return _build_payload("TIME_SERIES_MONTHLY_ADJUSTED", symbol, payload)

    async def amonthly_adjusted(
        self, symbol: str, *, datatype: Optional[str] = None
    ) -> TimeSeriesPayload:
        params = {"function": "TIME_SERIES_MONTHLY_ADJUSTED", "symbol": symbol}
        if datatype:
            params["datatype"] = datatype
        payload = await self._async_request(params)
        return _build_payload("TIME_SERIES_MONTHLY_ADJUSTED", symbol, payload)

    # ------------------------------------------------------------------
    # Quotes / utilities
    # ------------------------------------------------------------------

    def global_quote(
        self,
        symbol: str,
        *,
        entitlement: Optional[Entitlement | str] = None,
    ) -> GlobalQuote:
        params: dict[str, Any] = {"function": "GLOBAL_QUOTE", "symbol": symbol}
        if entitlement:
            params["entitlement"] = _value(entitlement)
        payload = self._sync_request(params)
        return GlobalQuote.model_validate(payload.get("Global Quote") or {})

    async def aglobal_quote(
        self,
        symbol: str,
        *,
        entitlement: Optional[Entitlement | str] = None,
    ) -> GlobalQuote:
        params: dict[str, Any] = {"function": "GLOBAL_QUOTE", "symbol": symbol}
        if entitlement:
            params["entitlement"] = _value(entitlement)
        payload = await self._async_request(params)
        return GlobalQuote.model_validate(payload.get("Global Quote") or {})

    def realtime_bulk_quotes(
        self,
        symbols: Sequence[str],
        *,
        entitlement: Optional[Entitlement | str] = None,
    ) -> List[dict]:
        """REALTIME_BULK_QUOTES (premium). Returns a list of quote dicts."""

        params: dict[str, Any] = {
            "function": "REALTIME_BULK_QUOTES",
            "symbol": ",".join(symbols),
        }
        if entitlement:
            params["entitlement"] = _value(entitlement)
        payload = self._sync_request(params)
        return list(payload.get("data", []))

    async def arealtime_bulk_quotes(
        self,
        symbols: Sequence[str],
        *,
        entitlement: Optional[Entitlement | str] = None,
    ) -> List[dict]:
        params: dict[str, Any] = {
            "function": "REALTIME_BULK_QUOTES",
            "symbol": ",".join(symbols),
        }
        if entitlement:
            params["entitlement"] = _value(entitlement)
        payload = await self._async_request(params)
        return list(payload.get("data", []))

    def search(self, keywords: str) -> List[SymbolSearchMatch]:
        params = {"function": "SYMBOL_SEARCH", "keywords": keywords}
        payload = self._sync_request(params)
        return [SymbolSearchMatch.model_validate(m) for m in payload.get("bestMatches", [])]

    async def asearch(self, keywords: str) -> List[SymbolSearchMatch]:
        params = {"function": "SYMBOL_SEARCH", "keywords": keywords}
        payload = await self._async_request(params)
        return [SymbolSearchMatch.model_validate(m) for m in payload.get("bestMatches", [])]

    def market_status(self) -> MarketStatusPayload:
        payload = self._sync_request({"function": "MARKET_STATUS"})
        return MarketStatusPayload(
            endpoint=payload.get("endpoint"),
            markets=[MarketStatusEntry.model_validate(m) for m in payload.get("markets", [])],
        )

    async def amarket_status(self) -> MarketStatusPayload:
        payload = await self._async_request({"function": "MARKET_STATUS"})
        return MarketStatusPayload(
            endpoint=payload.get("endpoint"),
            markets=[MarketStatusEntry.model_validate(m) for m in payload.get("markets", [])],
        )


def _value(v: Any) -> str:
    if hasattr(v, "value"):
        return str(v.value)
    return str(v)


__all__ = ["TimeSeries"]
