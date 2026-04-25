"""Interactive Brokers gateway producer.

Uses ``ib_insync`` to stream tick-by-tick AllLast trades, NBBO quotes, and
5-second bars from an in-cluster IBKR gateway. Maps contract + tick types
onto the canonical Avro records.

Environment:
    IBKR_HOST       default ibkr-gateway.data-services.svc.cluster.local
    IBKR_PORT       default 4002 (paper) / 4001 (live)
    IBKR_CLIENT_ID  default 1
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
    parser.add_argument("--symbols", type=str, default="AAPL,MSFT,SPY")
    parser.add_argument("--exchange", type=str, default="NASDAQ")
    parser.add_argument("--currency", type=str, default="USD")
    parser.add_argument("--trade-topic", type=str, default="market.trade.v1")
    parser.add_argument("--quote-topic", type=str, default="market.quote.v1")
    parser.add_argument("--bar-topic", type=str, default="market.bar.v1")
    parser.add_argument("--metrics-port", type=int, default=9314)
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    try:
        from ib_insync import IB, Stock  # type: ignore[import]
    except ImportError:
        raise SystemExit("install with: pip install '.[ibkr]'")

    host = os.environ.get("IBKR_HOST", "ibkr-gateway.data-services.svc.cluster.local")
    port = int(os.environ.get("IBKR_PORT", "4002"))
    client_id = int(os.environ.get("IBKR_CLIENT_ID", "1"))

    settings = KafkaSettings()
    tracer = configure_tracing("ibkr-producer", settings.otel_endpoint)
    start_http_server(args.metrics_port)

    codec = AvroCodec(settings.schema_registry_url, settings.schema_group, auto_register=True)
    codec.register("market_trade_v1", _load_schema("market_trade_v1"))
    codec.register("market_quote_v1", _load_schema("market_quote_v1"))
    codec.register("market_bar_v1", _load_schema("market_bar_v1"))
    producer = build_producer(settings, client_id="ibkr-producer")

    symbols: List[str] = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    ib = IB()
    await ib.connectAsync(host, port, clientId=client_id)
    logger.info("connected to ibkr host=%s port=%d", host, port)

    try:
        for symbol in symbols:
            contract = Stock(symbol, args.exchange, args.currency)
            await ib.qualifyContractsAsync(contract)
            vt = f"{symbol}.{args.exchange}"

            # Tick-by-tick trades
            ticks = ib.reqTickByTickData(contract, "AllLast", 0, False)

            def on_trade_update(tick, vt_symbol=vt):  # closure captures symbol
                now = time.time_ns()
                produce_with_tracing(
                    producer,
                    codec,
                    producer_name="ibkr",
                    schema_name="market_trade_v1",
                    topic=args.trade_topic,
                    record={
                        "ts_ns": int(tick.time.timestamp() * 1_000_000_000) if tick.time else now,
                        "vt_symbol": vt_symbol,
                        "price": float(tick.price or 0.0),
                        "size": int(tick.size or 0),
                        "exchange": args.exchange,
                        "conditions": list(tick.conditions or []) if hasattr(tick, "conditions") else [],
                        "received_ts_ns": now,
                    },
                    key=vt_symbol,
                    tracer=tracer,
                )

            ticks.updateEvent += on_trade_update

            # 5-second real-time bars
            bars = ib.reqRealTimeBars(contract, 5, "TRADES", useRTH=False)

            def on_bar_update(bar_list, has_new_bar, vt_symbol=vt):
                if not has_new_bar or not bar_list:
                    return
                bar = bar_list[-1]
                now = time.time_ns()
                produce_with_tracing(
                    producer,
                    codec,
                    producer_name="ibkr",
                    schema_name="market_bar_v1",
                    topic=args.bar_topic,
                    record={
                        "ts_ns": int(bar.time.timestamp() * 1_000_000_000),
                        "vt_symbol": vt_symbol,
                        "open": float(bar.open_),
                        "high": float(bar.high),
                        "low": float(bar.low),
                        "close": float(bar.close),
                        "volume": float(bar.volume),
                        "trade_count": int(bar.count),
                        "vwap": float(bar.wap),
                        "exchange": args.exchange,
                        "received_ts_ns": now,
                    },
                    key=vt_symbol,
                    tracer=tracer,
                )

            bars.updateEvent += on_bar_update
            logger.info("subscribed %s", vt)

        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("interrupted, flushing")
    finally:
        ib.disconnect()
        producer.flush(15)
        codec.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = _args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
