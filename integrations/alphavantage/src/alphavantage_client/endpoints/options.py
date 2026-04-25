"""Options Data endpoints."""

from __future__ import annotations

from typing import Any, List, Optional

from ..models.options import OptionChain, OptionContract, OptionsRatioPoint
from ._base import BaseEndpoint


class Options(BaseEndpoint):
    """Realtime + historical options (chains, PCR, VOI ratio)."""

    # ------------------------------------------------------------------
    # Chains
    # ------------------------------------------------------------------

    def realtime(self, symbol: str, *, contract: Optional[str] = None) -> OptionChain:
        params: dict[str, Any] = {"function": "REALTIME_OPTIONS", "symbol": symbol}
        if contract:
            params["contract"] = contract
        payload = self._sync_request(params)
        return self._chain(payload, symbol, "REALTIME_OPTIONS")

    async def arealtime(self, symbol: str, *, contract: Optional[str] = None) -> OptionChain:
        params: dict[str, Any] = {"function": "REALTIME_OPTIONS", "symbol": symbol}
        if contract:
            params["contract"] = contract
        payload = await self._async_request(params)
        return self._chain(payload, symbol, "REALTIME_OPTIONS")

    def historical(self, symbol: str, *, date: Optional[str] = None) -> OptionChain:
        params: dict[str, Any] = {"function": "HISTORICAL_OPTIONS", "symbol": symbol}
        if date:
            params["date"] = date
        payload = self._sync_request(params)
        return self._chain(payload, symbol, "HISTORICAL_OPTIONS")

    async def ahistorical(self, symbol: str, *, date: Optional[str] = None) -> OptionChain:
        params: dict[str, Any] = {"function": "HISTORICAL_OPTIONS", "symbol": symbol}
        if date:
            params["date"] = date
        payload = await self._async_request(params)
        return self._chain(payload, symbol, "HISTORICAL_OPTIONS")

    # ------------------------------------------------------------------
    # Ratios
    # ------------------------------------------------------------------

    def realtime_put_call_ratio(self, symbol: str) -> List[OptionsRatioPoint]:
        return self._ratio(
            "REALTIME_PUT_CALL_RATIO",
            symbol,
            data_key="data",
            async_mode=False,
        )

    async def arealtime_put_call_ratio(self, symbol: str) -> List[OptionsRatioPoint]:
        return await self._aratio("REALTIME_PUT_CALL_RATIO", symbol)

    def historical_put_call_ratio(
        self,
        symbol: str,
        *,
        date: Optional[str] = None,
    ) -> List[OptionsRatioPoint]:
        return self._ratio(
            "HISTORICAL_PUT_CALL_RATIO",
            symbol,
            data_key="data",
            async_mode=False,
            date=date,
        )

    async def ahistorical_put_call_ratio(
        self,
        symbol: str,
        *,
        date: Optional[str] = None,
    ) -> List[OptionsRatioPoint]:
        return await self._aratio("HISTORICAL_PUT_CALL_RATIO", symbol, date=date)

    def realtime_voi_ratio(self, symbol: str) -> List[OptionsRatioPoint]:
        return self._ratio("REALTIME_VOI_RATIO", symbol, data_key="data", async_mode=False)

    async def arealtime_voi_ratio(self, symbol: str) -> List[OptionsRatioPoint]:
        return await self._aratio("REALTIME_VOI_RATIO", symbol)

    def historical_voi_ratio(
        self,
        symbol: str,
        *,
        date: Optional[str] = None,
    ) -> List[OptionsRatioPoint]:
        return self._ratio(
            "HISTORICAL_VOI_RATIO",
            symbol,
            data_key="data",
            async_mode=False,
            date=date,
        )

    async def ahistorical_voi_ratio(
        self,
        symbol: str,
        *,
        date: Optional[str] = None,
    ) -> List[OptionsRatioPoint]:
        return await self._aratio("HISTORICAL_VOI_RATIO", symbol, date=date)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _chain(self, payload: dict, symbol: str, function: str) -> OptionChain:
        data = payload.get("data") or payload.get("options") or []
        return OptionChain(
            symbol=symbol,
            endpoint=function,
            message=payload.get("message") or payload.get("endpoint"),
            data=[OptionContract.model_validate(c) for c in data],
        )

    def _ratio(
        self,
        function: str,
        symbol: str,
        *,
        data_key: str,
        async_mode: bool,
        date: Optional[str] = None,
    ) -> List[OptionsRatioPoint]:
        params: dict[str, Any] = {"function": function, "symbol": symbol}
        if date:
            params["date"] = date
        payload = self._sync_request(params)
        data = payload.get(data_key) or []
        return [
            OptionsRatioPoint(date=row.get("date") or "", symbol=symbol, value=_float(row.get("value")))
            for row in data
        ]

    async def _aratio(
        self,
        function: str,
        symbol: str,
        *,
        date: Optional[str] = None,
    ) -> List[OptionsRatioPoint]:
        params: dict[str, Any] = {"function": function, "symbol": symbol}
        if date:
            params["date"] = date
        payload = await self._async_request(params)
        data = payload.get("data") or []
        return [
            OptionsRatioPoint(date=row.get("date") or "", symbol=symbol, value=_float(row.get("value")))
            for row in data
        ]


def _float(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


__all__ = ["Options"]
