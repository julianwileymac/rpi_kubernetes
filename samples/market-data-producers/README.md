# Market Data Producer Samples

End-to-end sample producers that emit Avro records to the `trading-kafka`
cluster and, indirectly, the Flink TA-Lib indicator jobs. These samples are
the preferred onboarding material for anyone who wants to adapt a new vendor
or a new instrument universe.

All Python samples share [`python/common/`](python/common/) for Avro
encoding, SCRAM authentication, OpenTelemetry tracing, and Prometheus
metrics. They deliberately mirror the shape of
[`agentic_quant_platform`'s `aqp.streaming.ingesters.*`](https://github.com/julianwiley/agentic_quant_platform)
so moving a strategy between the two repos requires only renaming the
imports.

## Index

| Sample | Topic(s) | Purpose |
|--------|----------|---------|
| [`python/synthetic_producer.py`](python/synthetic_producer.py) | `market.trade.v1`, `market.bar.v1` | Deterministic OHLCV + trade fan-out for dev + CI. No external credentials needed. |
| [`python/polygon_producer.py`](python/polygon_producer.py) | `market.trade.v1`, `market.bar.v1` | Polygon.io REST poller. Needs `POLYGON_API_KEY`. |
| [`python/yfinance_producer.py`](python/yfinance_producer.py) | `market.bar.v1` | Batch historical replay via the `yfinance` client; great for backfills. |
| [`python/alpaca_producer.py`](python/alpaca_producer.py) | `market.trade.v1`, `market.quote.v1` | Alpaca IEX websocket streaming. |
| [`python/ibkr_producer.py`](python/ibkr_producer.py) | `market.trade.v1`, `market.quote.v1`, `market.bar.v1` | Interactive Brokers gateway via `ib_insync`. |
| [`java/StockMarketSampleProducer.java`](java/StockMarketSampleProducer.java) | `market.trade.v1` | Java reference producer with `TaxiRideGenerator`-style iteration. |

## Layout

```
samples/market-data-producers/
├── README.md
├── python/
│   ├── pyproject.toml
│   ├── common/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── kafka_io.py
│   │   ├── avro_codec.py
│   │   └── tracing.py
│   ├── synthetic_producer.py
│   ├── polygon_producer.py
│   ├── yfinance_producer.py
│   ├── alpaca_producer.py
│   └── ibkr_producer.py
├── java/
│   ├── settings.gradle
│   ├── build.gradle
│   ├── src/main/java/io/rpi/samples/
│   │   ├── StockMarketSampleProducer.java
│   │   └── MarketBarsGenerator.java
│   └── src/main/resources/log4j2.properties
└── kubernetes/
    ├── kustomization.yaml
    ├── configmap.yaml
    └── deployments.yaml
```

## Running locally

```bash
cd samples/market-data-producers/python
pip install -e ".[dev]"
python synthetic_producer.py --rate 5
```

The synthetic producer is the only sample that requires no credentials; it
generates a stationary random walk per symbol so the Flink indicator jobs
can be tested end-to-end without a broker or vendor account.
