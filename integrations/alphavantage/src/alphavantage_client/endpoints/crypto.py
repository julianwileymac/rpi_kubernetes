"""Cryptocurrency endpoints."""

from __future__ import annotations

from typing import Any, Optional

from .._parsers import extract_series
from .._types import Interval, OutputSize
from ..models.crypto import CryptoBar, CryptoIntradaySeries, CryptoQuote, CryptoSeries
from ._base import BaseEndpoint


_KEY_BY_FUNCTION = {
    "CRYPTO_INTRADAY": lambda interval: f"Time Series Crypto ({interval})",
    "DIGITAL_CURRENCY_DAILY": lambda _: "Time Series (Digital Currency Daily)",
    "DIGITAL_CURRENCY_WEEKLY": lambda _: "Time Series (Digital Currency Weekly)",
    "DIGITAL_CURRENCY_MONTHLY": lambda _: "Time Series (Digital Currency Monthly)",
}


def _value(v: Any) -> str:
    return v.value if hasattr(v, "value") else str(v)


class Crypto(BaseEndpoint):
    """Digital currency exchange rates + intraday / daily / weekly / monthly bars."""

    def exchange_rate(self, symbol: str, market: str) -> CryptoQuote:
        params = {
            "function": "CURRENCY_EXCHANGE_RATE",
            "from_currency": symbol,
            "to_currency": market,
        }
        payload = self._sync_request(params)
        return CryptoQuote.model_validate(payload.get("Realtime Currency Exchange Rate") or {})

    async def aexchange_rate(self, symbol: str, market: str) -> CryptoQuote:
        params = {
            "function": "CURRENCY_EXCHANGE_RATE",
            "from_currency": symbol,
            "to_currency": market,
        }
        payload = await self._async_request(params)
        return CryptoQuote.model_validate(payload.get("Realtime Currency Exchange Rate") or {})

    def _build_series(
        self,
        function: str,
        symbol: str,
        market: Optional[str],
        payload: dict,
        *,
        interval: Optional[str],
    ) -> CryptoSeries:
        key_fn = _KEY_BY_FUNCTION.get(function)
        series_key = key_fn(interval) if key_fn else ""
        rows = extract_series(payload, series_key)
        bars = [CryptoBar.model_validate(row) for row in rows]
        cls = CryptoIntradaySeries if function == "CRYPTO_INTRADAY" else CryptoSeries
        return cls(
            function=function,
            symbol=symbol,
            market=market,
            interval=interval,
            bars=bars,
        )

    def intraday(
        self,
        symbol: str,
        market: str,
        *,
        interval: Interval | str = Interval.MIN_5,
        outputsize: OutputSize | str = OutputSize.COMPACT,
    ) -> CryptoIntradaySeries:
        params = {
            "function": "CRYPTO_INTRADAY",
            "symbol": symbol,
            "market": market,
            "interval": _value(interval),
            "outputsize": _value(outputsize),
        }
        payload = self._sync_request(params)
        return self._build_series("CRYPTO_INTRADAY", symbol, market, payload, interval=_value(interval))

    async def aintraday(
        self,
        symbol: str,
        market: str,
        *,
        interval: Interval | str = Interval.MIN_5,
        outputsize: OutputSize | str = OutputSize.COMPACT,
    ) -> CryptoIntradaySeries:
        params = {
            "function": "CRYPTO_INTRADAY",
            "symbol": symbol,
            "market": market,
            "interval": _value(interval),
            "outputsize": _value(outputsize),
        }
        payload = await self._async_request(params)
        return self._build_series("CRYPTO_INTRADAY", symbol, market, payload, interval=_value(interval))

    def daily(self, symbol: str, market: str) -> CryptoSeries:
        params = {"function": "DIGITAL_CURRENCY_DAILY", "symbol": symbol, "market": market}
        payload = self._sync_request(params)
        return self._build_series("DIGITAL_CURRENCY_DAILY", symbol, market, payload, interval=None)

    async def adaily(self, symbol: str, market: str) -> CryptoSeries:
        params = {"function": "DIGITAL_CURRENCY_DAILY", "symbol": symbol, "market": market}
        payload = await self._async_request(params)
        return self._build_series("DIGITAL_CURRENCY_DAILY", symbol, market, payload, interval=None)

    def weekly(self, symbol: str, market: str) -> CryptoSeries:
        params = {"function": "DIGITAL_CURRENCY_WEEKLY", "symbol": symbol, "market": market}
        payload = self._sync_request(params)
        return self._build_series("DIGITAL_CURRENCY_WEEKLY", symbol, market, payload, interval=None)

    async def aweekly(self, symbol: str, market: str) -> CryptoSeries:
        params = {"function": "DIGITAL_CURRENCY_WEEKLY", "symbol": symbol, "market": market}
        payload = await self._async_request(params)
        return self._build_series("DIGITAL_CURRENCY_WEEKLY", symbol, market, payload, interval=None)

    def monthly(self, symbol: str, market: str) -> CryptoSeries:
        params = {"function": "DIGITAL_CURRENCY_MONTHLY", "symbol": symbol, "market": market}
        payload = self._sync_request(params)
        return self._build_series("DIGITAL_CURRENCY_MONTHLY", symbol, market, payload, interval=None)

    async def amonthly(self, symbol: str, market: str) -> CryptoSeries:
        params = {"function": "DIGITAL_CURRENCY_MONTHLY", "symbol": symbol, "market": market}
        payload = await self._async_request(params)
        return self._build_series("DIGITAL_CURRENCY_MONTHLY", symbol, market, payload, interval=None)


__all__ = ["Crypto"]
