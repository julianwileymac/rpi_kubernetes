# rpi_k8s_sdk

Installable Python SDK for driving the streaming side of the
`rpi_kubernetes` cluster from notebooks, strategies, pipelines, or any other
Python workload.

The SDK wraps:

1. Strimzi-backed Kafka (produce/consume with Avro + Apicurio Schema Registry).
2. Kafka Bridge HTTP API and compatibility helpers for the legacy management
   backend proxy.
3. `AqpControlPlaneClient` for AQP workload lifecycle operations through the
   `agentic_quant_platform/aqp_control_plane` `/manage/*` API.
4. The Flink REST API (job/metric polling, savepoint queries).
5. Local access profiles for MinIO, MLflow, DataHub/Iceberg, OpenTelemetry,
   Argo pipelines, and vLLM/KServe model serving.

## Install

```bash
pip install -e 'management/sdk[streaming]'
```

Extras:

- `local` - all local lab access clients.
- `storage` - boto3-backed MinIO helpers.
- `mlflow` - MLflow tracking and model registry helpers.
- `datahub` - DataHub REST emitter and recipe runner.
- `iceberg` - PyIceberg REST catalog helpers.
- `kubernetes` - Kubernetes/Argo pipeline controls.
- `serving` - Hugging Face model download helpers.
- `streaming` - `confluent-kafka`, `aiokafka`, `fastavro`, `httpx`,
  `opentelemetry`.
- `dev` - `pytest`, `ruff`.

## Quick start

```python
from rpi_k8s_sdk import configure_tracing
from rpi_k8s_sdk.aqp import AqpControlPlaneClient
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

# AQP workload lifecycle via the AQP control plane
with AqpControlPlaneClient.from_env() as cp:
    cp.health()
    cp.list_deployments(namespace="aqp")

# Legacy Flink orchestration via management API (compatibility only)
flink = ManagementFlinkClient("http://control.local/api")
flink.activate("indicator-compute")
flink.savepoint("indicator-compute")
```

See the module docstrings for reference.

## Local lab access

```python
from rpi_k8s_sdk import (
    ArgoPipelineClient,
    DataHubClient,
    IcebergClient,
    LocalTunnelManager,
    MinioClient,
    MLflowClient,
    ModelStore,
    load_settings,
)

settings = load_settings()

# Keep private APIs private: use tunnels for GMS/Iceberg and OTLP.
tunnels = LocalTunnelManager(settings)
with tunnels.started(settings.datahub_gms, settings.otel_collector):
    MinioClient(settings).health()
    MLflowClient(settings).ensure_experiment("local-smoke")
    DataHubClient(settings).mlflow_recipe()
    IcebergClient(settings).config()

    ArgoPipelineClient(settings).raw_ingest(
        source_name="sample",
        source_uri="https://example.com/data.json",
    )

# Model workflow: download locally, push to MinIO, then render a serving spec.
store = ModelStore(settings)
model_dir = store.download_hf_snapshot("TinyLlama/TinyLlama-1.1B-Chat-v1.0", local_dir=".models/tinyllama")
artifact = store.upload_directory("TinyLlama/TinyLlama-1.1B-Chat-v1.0", model_dir)
print(artifact.s3_uri)
```
