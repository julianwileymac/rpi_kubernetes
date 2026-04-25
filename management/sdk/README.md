# rpi_k8s_sdk

Installable Python SDK for driving the streaming side of the
`rpi_kubernetes` cluster from notebooks, strategies, pipelines, or any other
Python workload.

The SDK wraps:

1. Strimzi-backed Kafka (produce/consume with Avro + Apicurio Schema Registry).
2. Kafka Bridge HTTP API (via the management backend proxy).
3. The management FastAPI endpoints under `/kafka` and `/flink` for granular
   Kafka/Flink control.
4. The Flink REST API (job/metric polling, savepoint queries).

## Install

```bash
pip install -e 'management/sdk[streaming]'
```

Extras:

- `streaming` - `confluent-kafka`, `aiokafka`, `fastavro`, `httpx`,
  `opentelemetry`.
- `dev` - `pytest`, `ruff`.

## Quick start

```python
from rpi_k8s_sdk import configure_tracing
from rpi_k8s_sdk.kafka import AvroProducer, AvroConsumer
from rpi_k8s_sdk.flink import ManagementFlinkClient

# Tracing (optional but recommended)
configure_tracing("my-strategy")

# Producer
with AvroProducer(
    bootstrap="trading-kafka-kafka-bootstrap.data-services:9094",
    username="producer-market",
    password=...,          # mount secret in-cluster or use Vault
    schema_registry_url="http://apicurio-registry.data-services:8080/apis/registry/v2",
) as producer:
    producer.produce(
        topic="market.trade.v1",
        schema="market_trade_v1",
        record={"ts_ns": ..., "vt_symbol": "AAPL.NASDAQ", "price": 123.45, ...},
        key="AAPL.NASDAQ",
    )

# Flink orchestration via management API
flink = ManagementFlinkClient("http://control.local/api")
flink.activate("indicator-compute")
flink.savepoint("indicator-compute")
```

See the module docstrings for reference.
