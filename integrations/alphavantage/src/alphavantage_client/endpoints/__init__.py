"""Endpoint groups exposed by :class:`~alphavantage_client.client.AlphaVantageClient`."""

from .commodities import Commodities
from .crypto import Crypto
from .economics import Economics
from .forex import Forex
from .fundamentals import Fundamentals
from .indices import Indices
from .intelligence import Intelligence
from .options import Options
from .technicals import Technicals
from .timeseries import TimeSeries


__all__ = [
    "Commodities",
    "Crypto",
    "Economics",
    "Forex",
    "Fundamentals",
    "Indices",
    "Intelligence",
    "Options",
    "Technicals",
    "TimeSeries",
]
