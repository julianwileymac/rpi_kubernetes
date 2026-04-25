"""yfinance-based batch historical replay producer.

Emits ``market.bar.v1`` records derived from Yahoo Finance historical data.
Good for bootstrapping local experiments where you want a full day of bars
without waiting for a live feed. Requires ``yfinance`` + ``pandas``.
"""

from __future__ import annotations

import argparse
import json
import logging
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
    parser.add_argument("--symbols", type=str, default="AAPL,MSFT,SPY")
    parser.add_argument("--exchange", type=str, default="NASDAQ")
    parser.add_argument("--period", type=str, default="1mo",
                        help="yfinance period (e.g. 1d, 5d, 1mo, 3mo, 1y)")
    parser.add_argument("--interval", type=str, default="1m",
                        help="yfinance interval (1m, 5m, 15m, 30m, 1h, 1d)")
    parser.add_argument("--bar-topic", type=str, default="market.bar.v1")
    parser.add_argument("--rate-per-second", type=int, default=50,
                        help="Playback rate when replaying the dataset")
    parser.add_argument("--metrics-port", type=int, default=9312)
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    try:
        import yfinance as yf  # type: ignore[import]
    except ImportError:
        raise SystemExit("install with: pip install '.[yfinance]'")

    args = _args()
    settings = KafkaSettings()
    tracer = configure_tracing("yfinance-producer", settings.otel_endpoint)
    start_http_server(args.metrics_port)

    codec = AvroCodec(settings.schema_registry_url, settings.schema_group, auto_register=True)
    codec.register("market_bar_v1", _load_schema("market_bar_v1"))
    producer = build_producer(settings, client_id="yfinance-producer")

    symbols: List[str] = [s.strip() for s in args.symbols.split(",") if s.strip()]
    sleep_between = 1.0 / max(args.rate_per_second, 1)

    try:
        for symbol in symbols:
            vt = f"{symbol}.{args.exchange}"
            logger.info("downloading %s period=%s interval=%s", vt, args.period, args.interval)
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=args.period, interval=args.interval)
            for ts, row in df.iterrows():
                now = int(time.time() * 1_000_000_000)
                bar = {
                    "ts_ns": int(ts.value),  # pandas Timestamp.value is ns
                    "vt_symbol": vt,
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": float(row["Volume"]),
                    "trade_count": 0,
                    "vwap": float(row["Close"]),
                    "exchange": args.exchange,
                    "received_ts_ns": now,
                }
                produce_with_tracing(
                    producer,
                    codec,
                    producer_name="yfinance",
                    schema_name="market_bar_v1",
                    topic=args.bar_topic,
                    record=bar,
                    key=vt,
                    tracer=tracer,
                )
                time.sleep(sleep_between)
    except KeyboardInterrupt:
        logger.info("interrupted, flushing")
    finally:
        producer.flush(15)
        codec.close()


if __name__ == "__main__":
    main()
