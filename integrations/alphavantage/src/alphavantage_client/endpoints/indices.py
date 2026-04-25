"""Index data endpoints (premium).

Alpha Vantage exposes major indices through dedicated FUNCTIONs. They share the
time-series response shape, so we reuse the :class:`~..models.timeseries.OhlcvBar`
parser.
"""

from __future__ import annotations

from typing import Any, List, Optional

from .._parsers import extract_series
from ..models.indices import IndexCatalogEntry, IndexSeries
from ..models.timeseries import OhlcvBar
from ._base import BaseEndpoint


_INDEX_FUNCTIONS = {
    "dji": "DOW_JONES",
    "spx": "SP500",
    "ixic": "NASDAQ_COMPOSITE",
    "ndx": "NASDAQ_100",
    "vix": "CBOE_VIX",
    "rut": "RUSSELL_2000",
}


def _find_series_key(payload: dict) -> Optional[str]:
    for key in payload.keys():
        low = key.lower()
        if "time series" in low or "historical" in low or "chart" in low:
            return key
    return None


class Indices(BaseEndpoint):
    """Major US indices + index catalog utility."""

    def _build_series(self, function: str, name: str, payload: dict, *, interval: Optional[str]) -> IndexSeries:
        key = _find_series_key(payload) or ""
        rows = extract_series(payload, key) if key else []
        return IndexSeries(
            function=function,
            index_name=name,
            interval=interval,
            bars=[OhlcvBar.model_validate(row) for row in rows],
        )

    def _index_params(self, function: str, *, interval: Optional[str]) -> dict:
        params: dict[str, Any] = {"function": function}
        if interval:
            params["interval"] = interval
        return params

    def get(self, key: str, *, interval: Optional[str] = None) -> IndexSeries:
        function = _INDEX_FUNCTIONS.get(key.lower(), key.upper())
        payload = self._sync_request(self._index_params(function, interval=interval))
        return self._build_series(function, key.upper(), payload, interval=interval)

    async def aget(self, key: str, *, interval: Optional[str] = None) -> IndexSeries:
        function = _INDEX_FUNCTIONS.get(key.lower(), key.upper())
        payload = await self._async_request(self._index_params(function, interval=interval))
        return self._build_series(function, key.upper(), payload, interval=interval)

    def catalog(self) -> List[IndexCatalogEntry]:
        payload = self._sync_request({"function": "INDEX_CATALOG"})
        entries = payload.get("catalog") or payload.get("data") or []
        return [IndexCatalogEntry.model_validate(e) for e in entries]

    async def acatalog(self) -> List[IndexCatalogEntry]:
        payload = await self._async_request({"function": "INDEX_CATALOG"})
        entries = payload.get("catalog") or payload.get("data") or []
        return [IndexCatalogEntry.model_validate(e) for e in entries]

    # Convenience aliases for common indices.

    def dji(self, **kwargs: Any) -> IndexSeries:
        return self.get("dji", **kwargs)

    def spx(self, **kwargs: Any) -> IndexSeries:
        return self.get("spx", **kwargs)

    def nasdaq_composite(self, **kwargs: Any) -> IndexSeries:
        return self.get("ixic", **kwargs)

    def nasdaq_100(self, **kwargs: Any) -> IndexSeries:
        return self.get("ndx", **kwargs)

    def vix(self, **kwargs: Any) -> IndexSeries:
        return self.get("vix", **kwargs)

    def russell_2000(self, **kwargs: Any) -> IndexSeries:
        return self.get("rut", **kwargs)


__all__ = ["Indices"]
