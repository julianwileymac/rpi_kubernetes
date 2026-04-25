"""Pydantic v2 response models for Alpha Vantage endpoints.

Each endpoint module returns one of these models (or a list of them) unless the
caller explicitly passes ``output_format='raw'``. Models are deliberately tolerant
of AV's occasional rename/renumber churn by allowing extra fields and coercing
numeric strings to floats.
"""

from .common import AVMetadata, AVResponse, ResponseStatus
from .commodities import CommodityPoint, CommoditySeries
from .crypto import CryptoBar, CryptoIntradaySeries, CryptoQuote, CryptoSeries
from .economics import EconIndicatorPoint, EconIndicatorSeries
from .forex import FxBar, FxIntradaySeries, FxRate, FxSeries
from .fundamentals import (
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
from .indices import IndexCatalogEntry, IndexSeries
from .intelligence import (
    AnalyticsFixedWindow,
    AnalyticsSlidingWindow,
    EarningsTranscriptTurn,
    EarningsTranscript,
    InsiderTransaction,
    InstitutionalHolding,
    NewsArticle,
    NewsSentimentPayload,
    TopMover,
    TopGainersLosersPayload,
    SymbolSentiment,
    TickerSentiment,
)
from .options import OptionContract, OptionChain, OptionsRatioPoint
from .quotes import GlobalQuote, MarketStatusEntry, MarketStatusPayload, SymbolSearchMatch
from .technicals import IndicatorPoint, IndicatorSeries
from .timeseries import OhlcvBar, TimeSeriesPayload


__all__ = [
    "AnalyticsFixedWindow",
    "AnalyticsSlidingWindow",
    "AVMetadata",
    "AVResponse",
    "BalanceSheetReport",
    "CashFlowReport",
    "CommodityPoint",
    "CommoditySeries",
    "CompanyOverview",
    "CryptoBar",
    "CryptoIntradaySeries",
    "CryptoQuote",
    "CryptoSeries",
    "Dividend",
    "EarningsCalendarEntry",
    "EarningsEstimate",
    "EarningsReport",
    "EarningsTranscript",
    "EarningsTranscriptTurn",
    "EconIndicatorPoint",
    "EconIndicatorSeries",
    "EtfProfile",
    "FundamentalsEarnings",
    "FxBar",
    "FxIntradaySeries",
    "FxRate",
    "FxSeries",
    "GlobalQuote",
    "IncomeStatementReport",
    "IndexCatalogEntry",
    "IndexSeries",
    "IndicatorPoint",
    "IndicatorSeries",
    "InsiderTransaction",
    "InstitutionalHolding",
    "IpoCalendarEntry",
    "ListingStatusEntry",
    "MarketStatusEntry",
    "MarketStatusPayload",
    "NewsArticle",
    "NewsSentimentPayload",
    "OhlcvBar",
    "OptionChain",
    "OptionContract",
    "OptionsRatioPoint",
    "ResponseStatus",
    "SharesOutstandingPoint",
    "Split",
    "SymbolSearchMatch",
    "SymbolSentiment",
    "TickerSentiment",
    "TimeSeriesPayload",
    "TopGainersLosersPayload",
    "TopMover",
]
