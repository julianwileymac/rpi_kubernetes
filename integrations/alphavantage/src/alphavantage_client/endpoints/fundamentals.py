"""Fundamental data endpoints."""

from __future__ import annotations

from typing import Any, List, Optional

from ..models.fundamentals import (
    BalanceSheetReport,
    CashFlowReport,
    CompanyOverview,
    Dividend,
    EarningsCalendarEntry,
    EarningsEstimate,
    EarningsReport,
    EtfProfile,
    FundamentalsEarnings,
    IncomeStatementReport,
    IpoCalendarEntry,
    ListingStatusEntry,
    SharesOutstandingPoint,
    Split,
)
from ._base import BaseEndpoint


class Fundamentals(BaseEndpoint):
    """Company overview, statements, earnings, dividends/splits, calendars, universe."""

    # Company overview / ETF profile

    def overview(self, symbol: str) -> CompanyOverview:
        payload = self._sync_request({"function": "OVERVIEW", "symbol": symbol})
        return CompanyOverview.model_validate(payload)

    async def aoverview(self, symbol: str) -> CompanyOverview:
        payload = await self._async_request({"function": "OVERVIEW", "symbol": symbol})
        return CompanyOverview.model_validate(payload)

    def etf_profile(self, symbol: str) -> EtfProfile:
        payload = self._sync_request({"function": "ETF_PROFILE", "symbol": symbol})
        return EtfProfile.model_validate(payload)

    async def aetf_profile(self, symbol: str) -> EtfProfile:
        payload = await self._async_request({"function": "ETF_PROFILE", "symbol": symbol})
        return EtfProfile.model_validate(payload)

    # Corporate actions

    def dividends(self, symbol: str) -> List[Dividend]:
        payload = self._sync_request({"function": "DIVIDENDS", "symbol": symbol})
        return [Dividend.model_validate(d) for d in payload.get("data", [])]

    async def adividends(self, symbol: str) -> List[Dividend]:
        payload = await self._async_request({"function": "DIVIDENDS", "symbol": symbol})
        return [Dividend.model_validate(d) for d in payload.get("data", [])]

    def splits(self, symbol: str) -> List[Split]:
        payload = self._sync_request({"function": "SPLITS", "symbol": symbol})
        return [Split.model_validate(s) for s in payload.get("data", [])]

    async def asplits(self, symbol: str) -> List[Split]:
        payload = await self._async_request({"function": "SPLITS", "symbol": symbol})
        return [Split.model_validate(s) for s in payload.get("data", [])]

    # Statements

    def income_statement(self, symbol: str) -> dict:
        payload = self._sync_request({"function": "INCOME_STATEMENT", "symbol": symbol})
        return {
            "symbol": payload.get("symbol"),
            "annual": [IncomeStatementReport.model_validate(r)
                       for r in payload.get("annualReports", [])],
            "quarterly": [IncomeStatementReport.model_validate(r)
                          for r in payload.get("quarterlyReports", [])],
        }

    async def aincome_statement(self, symbol: str) -> dict:
        payload = await self._async_request({"function": "INCOME_STATEMENT", "symbol": symbol})
        return {
            "symbol": payload.get("symbol"),
            "annual": [IncomeStatementReport.model_validate(r)
                       for r in payload.get("annualReports", [])],
            "quarterly": [IncomeStatementReport.model_validate(r)
                          for r in payload.get("quarterlyReports", [])],
        }

    def balance_sheet(self, symbol: str) -> dict:
        payload = self._sync_request({"function": "BALANCE_SHEET", "symbol": symbol})
        return {
            "symbol": payload.get("symbol"),
            "annual": [BalanceSheetReport.model_validate(r)
                       for r in payload.get("annualReports", [])],
            "quarterly": [BalanceSheetReport.model_validate(r)
                          for r in payload.get("quarterlyReports", [])],
        }

    async def abalance_sheet(self, symbol: str) -> dict:
        payload = await self._async_request({"function": "BALANCE_SHEET", "symbol": symbol})
        return {
            "symbol": payload.get("symbol"),
            "annual": [BalanceSheetReport.model_validate(r)
                       for r in payload.get("annualReports", [])],
            "quarterly": [BalanceSheetReport.model_validate(r)
                          for r in payload.get("quarterlyReports", [])],
        }

    def cash_flow(self, symbol: str) -> dict:
        payload = self._sync_request({"function": "CASH_FLOW", "symbol": symbol})
        return {
            "symbol": payload.get("symbol"),
            "annual": [CashFlowReport.model_validate(r)
                       for r in payload.get("annualReports", [])],
            "quarterly": [CashFlowReport.model_validate(r)
                          for r in payload.get("quarterlyReports", [])],
        }

    async def acash_flow(self, symbol: str) -> dict:
        payload = await self._async_request({"function": "CASH_FLOW", "symbol": symbol})
        return {
            "symbol": payload.get("symbol"),
            "annual": [CashFlowReport.model_validate(r)
                       for r in payload.get("annualReports", [])],
            "quarterly": [CashFlowReport.model_validate(r)
                          for r in payload.get("quarterlyReports", [])],
        }

    # Earnings

    def earnings(self, symbol: str) -> FundamentalsEarnings:
        payload = self._sync_request({"function": "EARNINGS", "symbol": symbol})
        return FundamentalsEarnings(
            symbol=payload.get("symbol"),
            annual_earnings=[EarningsReport.model_validate(r)
                             for r in payload.get("annualEarnings", [])],
            quarterly_earnings=[EarningsReport.model_validate(r)
                                for r in payload.get("quarterlyEarnings", [])],
        )

    async def aearnings(self, symbol: str) -> FundamentalsEarnings:
        payload = await self._async_request({"function": "EARNINGS", "symbol": symbol})
        return FundamentalsEarnings(
            symbol=payload.get("symbol"),
            annual_earnings=[EarningsReport.model_validate(r)
                             for r in payload.get("annualEarnings", [])],
            quarterly_earnings=[EarningsReport.model_validate(r)
                                for r in payload.get("quarterlyEarnings", [])],
        )

    def earnings_estimates(self, symbol: str) -> List[EarningsEstimate]:
        payload = self._sync_request({"function": "EARNINGS_ESTIMATES", "symbol": symbol})
        rows = payload.get("estimates") or payload.get("data") or []
        return [EarningsEstimate.model_validate(r) for r in rows]

    async def aearnings_estimates(self, symbol: str) -> List[EarningsEstimate]:
        payload = await self._async_request(
            {"function": "EARNINGS_ESTIMATES", "symbol": symbol},
        )
        rows = payload.get("estimates") or payload.get("data") or []
        return [EarningsEstimate.model_validate(r) for r in rows]

    def shares_outstanding(self, symbol: str) -> List[SharesOutstandingPoint]:
        payload = self._sync_request({"function": "SHARES_OUTSTANDING", "symbol": symbol})
        rows = payload.get("data") or []
        return [SharesOutstandingPoint.model_validate(r) for r in rows]

    async def ashares_outstanding(self, symbol: str) -> List[SharesOutstandingPoint]:
        payload = await self._async_request(
            {"function": "SHARES_OUTSTANDING", "symbol": symbol},
        )
        rows = payload.get("data") or []
        return [SharesOutstandingPoint.model_validate(r) for r in rows]

    # Calendars & universe

    def earnings_calendar(
        self,
        *,
        symbol: Optional[str] = None,
        horizon: Optional[str] = None,
    ) -> str:
        params: dict[str, Any] = {"function": "EARNINGS_CALENDAR"}
        if symbol:
            params["symbol"] = symbol
        if horizon:
            params["horizon"] = horizon
        payload = self._sync_request(params, datatype="csv")
        return str(payload)

    async def aearnings_calendar(
        self,
        *,
        symbol: Optional[str] = None,
        horizon: Optional[str] = None,
    ) -> str:
        params: dict[str, Any] = {"function": "EARNINGS_CALENDAR"}
        if symbol:
            params["symbol"] = symbol
        if horizon:
            params["horizon"] = horizon
        payload = await self._async_request(params, datatype="csv")
        return str(payload)

    def ipo_calendar(self) -> str:
        payload = self._sync_request({"function": "IPO_CALENDAR"}, datatype="csv")
        return str(payload)

    async def aipo_calendar(self) -> str:
        payload = await self._async_request({"function": "IPO_CALENDAR"}, datatype="csv")
        return str(payload)

    def listing_status(
        self,
        *,
        date: Optional[str] = None,
        state: Optional[str] = None,
    ) -> str:
        params: dict[str, Any] = {"function": "LISTING_STATUS"}
        if date:
            params["date"] = date
        if state:
            params["state"] = state
        payload = self._sync_request(params, datatype="csv")
        return str(payload)

    async def alisting_status(
        self,
        *,
        date: Optional[str] = None,
        state: Optional[str] = None,
    ) -> str:
        params: dict[str, Any] = {"function": "LISTING_STATUS"}
        if date:
            params["date"] = date
        if state:
            params["state"] = state
        payload = await self._async_request(params, datatype="csv")
        return str(payload)


__all__ = ["Fundamentals"]
