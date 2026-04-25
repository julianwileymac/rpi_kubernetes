"""Technical indicator endpoints.

Provides a uniform ``get(name, symbol, ...)`` accessor for all 52 Alpha Vantage
indicators as well as dedicated helpers for the most frequently used ones. Each
indicator call returns an :class:`~..models.technicals.IndicatorSeries`.
"""

from __future__ import annotations

from typing import Any, List, Optional

from .._types import Interval, MaType, SeriesType
from ..models.technicals import IndicatorPoint, IndicatorSeries
from ._base import BaseEndpoint


SUPPORTED_INDICATORS: tuple[str, ...] = (
    "SMA", "EMA", "WMA", "DEMA", "TEMA", "TRIMA", "KAMA", "MAMA", "VWAP", "T3",
    "MACD", "MACDEXT", "STOCH", "STOCHF", "RSI", "STOCHRSI", "WILLR", "ADX", "ADXR",
    "APO", "PPO", "MOM", "BOP", "CCI", "CMO", "ROC", "ROCR", "AROON", "AROONOSC",
    "MFI", "TRIX", "ULTOSC", "DX", "MINUS_DI", "PLUS_DI", "MINUS_DM", "PLUS_DM",
    "BBANDS", "MIDPOINT", "MIDPRICE", "SAR", "TRANGE", "ATR", "NATR", "AD", "ADOSC",
    "OBV", "HT_TRENDLINE", "HT_SINE", "HT_TRENDMODE", "HT_DCPERIOD", "HT_DCPHASE",
    "HT_PHASOR",
)


def _value(v: Any) -> str:
    if hasattr(v, "value"):
        return str(v.value)
    return str(v)


def _series_key(payload: dict) -> Optional[str]:
    for key in payload.keys():
        if key.startswith("Technical Analysis"):
            return key
    return None


def _parse_points(payload: dict) -> List[IndicatorPoint]:
    key = _series_key(payload)
    if not key:
        return []
    series = payload.get(key) or {}
    points: List[IndicatorPoint] = []
    if not isinstance(series, dict):
        return points
    for timestamp, values in series.items():
        if not isinstance(values, dict):
            continue
        converted = {k: _try_float(v) for k, v in values.items()}
        points.append(IndicatorPoint(timestamp=timestamp, values=converted))
    return points


def _try_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


class Technicals(BaseEndpoint):
    """All 52 AV technical indicators via a single ``get``/``aget`` entrypoint."""

    @staticmethod
    def supported() -> tuple[str, ...]:
        return SUPPORTED_INDICATORS

    def _build_params(
        self,
        name: str,
        symbol: str,
        *,
        interval: Interval | str = Interval.DAILY,
        time_period: Optional[int] = None,
        series_type: Optional[SeriesType | str] = None,
        month: Optional[str] = None,
        entitlement: Optional[str] = None,
        extras: Optional[dict] = None,
    ) -> dict:
        name_up = name.upper()
        if name_up not in SUPPORTED_INDICATORS:
            raise ValueError(f"Unsupported indicator {name!r}")
        params: dict[str, Any] = {
            "function": name_up,
            "symbol": symbol,
            "interval": _value(interval),
        }
        if time_period is not None:
            params["time_period"] = str(int(time_period))
        if series_type is not None:
            params["series_type"] = _value(series_type)
        if month:
            params["month"] = month
        if entitlement:
            params["entitlement"] = entitlement
        if extras:
            for k, v in extras.items():
                if v is None:
                    continue
                if isinstance(v, MaType):
                    params[k] = str(int(v.value))
                elif hasattr(v, "value"):
                    params[k] = str(v.value)
                else:
                    params[k] = str(v)
        return params

    def get(
        self,
        name: str,
        symbol: str,
        *,
        interval: Interval | str = Interval.DAILY,
        time_period: Optional[int] = 20,
        series_type: Optional[SeriesType | str] = SeriesType.CLOSE,
        month: Optional[str] = None,
        entitlement: Optional[str] = None,
        **extras: Any,
    ) -> IndicatorSeries:
        params = self._build_params(
            name,
            symbol,
            interval=interval,
            time_period=time_period,
            series_type=series_type,
            month=month,
            entitlement=entitlement,
            extras=extras,
        )
        payload = self._sync_request(params)
        return IndicatorSeries(
            function=params["function"],
            symbol=symbol,
            interval=params.get("interval"),
            time_period=int(params["time_period"]) if params.get("time_period") else None,
            series_type=params.get("series_type"),
            indicator_name=name.upper(),
            points=_parse_points(payload),
            metadata=payload.get("Meta Data") or {},
        )

    async def aget(
        self,
        name: str,
        symbol: str,
        *,
        interval: Interval | str = Interval.DAILY,
        time_period: Optional[int] = 20,
        series_type: Optional[SeriesType | str] = SeriesType.CLOSE,
        month: Optional[str] = None,
        entitlement: Optional[str] = None,
        **extras: Any,
    ) -> IndicatorSeries:
        params = self._build_params(
            name,
            symbol,
            interval=interval,
            time_period=time_period,
            series_type=series_type,
            month=month,
            entitlement=entitlement,
            extras=extras,
        )
        payload = await self._async_request(params)
        return IndicatorSeries(
            function=params["function"],
            symbol=symbol,
            interval=params.get("interval"),
            time_period=int(params["time_period"]) if params.get("time_period") else None,
            series_type=params.get("series_type"),
            indicator_name=name.upper(),
            points=_parse_points(payload),
            metadata=payload.get("Meta Data") or {},
        )

    # Convenience aliases for the most frequently used indicators.

    def sma(self, symbol: str, **kwargs: Any) -> IndicatorSeries:
        return self.get("SMA", symbol, **kwargs)

    def ema(self, symbol: str, **kwargs: Any) -> IndicatorSeries:
        return self.get("EMA", symbol, **kwargs)

    def rsi(self, symbol: str, *, time_period: int = 14, **kwargs: Any) -> IndicatorSeries:
        return self.get("RSI", symbol, time_period=time_period, **kwargs)

    def macd(self, symbol: str, **kwargs: Any) -> IndicatorSeries:
        return self.get("MACD", symbol, time_period=None, series_type=SeriesType.CLOSE, **kwargs)

    def bbands(self, symbol: str, *, time_period: int = 20, **kwargs: Any) -> IndicatorSeries:
        return self.get("BBANDS", symbol, time_period=time_period, **kwargs)

    def adx(self, symbol: str, *, time_period: int = 14, **kwargs: Any) -> IndicatorSeries:
        return self.get("ADX", symbol, time_period=time_period, series_type=None, **kwargs)

    def vwap(self, symbol: str, **kwargs: Any) -> IndicatorSeries:
        return self.get("VWAP", symbol, time_period=None, series_type=None, **kwargs)

    def obv(self, symbol: str, **kwargs: Any) -> IndicatorSeries:
        return self.get("OBV", symbol, time_period=None, series_type=None, **kwargs)


__all__ = ["SUPPORTED_INDICATORS", "Technicals"]
