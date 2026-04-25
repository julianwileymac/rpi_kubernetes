"""Alpha Intelligence endpoints."""

from __future__ import annotations

from typing import Any, Iterable, List, Optional, Sequence

from .._types import NewsSort, AnalyticsCalculation
from ..models.intelligence import (
    AnalyticsFixedWindow,
    AnalyticsSlidingWindow,
    EarningsTranscript,
    EarningsTranscriptTurn,
    InsiderTransaction,
    InstitutionalHolding,
    NewsSentimentPayload,
    TopGainersLosersPayload,
)
from ._base import BaseEndpoint


def _joined(values: Optional[Sequence[str] | str]) -> Optional[str]:
    if values is None:
        return None
    if isinstance(values, str):
        return values
    return ",".join(values)


class Intelligence(BaseEndpoint):
    """News sentiment, earnings transcripts, top gainers/losers, insider/institutional,
    analytics (fixed & sliding window)."""

    # ------------------------------------------------------------------
    # News sentiment
    # ------------------------------------------------------------------

    def _news_params(
        self,
        *,
        tickers: Optional[Sequence[str] | str] = None,
        topics: Optional[Sequence[str] | str] = None,
        time_from: Optional[str] = None,
        time_to: Optional[str] = None,
        sort: Optional[NewsSort | str] = NewsSort.LATEST,
        limit: Optional[int] = None,
    ) -> dict:
        params: dict[str, Any] = {"function": "NEWS_SENTIMENT"}
        t = _joined(tickers)
        if t:
            params["tickers"] = t
        topics_joined = _joined(topics)
        if topics_joined:
            params["topics"] = topics_joined
        if time_from:
            params["time_from"] = time_from
        if time_to:
            params["time_to"] = time_to
        if sort:
            params["sort"] = sort.value if hasattr(sort, "value") else str(sort)
        if limit is not None:
            params["limit"] = str(int(limit))
        return params

    def news(self, **kwargs: Any) -> NewsSentimentPayload:
        payload = self._sync_request(self._news_params(**kwargs))
        return NewsSentimentPayload.model_validate(payload)

    async def anews(self, **kwargs: Any) -> NewsSentimentPayload:
        payload = await self._async_request(self._news_params(**kwargs))
        return NewsSentimentPayload.model_validate(payload)

    # ------------------------------------------------------------------
    # Earnings transcripts
    # ------------------------------------------------------------------

    def earnings_transcript(self, symbol: str, quarter: str) -> EarningsTranscript:
        payload = self._sync_request(
            {"function": "EARNINGS_CALL_TRANSCRIPT", "symbol": symbol, "quarter": quarter},
        )
        return EarningsTranscript(
            symbol=symbol,
            quarter=quarter,
            transcript=[EarningsTranscriptTurn.model_validate(turn)
                        for turn in (payload.get("transcript") or [])],
        )

    async def aearnings_transcript(self, symbol: str, quarter: str) -> EarningsTranscript:
        payload = await self._async_request(
            {"function": "EARNINGS_CALL_TRANSCRIPT", "symbol": symbol, "quarter": quarter},
        )
        return EarningsTranscript(
            symbol=symbol,
            quarter=quarter,
            transcript=[EarningsTranscriptTurn.model_validate(turn)
                        for turn in (payload.get("transcript") or [])],
        )

    # ------------------------------------------------------------------
    # Top gainers / losers / actively traded
    # ------------------------------------------------------------------

    def top_movers(self, *, entitlement: Optional[str] = None) -> TopGainersLosersPayload:
        params: dict[str, Any] = {"function": "TOP_GAINERS_LOSERS"}
        if entitlement:
            params["entitlement"] = entitlement
        payload = self._sync_request(params)
        return TopGainersLosersPayload.model_validate(payload)

    async def atop_movers(self, *, entitlement: Optional[str] = None) -> TopGainersLosersPayload:
        params: dict[str, Any] = {"function": "TOP_GAINERS_LOSERS"}
        if entitlement:
            params["entitlement"] = entitlement
        payload = await self._async_request(params)
        return TopGainersLosersPayload.model_validate(payload)

    # ------------------------------------------------------------------
    # Insider / Institutional
    # ------------------------------------------------------------------

    def insider(self, symbol: str) -> List[InsiderTransaction]:
        payload = self._sync_request(
            {"function": "INSIDER_TRANSACTIONS", "symbol": symbol},
        )
        rows = payload.get("data") or []
        return [InsiderTransaction.model_validate(r) for r in rows]

    async def ainsider(self, symbol: str) -> List[InsiderTransaction]:
        payload = await self._async_request(
            {"function": "INSIDER_TRANSACTIONS", "symbol": symbol},
        )
        rows = payload.get("data") or []
        return [InsiderTransaction.model_validate(r) for r in rows]

    def institutional(self, symbol: str) -> List[InstitutionalHolding]:
        payload = self._sync_request(
            {"function": "INSTITUTIONAL_HOLDINGS", "symbol": symbol},
        )
        rows = payload.get("data") or []
        return [InstitutionalHolding.model_validate(r) for r in rows]

    async def ainstitutional(self, symbol: str) -> List[InstitutionalHolding]:
        payload = await self._async_request(
            {"function": "INSTITUTIONAL_HOLDINGS", "symbol": symbol},
        )
        rows = payload.get("data") or []
        return [InstitutionalHolding.model_validate(r) for r in rows]

    # ------------------------------------------------------------------
    # Analytics (fixed / sliding)
    # ------------------------------------------------------------------

    def _analytics_params(
        self,
        *,
        symbols: Sequence[str],
        range_: str,
        interval: str,
        calculations: Iterable[AnalyticsCalculation | str],
        ohlc: str = "close",
        window_size: Optional[int] = None,
    ) -> dict:
        params: dict[str, Any] = {
            "SYMBOLS": ",".join(symbols),
            "RANGE": range_,
            "INTERVAL": interval,
            "OHLC": ohlc,
            "CALCULATIONS": ",".join(
                c.value if hasattr(c, "value") else str(c) for c in calculations
            ),
        }
        if window_size is not None:
            params["WINDOW_SIZE"] = str(int(window_size))
        return params

    def analytics_fixed(self, **kwargs: Any) -> AnalyticsFixedWindow:
        params = self._analytics_params(**kwargs)
        params["function"] = "ANALYTICS_FIXED_WINDOW"
        payload = self._sync_request(params)
        meta = payload.get("meta_data") or {}
        return AnalyticsFixedWindow(
            symbols=list(kwargs.get("symbols", [])),
            range=kwargs.get("range_"),
            ohlc=kwargs.get("ohlc", "close"),
            interval=kwargs.get("interval"),
            calculations=payload.get("payload", {}).get("RETURNS_CALCULATIONS", payload),
        )

    async def aanalytics_fixed(self, **kwargs: Any) -> AnalyticsFixedWindow:
        params = self._analytics_params(**kwargs)
        params["function"] = "ANALYTICS_FIXED_WINDOW"
        payload = await self._async_request(params)
        return AnalyticsFixedWindow(
            symbols=list(kwargs.get("symbols", [])),
            range=kwargs.get("range_"),
            ohlc=kwargs.get("ohlc", "close"),
            interval=kwargs.get("interval"),
            calculations=payload.get("payload", {}).get("RETURNS_CALCULATIONS", payload),
        )

    def analytics_sliding(self, **kwargs: Any) -> AnalyticsSlidingWindow:
        params = self._analytics_params(**kwargs)
        params["function"] = "ANALYTICS_SLIDING_WINDOW"
        payload = self._sync_request(params)
        return AnalyticsSlidingWindow(
            symbols=list(kwargs.get("symbols", [])),
            range=kwargs.get("range_"),
            ohlc=kwargs.get("ohlc", "close"),
            interval=kwargs.get("interval"),
            window_size=kwargs.get("window_size"),
            calculations=payload.get("payload", payload),
        )

    async def aanalytics_sliding(self, **kwargs: Any) -> AnalyticsSlidingWindow:
        params = self._analytics_params(**kwargs)
        params["function"] = "ANALYTICS_SLIDING_WINDOW"
        payload = await self._async_request(params)
        return AnalyticsSlidingWindow(
            symbols=list(kwargs.get("symbols", [])),
            range=kwargs.get("range_"),
            ohlc=kwargs.get("ohlc", "close"),
            interval=kwargs.get("interval"),
            window_size=kwargs.get("window_size"),
            calculations=payload.get("payload", payload),
        )


__all__ = ["Intelligence"]
