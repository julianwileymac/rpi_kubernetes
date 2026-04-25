"""Synthetic market-data producer.

Generates a stationary random walk per symbol and emits both
``market.trade.v1`` ticks and 1s ``market.bar.v1`` aggregates. No external
credentials required, so this is the recommended starting point for local
development and CI smoke tests.

Usage (in-cluster):
    python synthetic_producer.py --rate 20 --symbols AAPL.NASDAQ,MSFT.NASDAQ

The corresponding Avro schemas are the same files used by the Flink jobs at
``flink-jobs/jobs/schemas/``.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import time
from pathlib import Path
from typing import Dict, List

from prometheus_client import start_http_server

from common import AvroCodec, KafkaSettings, build_producer, configure_tracing, produce_with_tracing

logger = logging.getLogger(__name__)

SCHEMAS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "flink-jobs" / "jobs" / "schemas"


def _load_schema(name: str) -> Dict:
    path = SCHEMAS_DIR / f"{name}.avsc"
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rate", type=int, default=10, help="Records per second per symbol")
    parser.add_argument(
        "--symbols",
        type=str,
        default="AAPL.NASDAQ,MSFT.NASDAQ,SPY.NYSE,TSLA.NASDAQ",
        help="Comma-separated list of vt_symbols",
    )
    parser.add_argument("--trade-topic", type=str, default="market.trade.v1")
    parser.add_argument("--bar-topic", type=str, default="market.bar.v1")
    parser.add_argument("--bar-period-seconds", type=int, default=1)
    parser.add_argument("--metrics-port", type=int, default=9310)
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = _args()
    settings = KafkaSettings()

    tracer = configure_tracing("synthetic-producer", settings.otel_endpoint)
    start_http_server(args.metrics_port)

    codec = AvroCodec(settings.schema_registry_url, settings.schema_group, auto_register=True)
    codec.register("market_trade_v1", _load_schema("market_trade_v1"))
    codec.register("market_bar_v1", _load_schema("market_bar_v1"))

    producer = build_producer(settings, client_id="synthetic-producer")

    symbols: List[str] = [s.strip() for s in args.symbols.split(",") if s.strip()]
    prices = {sym: random.uniform(100.0, 500.0) for sym in symbols}
    bar_state = {sym: {"open": prices[sym], "high": prices[sym], "low": prices[sym], "volume": 0.0}
                 for sym in symbols}
    last_bar_ns = time.time_ns()
    tick_interval = 1.0 / max(args.rate, 1) / len(symbols)
    bar_period_ns = args.bar_period_seconds * 1_000_000_000

    logger.info("synthetic producer starting rate=%d symbols=%s", args.rate, symbols)
    try:
        while True:
            now = time.time_ns()
            for sym in symbols:
                drift = random.gauss(0, 0.1)
                prices[sym] = max(1.0, prices[sym] + drift)
                size = random.randint(1, 200)

                trade = {
                    "ts_ns": now,
                    "vt_symbol": sym,
                    "price": round(prices[sym], 4),
                    "size": size,
                    "exchange": sym.split(".")[-1],
                    "conditions": [],
                    "received_ts_ns": now,
                }
                produce_with_tracing(
                    producer,
                    codec,
                    producer_name="synthetic",
                    schema_name="market_trade_v1",
                    topic=args.trade_topic,
                    record=trade,
                    key=sym,
                    tracer=tracer,
                )

                state = bar_state[sym]
                state["high"] = max(state["high"], prices[sym])
                state["low"] = min(state["low"], prices[sym])
                state["volume"] += size

            # close bar on period boundary
            if now - last_bar_ns >= bar_period_ns:
                for sym, state in bar_state.items():
                    bar = {
                        "ts_ns": now,
                        "vt_symbol": sym,
                        "open": state["open"],
                        "high": state["high"],
                        "low": state["low"],
                        "close": prices[sym],
                        "volume": state["volume"],
                        "trade_count": 0,
                        "vwap": prices[sym],
                        "exchange": sym.split(".")[-1],
                        "received_ts_ns": now,
                    }
                    produce_with_tracing(
                        producer,
                        codec,
                        producer_name="synthetic",
                        schema_name="market_bar_v1",
                        topic=args.bar_topic,
                        record=bar,
                        key=sym,
                        tracer=tracer,
                    )
                    bar_state[sym] = {
                        "open": prices[sym],
                        "high": prices[sym],
                        "low": prices[sym],
                        "volume": 0.0,
                    }
                last_bar_ns = now

            time.sleep(tick_interval)
    except KeyboardInterrupt:
        logger.info("interrupted, flushing")
    finally:
        producer.flush(15)
        codec.close()


if __name__ == "__main__":
    main()
