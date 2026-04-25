"""Polygon.io REST poller producer.

Uses the Polygon REST API to poll last-trade/last-quote/aggregate endpoints
and produce Avro-encoded records to the trading-kafka cluster. Requires
``POLYGON_API_KEY`` in the environment.

Run with:
    POLYGON_API_KEY=... python polygon_producer.py --symbols AAPL,MSFT
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List

import httpx
from prometheus_client import start_http_server

from common import AvroCodec, KafkaSettings, build_producer, configure_tracing, produce_with_tracing

logger = logging.getLogger(__name__)

SCHEMAS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "flink-jobs" / "jobs" / "schemas"
POLYGON_BASE = "https://api.polygon.io"


def _load_schema(name: str) -> Dict:
    with (SCHEMAS_DIR / f"{name}.avsc").open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--symbols", type=str, default="AAPL,MSFT,SPY,TSLA",
        help="Comma-separated Polygon tickers (without exchange suffix)",
    )
    parser.add_argument(
        "--exchange", type=str, default="NASDAQ", help="Default exchange suffix for vt_symbol",
    )
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--trade-topic", type=str, default="market.trade.v1")
    parser.add_argument("--bar-topic", type=str, default="market.bar.v1")
    parser.add_argument("--metrics-port", type=int, default=9311)
    return parser.parse_args()


def _last_trade(client: httpx.Client, ticker: str, api_key: str) -> Dict | None:
    res = client.get(f"{POLYGON_BASE}/v2/last/trade/{ticker}", params={"apiKey": api_key}, timeout=10.0)
    if res.status_code >= 400:
        logger.warning("polygon last/trade %s failed: %s", ticker, res.text)
        return None
    body = res.json().get("results")
    return body


def _last_bar(client: httpx.Client, ticker: str, api_key: str) -> Dict | None:
    res = client.get(
        f"{POLYGON_BASE}/v2/aggs/ticker/{ticker}/prev",
        params={"adjusted": "true", "apiKey": api_key},
        timeout=10.0,
    )
    if res.status_code >= 400:
        logger.warning("polygon aggs/prev %s failed: %s", ticker, res.text)
        return None
    hits = res.json().get("results") or []
    return hits[0] if hits else None


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = _args()
    api_key = os.environ.get("POLYGON_API_KEY")
    if not api_key:
        raise SystemExit("POLYGON_API_KEY env var is required")

    settings = KafkaSettings()
    tracer = configure_tracing("polygon-producer", settings.otel_endpoint)
    start_http_server(args.metrics_port)
    codec = AvroCodec(settings.schema_registry_url, settings.schema_group, auto_register=True)
    codec.register("market_trade_v1", _load_schema("market_trade_v1"))
    codec.register("market_bar_v1", _load_schema("market_bar_v1"))
    producer = build_producer(settings, client_id="polygon-producer")
    client = httpx.Client()

    symbols: List[str] = [s.strip() for s in args.symbols.split(",") if s.strip()]
    logger.info("polling polygon symbols=%s interval=%ss", symbols, args.poll_interval)
    try:
        while True:
            for ticker in symbols:
                vt = f"{ticker}.{args.exchange}"
                now = time.time_ns()

                trade = _last_trade(client, ticker, api_key)
                if trade:
                    produce_with_tracing(
                        producer,
                        codec,
                        producer_name="polygon",
                        schema_name="market_trade_v1",
                        topic=args.trade_topic,
                        record={
                            "ts_ns": int(trade.get("t", now / 1e6)) * 1_000_000 if trade.get("t") else now,
                            "vt_symbol": vt,
                            "price": float(trade.get("p", 0.0)),
                            "size": int(trade.get("s", 0)),
                            "exchange": args.exchange,
                            "conditions": list(trade.get("c", [])) or [],
                            "received_ts_ns": now,
                        },
                        key=vt,
                        tracer=tracer,
                    )

                bar = _last_bar(client, ticker, api_key)
                if bar:
                    produce_with_tracing(
                        producer,
                        codec,
                        producer_name="polygon",
                        schema_name="market_bar_v1",
                        topic=args.bar_topic,
                        record={
                            "ts_ns": int(bar.get("t", now / 1e6)) * 1_000_000 if bar.get("t") else now,
                            "vt_symbol": vt,
                            "open": float(bar.get("o", 0.0)),
                            "high": float(bar.get("h", 0.0)),
                            "low": float(bar.get("l", 0.0)),
                            "close": float(bar.get("c", 0.0)),
                            "volume": float(bar.get("v", 0.0)),
                            "trade_count": int(bar.get("n", 0)),
                            "vwap": float(bar.get("vw", 0.0)),
                            "exchange": args.exchange,
                            "received_ts_ns": now,
                        },
                        key=vt,
                        tracer=tracer,
                    )
            time.sleep(args.poll_interval)
    except KeyboardInterrupt:
        logger.info("interrupted, flushing")
    finally:
        producer.flush(15)
        codec.close()
        client.close()


if __name__ == "__main__":
    main()
