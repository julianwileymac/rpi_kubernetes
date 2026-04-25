"""Fundamental data models."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CompanyOverview(BaseModel):
    """OVERVIEW endpoint response."""

    model_config = ConfigDict(extra="allow")

    symbol: Optional[str] = Field(default=None, alias="Symbol")
    asset_type: Optional[str] = Field(default=None, alias="AssetType")
    name: Optional[str] = Field(default=None, alias="Name")
    description: Optional[str] = Field(default=None, alias="Description")
    cik: Optional[str] = Field(default=None, alias="CIK")
    exchange: Optional[str] = Field(default=None, alias="Exchange")
    currency: Optional[str] = Field(default=None, alias="Currency")
    country: Optional[str] = Field(default=None, alias="Country")
    sector: Optional[str] = Field(default=None, alias="Sector")
    industry: Optional[str] = Field(default=None, alias="Industry")
    address: Optional[str] = Field(default=None, alias="Address")
    fiscal_year_end: Optional[str] = Field(default=None, alias="FiscalYearEnd")
    latest_quarter: Optional[str] = Field(default=None, alias="LatestQuarter")
    market_capitalization: Optional[str] = Field(default=None, alias="MarketCapitalization")
    ebitda: Optional[str] = Field(default=None, alias="EBITDA")
    pe_ratio: Optional[str] = Field(default=None, alias="PERatio")
    peg_ratio: Optional[str] = Field(default=None, alias="PEGRatio")
    book_value: Optional[str] = Field(default=None, alias="BookValue")
    dividend_per_share: Optional[str] = Field(default=None, alias="DividendPerShare")
    dividend_yield: Optional[str] = Field(default=None, alias="DividendYield")
    eps: Optional[str] = Field(default=None, alias="EPS")
    revenue_per_share_ttm: Optional[str] = Field(default=None, alias="RevenuePerShareTTM")
    profit_margin: Optional[str] = Field(default=None, alias="ProfitMargin")
    operating_margin_ttm: Optional[str] = Field(default=None, alias="OperatingMarginTTM")
    return_on_assets_ttm: Optional[str] = Field(default=None, alias="ReturnOnAssetsTTM")
    return_on_equity_ttm: Optional[str] = Field(default=None, alias="ReturnOnEquityTTM")
    revenue_ttm: Optional[str] = Field(default=None, alias="RevenueTTM")
    gross_profit_ttm: Optional[str] = Field(default=None, alias="GrossProfitTTM")
    diluted_eps_ttm: Optional[str] = Field(default=None, alias="DilutedEPSTTM")
    quarterly_earnings_growth_yoy: Optional[str] = Field(
        default=None, alias="QuarterlyEarningsGrowthYOY"
    )
    quarterly_revenue_growth_yoy: Optional[str] = Field(
        default=None, alias="QuarterlyRevenueGrowthYOY"
    )
    analyst_target_price: Optional[str] = Field(default=None, alias="AnalystTargetPrice")
    trailing_pe: Optional[str] = Field(default=None, alias="TrailingPE")
    forward_pe: Optional[str] = Field(default=None, alias="ForwardPE")
    price_to_sales_ratio_ttm: Optional[str] = Field(
        default=None, alias="PriceToSalesRatioTTM"
    )
    price_to_book_ratio: Optional[str] = Field(default=None, alias="PriceToBookRatio")
    ev_to_revenue: Optional[str] = Field(default=None, alias="EVToRevenue")
    ev_to_ebitda: Optional[str] = Field(default=None, alias="EVToEBITDA")
    beta: Optional[str] = Field(default=None, alias="Beta")
    fifty_two_week_high: Optional[str] = Field(default=None, alias="52WeekHigh")
    fifty_two_week_low: Optional[str] = Field(default=None, alias="52WeekLow")
    fifty_day_moving_average: Optional[str] = Field(default=None, alias="50DayMovingAverage")
    two_hundred_day_moving_average: Optional[str] = Field(
        default=None, alias="200DayMovingAverage"
    )
    shares_outstanding: Optional[str] = Field(default=None, alias="SharesOutstanding")
    dividend_date: Optional[str] = Field(default=None, alias="DividendDate")
    ex_dividend_date: Optional[str] = Field(default=None, alias="ExDividendDate")


class EtfProfile(BaseModel):
    model_config = ConfigDict(extra="allow")

    net_assets: Optional[str] = None
    net_expense_ratio: Optional[str] = None
    portfolio_turnover: Optional[str] = None
    dividend_yield: Optional[str] = None
    inception_date: Optional[str] = None
    leveraged: Optional[str] = None
    sectors: List[dict] = []
    holdings: List[dict] = []


class Dividend(BaseModel):
    model_config = ConfigDict(extra="allow")

    ex_dividend_date: Optional[str] = None
    declaration_date: Optional[str] = None
    record_date: Optional[str] = None
    payment_date: Optional[str] = None
    amount: Optional[float] = None


class Split(BaseModel):
    model_config = ConfigDict(extra="allow")

    effective_date: Optional[str] = None
    split_factor: Optional[str] = None


class IncomeStatementReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    fiscal_date_ending: Optional[str] = Field(default=None, alias="fiscalDateEnding")
    reported_currency: Optional[str] = Field(default=None, alias="reportedCurrency")
    gross_profit: Optional[str] = Field(default=None, alias="grossProfit")
    total_revenue: Optional[str] = Field(default=None, alias="totalRevenue")
    cost_of_revenue: Optional[str] = Field(default=None, alias="costOfRevenue")
    operating_income: Optional[str] = Field(default=None, alias="operatingIncome")
    net_income: Optional[str] = Field(default=None, alias="netIncome")
    ebitda: Optional[str] = None


class BalanceSheetReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    fiscal_date_ending: Optional[str] = Field(default=None, alias="fiscalDateEnding")
    reported_currency: Optional[str] = Field(default=None, alias="reportedCurrency")
    total_assets: Optional[str] = Field(default=None, alias="totalAssets")
    total_current_assets: Optional[str] = Field(default=None, alias="totalCurrentAssets")
    total_liabilities: Optional[str] = Field(default=None, alias="totalLiabilities")
    total_current_liabilities: Optional[str] = Field(
        default=None, alias="totalCurrentLiabilities"
    )
    total_shareholder_equity: Optional[str] = Field(
        default=None, alias="totalShareholderEquity"
    )


class CashFlowReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    fiscal_date_ending: Optional[str] = Field(default=None, alias="fiscalDateEnding")
    reported_currency: Optional[str] = Field(default=None, alias="reportedCurrency")
    operating_cashflow: Optional[str] = Field(default=None, alias="operatingCashflow")
    cashflow_from_investment: Optional[str] = Field(
        default=None, alias="cashflowFromInvestment"
    )
    cashflow_from_financing: Optional[str] = Field(
        default=None, alias="cashflowFromFinancing"
    )
    capital_expenditures: Optional[str] = Field(default=None, alias="capitalExpenditures")
    net_income: Optional[str] = Field(default=None, alias="netIncome")


class EarningsReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    fiscal_date_ending: Optional[str] = Field(default=None, alias="fiscalDateEnding")
    reported_date: Optional[str] = Field(default=None, alias="reportedDate")
    reported_eps: Optional[str] = Field(default=None, alias="reportedEPS")
    estimated_eps: Optional[str] = Field(default=None, alias="estimatedEPS")
    surprise: Optional[str] = None
    surprise_percentage: Optional[str] = Field(default=None, alias="surprisePercentage")


class EarningsEstimate(BaseModel):
    model_config = ConfigDict(extra="allow")

    date: Optional[str] = None
    horizon: Optional[str] = None
    eps_estimate_average: Optional[str] = Field(default=None, alias="epsEstimateAverage")
    eps_estimate_high: Optional[str] = Field(default=None, alias="epsEstimateHigh")
    eps_estimate_low: Optional[str] = Field(default=None, alias="epsEstimateLow")
    number_of_analysts: Optional[str] = Field(default=None, alias="numberOfAnalysts")


class FundamentalsEarnings(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: Optional[str] = None
    annual_earnings: List[EarningsReport] = []
    quarterly_earnings: List[EarningsReport] = []


class EarningsCalendarEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: Optional[str] = None
    name: Optional[str] = None
    report_date: Optional[str] = Field(default=None, alias="reportDate")
    fiscal_date_ending: Optional[str] = Field(default=None, alias="fiscalDateEnding")
    estimate: Optional[str] = None
    currency: Optional[str] = None


class IpoCalendarEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: Optional[str] = None
    name: Optional[str] = None
    ipo_date: Optional[str] = Field(default=None, alias="ipoDate")
    price_range_low: Optional[str] = Field(default=None, alias="priceRangeLow")
    price_range_high: Optional[str] = Field(default=None, alias="priceRangeHigh")
    currency: Optional[str] = None
    exchange: Optional[str] = None


class ListingStatusEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: Optional[str] = None
    name: Optional[str] = None
    exchange: Optional[str] = None
    asset_type: Optional[str] = Field(default=None, alias="assetType")
    ipo_date: Optional[str] = Field(default=None, alias="ipoDate")
    delisting_date: Optional[str] = Field(default=None, alias="delistingDate")
    status: Optional[str] = None


class SharesOutstandingPoint(BaseModel):
    model_config = ConfigDict(extra="allow")

    date: Optional[str] = None
    shares_outstanding: Optional[float] = None


__all__ = [
    "BalanceSheetReport",
    "CashFlowReport",
    "CompanyOverview",
    "Dividend",
    "EarningsCalendarEntry",
    "EarningsEstimate",
    "EarningsReport",
    "EtfProfile",
    "FundamentalsEarnings",
    "IncomeStatementReport",
    "IpoCalendarEntry",
    "ListingStatusEntry",
    "SharesOutstandingPoint",
    "Split",
]
