"""Alpaca IEX streaming producer.

Connects to Alpaca Markets' IEX websocket feed and publishes:
    - ``market.trade.v1`` for each trade tick
    - ``market.quote.v1`` for NBBO updates

Requires ``ALPACA_API_KEY`` + ``ALPACA_SECRET_KEY`` in the environment and
``pip install '.[alpaca]'``. Mirrors the shape of aqp's AlpacaIngester so
both can be maintained side-by-side.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List

from prometheus_client import start_http_server

from common import AvroCodec, KafkaSettings, build_producer, configure_tracing, produce_with_tracing

logger = logging.getLogger(__name__)
SCHEMAS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "flink-jobs" / "jobs" / "schemas"


def _load_schema(name: str) -> Dict:
    with (SCHEMAS_DIR / f"{name}.avsc").open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", type=str, default="AAPL,MSFT,SPY,TSLA")
    parser.add_argument("--exchange", type=str, default="NASDAQ")
    parser.add_argument("--feed", type=str, default="iex", choices=["iex", "sip"])
    parser.add_argument("--trade-topic", type=str, default="market.trade.v1")
    parser.add_argument("--quote-topic", type=str, default="market.quote.v1")
    parser.add_argument("--metrics-port", type=int, default=9313)
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    try:
        from alpaca.data.live import StockDataStream  # type: ignore[import]
    except ImportError:
        raise SystemExit("install with: pip install '.[alpaca]'")

    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        raise SystemExit("ALPACA_API_KEY and ALPACA_SECRET_KEY env vars are required")

    settings = KafkaSettings()
    tracer = configure_tracing("alpaca-producer", settings.otel_endpoint)
    start_http_server(args.metrics_port)

    codec = AvroCodec(settings.schema_registry_url, settings.schema_group, auto_register=True)
    codec.register("market_trade_v1", _load_schema("market_trade_v1"))
    codec.register("market_quote_v1", _load_schema("market_quote_v1"))
    producer = build_producer(settings, client_id="alpaca-producer")

    symbols: List[str] = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    stream = StockDataStream(api_key=api_key, secret_key=secret_key, feed=args.feed)

    async def handle_trade(trade):  # Alpaca SDK dataclass
        vt = f"{trade.symbol}.{args.exchange}"
        now = time.time_ns()
        produce_with_tracing(
            producer,
            codec,
            producer_name="alpaca",
            schema_name="market_trade_v1",
            topic=args.trade_topic,
            record={
                "ts_ns": int(trade.timestamp.timestamp() * 1_000_000_000),
                "vt_symbol": vt,
                "price": float(trade.price),
                "size": int(trade.size),
                "exchange": args.exchange,
                "conditions": list(trade.conditions or []),
                "received_ts_ns": now,
            },
            key=vt,
            tracer=tracer,
        )

    async def handle_quote(quote):
        vt = f"{quote.symbol}.{args.exchange}"
        now = time.time_ns()
        produce_with_tracing(
            producer,
            codec,
            producer_name="alpaca",
            schema_name="market_quote_v1",
            topic=args.quote_topic,
            record={
                "ts_ns": int(quote.timestamp.timestamp() * 1_000_000_000),
                "vt_symbol": vt,
                "bid_price": float(quote.bid_price),
                "bid_size": int(quote.bid_size),
                "ask_price": float(quote.ask_price),
                "ask_size": int(quote.ask_size),
                "exchange": args.exchange,
                "conditions": list(quote.conditions or []),
                "received_ts_ns": now,
            },
            key=vt,
            tracer=tracer,
        )

    stream.subscribe_trades(handle_trade, *symbols)
    stream.subscribe_quotes(handle_quote, *symbols)
    logger.info("alpaca streaming symbols=%s feed=%s", symbols, args.feed)

    try:
        await stream._run_forever()  # noqa: SLF001  SDK private API
    except KeyboardInterrupt:
        logger.info("interrupted, flushing")
    finally:
        await stream.stop_ws()
        producer.flush(15)
        codec.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = _args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
