"""Alpha Intelligence response models."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class TickerSentiment(BaseModel):
    model_config = ConfigDict(extra="allow")

    ticker: Optional[str] = None
    relevance_score: Optional[float] = None
    ticker_sentiment_score: Optional[float] = None
    ticker_sentiment_label: Optional[str] = None


class SymbolSentiment(BaseModel):
    model_config = ConfigDict(extra="allow")

    topic: Optional[str] = None
    relevance_score: Optional[float] = None


class NewsArticle(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: Optional[str] = None
    url: Optional[str] = None
    time_published: Optional[str] = None
    authors: List[str] = []
    summary: Optional[str] = None
    banner_image: Optional[str] = None
    source: Optional[str] = None
    category_within_source: Optional[str] = None
    source_domain: Optional[str] = None
    topics: List[SymbolSentiment] = []
    overall_sentiment_score: Optional[float] = None
    overall_sentiment_label: Optional[str] = None
    ticker_sentiment: List[TickerSentiment] = []


class NewsSentimentPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    items: Optional[str] = None
    sentiment_score_definition: Optional[str] = None
    relevance_score_definition: Optional[str] = None
    feed: List[NewsArticle] = []


class EarningsTranscriptTurn(BaseModel):
    model_config = ConfigDict(extra="allow")

    speaker: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    sentiment: Optional[float] = None


class EarningsTranscript(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: Optional[str] = None
    quarter: Optional[str] = None
    transcript: List[EarningsTranscriptTurn] = []


class TopMover(BaseModel):
    model_config = ConfigDict(extra="allow")

    ticker: Optional[str] = None
    price: Optional[str] = None
    change_amount: Optional[str] = None
    change_percentage: Optional[str] = None
    volume: Optional[str] = None


class TopGainersLosersPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    metadata: Optional[str] = None
    last_updated: Optional[str] = None
    top_gainers: List[TopMover] = []
    top_losers: List[TopMover] = []
    most_actively_traded: List[TopMover] = []


class InsiderTransaction(BaseModel):
    model_config = ConfigDict(extra="allow")

    transaction_date: Optional[str] = None
    ticker: Optional[str] = None
    executive: Optional[str] = None
    executive_title: Optional[str] = None
    security_type: Optional[str] = None
    acquisition_or_disposal: Optional[str] = None
    shares: Optional[str] = None
    share_price: Optional[str] = None


class InstitutionalHolding(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: Optional[str] = None
    holder: Optional[str] = None
    shares: Optional[str] = None
    date_reported: Optional[str] = None
    percent_out: Optional[str] = None
    value: Optional[str] = None


class AnalyticsFixedWindow(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbols: List[str] = []
    range: Optional[str] = None
    ohlc: Optional[str] = None
    interval: Optional[str] = None
    calculations: Dict[str, Any] = {}


class AnalyticsSlidingWindow(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbols: List[str] = []
    range: Optional[str] = None
    ohlc: Optional[str] = None
    interval: Optional[str] = None
    window_size: Optional[int] = None
    calculations: Dict[str, Any] = {}


__all__ = [
    "AnalyticsFixedWindow",
    "AnalyticsSlidingWindow",
    "EarningsTranscript",
    "EarningsTranscriptTurn",
    "InsiderTransaction",
    "InstitutionalHolding",
    "NewsArticle",
    "NewsSentimentPayload",
    "SymbolSentiment",
    "TickerSentiment",
    "TopGainersLosersPayload",
    "TopMover",
]
