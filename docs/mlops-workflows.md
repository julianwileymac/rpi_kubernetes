# MLOps Workflows Guide

This guide covers Argo Workflows, Dagster, BentoML, and Apache Flink for ML and data orchestration, model serving, and real-time stream processing.

## Overview

The cluster provides four key MLOps and data processing tools:

- **Argo Workflows** - Kubernetes-native workflow engine for ML pipelines
- **Dagster** - Data and asset orchestration platform
- **BentoML / Yatai** - Model serving and deployment platform
- **Apache Flink** - Distributed stream processing for real-time trading data

## Argo Workflows

### Use Cases

- ML training pipelines
- Data preprocessing workflows
- Model evaluation and validation
- Distributed training coordination
- CI/CD for ML models

### Access

- **Internal**: `http://argo-workflows-server.mlops:2746`
- **External**: `http://argo.local`

### Workflows vs Events (Important)

- **Argo Workflows** provides `Workflow`, `WorkflowTemplate`, and `CronWorkflow`.
- **Argo Events** provides `Sensor`, `EventSource`, and `EventBus`.

Argo Workflows UI/API may still query Argo Events resource discovery. If Argo Events
CRDs are missing, you can see:
`Not Found: the server could not find the requested resource (get sensors.argoproj.io)`.

Install Argo Events and a default EventBus:

```bash
helm upgrade --install argo-events argo/argo-events \
  --namespace mlops \
  --create-namespace \
  -f kubernetes/mlops/argo-events/values.yaml

kubectl apply -k kubernetes/mlops/argo-events/
kubectl get crd sensors.argoproj.io eventsources.argoproj.io eventbus.argoproj.io
```

### Basic Workflow Example

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Workflow
metadata:
  generateName: ml-pipeline-
  namespace: mlops
spec:
  entrypoint: train-model
  templates:
    - name: train-model
      dag:
        tasks:
          - name: prepare-data
            template: data-prep
          - name: train
            dependencies: [prepare-data]
            template: train-job
          - name: evaluate
            dependencies: [train]
            template: evaluate-job
    
    - name: data-prep
      container:
        image: python:3.11
        command: [python, -c]
        args: ["print('Preparing data...')"]
        resources:
          requests:
            memory: 1Gi
            cpu: 500m
    
    - name: train-job
      container:
        image: rayproject/ray:2.9.0
        command: [python, -c]
        args: ["print('Training model...')"]
        resources:
          requests:
            memory: 2Gi
            cpu: 1000m
    
    - name: evaluate-job
      container:
        image: python:3.11
        command: [python, -c]
        args: ["print('Evaluating model...')"]
        resources:
          requests:
            memory: 1Gi
            cpu: 500m
```

### Integration with Ray

Launch distributed Ray jobs from Argo Workflows:

```yaml
- name: ray-training
  container:
    image: rayproject/ray:2.9.0
    command: [ray, submit]
    args:
      - --address=ray-head.ml-platform:10001
      - --working-dir=/workspace
      - train_distributed.py
    env:
      - name: MLFLOW_TRACKING_URI
        value: http://mlflow.ml-platform:5000
```

### Integration with MLFlow

Log experiments and register models:

```yaml
- name: train-and-log
  container:
    image: python:3.11
    env:
      - name: MLFLOW_TRACKING_URI
        value: http://mlflow.ml-platform:5000
    command: [python, -c]
    args:
      - |
        import mlflow
        import mlflow.sklearn
        
        with mlflow.start_run():
            # Train model
            model = train_model()
            
            # Log parameters and metrics
            mlflow.log_param("epochs", 10)
            mlflow.log_metric("accuracy", 0.95)
            
            # Register model
            mlflow.sklearn.log_model(model, "model")
```

### Artifact Management

Workflows store artifacts in MinIO:

```yaml
- name: save-artifact
  container:
    image: python:3.11
    command: [python, -c]
    args: ["print('Saving artifact...')"]
  outputs:
    artifacts:
      - name: model
        path: /workspace/model.pkl
        s3:
          endpoint: minio.data-services.svc.cluster.local:9000
          bucket: argo-workflows
          key: models/{{workflow.name}}/model.pkl
          accessKeySecret:
            name: argo-workflows-minio
            key: accesskey
          secretKeySecret:
            name: argo-workflows-minio
            key: secretkey
```

### Workflow Templates

Create reusable workflow templates:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: WorkflowTemplate
metadata:
  name: ml-training-template
  namespace: mlops
spec:
  entrypoint: train
  templates:
    - name: train
      dag:
        tasks:
          - name: train
            template: train-job
    # ... templates ...
```

## Dagster

### Use Cases

- Data pipeline orchestration with software-defined assets
- Scheduled orchestration and event-driven automation
- Backfills and partition-aware data processing
- Cross-service workflows that launch Kubernetes jobs

### Access

- **Internal**: `http://dagster-webserver.mlops`
- **External**: `http://dagster.local`

### Runtime Integration

- Dagster webserver and daemon run in `mlops` namespace.
- Dagster metadata is stored in PostgreSQL (`postgresql.data-services.svc.cluster.local`).
- Dagster compute logs use MinIO (`dagster-artifacts` bucket).
- Telemetry is exported to OpenTelemetry Collector over OTLP.

### Pipeline Recipes (Implemented)

The repository now ships runnable MVP recipes under:
`kubernetes/mlops/pipelines/` and Python runtime code in `pipelines/`.

#### 1) Argo raw ingest (HTTP/REST/S3/filesystem -> MinIO)

```bash
argo submit --from workflowtemplate/pipeline-raw-ingest -n mlops \
  -p source_type=http \
  -p source_name=sample-http \
  -p source_uri=https://example.com/data.json
```

#### 2) Dagster asset load (MinIO -> PostgreSQL)

Dagster asset: `minio_to_postgres_curated` in
`pipelines/dagster_user_code/assets.py`.

#### 3) Hybrid orchestration (Dagster -> Argo heavy transform)

Dagster asset: `hybrid_argo_heavy_transform` submits template
`pipeline-heavy-transform` and reports workflow status.

#### 4) Vector sync (MinIO -> Milvus + ChromaDB + PostgreSQL audit)

```bash
argo submit --from workflowtemplate/pipeline-vector-sync -n mlops \
  -p source_key=processed/heavy/sample.json \
  -p collection_name=pipeline_documents
```

#### 5) CDC incremental sync (PostgreSQL source -> MinIO + sink tables)

```bash
argo submit --from workflowtemplate/pipeline-cdc-sync -n mlops \
  -p pipeline_name=cdc-source-events \
  -p source_table=source_events
```

Production-hardening TODOs are included directly in manifests/code comments for:
- retry/backoff and dead-letter handling
- source pagination and replay windows
- embedding model version pinning and re-embedding strategy
- credential externalization and image digest pinning

## BentoML / Yatai

### Use Cases

- Model serving as REST APIs
- Model versioning and management
- A/B testing different model versions
- Production model deployment
- Integration with MLFlow model registry

### Access

- **Internal**: `http://yatai.ml-platform:3000`
- **External**: `http://yatai.local`

### Creating a Bento Service

#### 1. Define Service

```python
# service.py
import bentoml
from bentoml.io import JSON, NumpyNdarray
import numpy as np

@bentoml.service(
    resources={"cpu": "1", "memory": "2Gi"},
    traffic={"timeout": 60}
)
class MyMLService:
    @bentoml.api(input=JSON(), output=JSON())
    def predict(self, input_data: dict):
        # Your inference logic
        result = model.predict(input_data["features"])
        return {"prediction": result.tolist()}
    
    @bentoml.api(input=NumpyNdarray(), output=NumpyNdarray())
    def predict_batch(self, input_array: np.ndarray):
        # Batch prediction
        return model.predict(input_array)
```

#### 2. Build Bento

```python
# build_bento.py
import bentoml

# Build the service
svc = MyMLService()

# Save as Bento
bentoml.build("my-ml-service:latest")
```

#### 3. Deploy to Kubernetes

```python
# deploy.py
import bentoml

# Deploy using Yatai
yatai_client = bentoml.YataiClient()

deployment = yatai_client.deployment.create(
    name="my-ml-service",
    bento="my-ml-service:latest",
    namespace="ml-platform",
    replicas=2
)
```

### Integration with MLFlow

Deploy models from MLFlow registry:

```python
import mlflow
import bentoml

# Load model from MLFlow
model = mlflow.sklearn.load_model("models:/my-model/Production")

# Create BentoML service
svc = bentoml.sklearn.save_model("my-model", model)

# Deploy
bentoml.deploy("my-model", platform="yatai")
```

### Integration with Ray

Use Ray for distributed inference:

```python
import ray
from bentoml.io import JSON

@bentoml.service(
    resources={"cpu": "2", "memory": "4Gi"}
)
class RayMLService:
    @bentoml.api(input=JSON(), output=JSON())
    def predict(self, input_data):
        @ray.remote
        def process_chunk(chunk):
            return model.predict(chunk)
        
        # Distribute processing
        results = ray.get([
            process_chunk.remote(chunk) 
            for chunk in data_chunks
        ])
        return {"predictions": results}
```

### Model Versioning

BentoML tracks model versions automatically:

```python
# List all versions
bentoml.models.list()

# Load specific version
model = bentoml.models.get("my-model:latest")
model = bentoml.models.get("my-model:v1.0.0")

# Tag versions
bentoml.models.tag("my-model:latest", "production")
```

## Complete ML Pipeline Example

### Workflow: Train → Evaluate → Deploy

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Workflow
metadata:
  generateName: ml-pipeline-
  namespace: mlops
spec:
  entrypoint: ml-pipeline
  templates:
    - name: ml-pipeline
      dag:
        tasks:
          - name: train
            template: train-model
          - name: evaluate
            dependencies: [train]
            template: evaluate-model
          - name: deploy
            dependencies: [evaluate]
            template: deploy-model
            when: "{{tasks.evaluate.outputs.result}} == success"
    
    - name: train-model
      container:
        image: python:3.11
        command: [python, train.py]
        env:
          - name: MLFLOW_TRACKING_URI
            value: http://mlflow.ml-platform:5000
        resources:
          requests:
            memory: 4Gi
            cpu: 2000m
    
    - name: evaluate-model
      container:
        image: python:3.11
        command: [python, evaluate.py]
        env:
          - name: MLFLOW_TRACKING_URI
            value: http://mlflow.ml-platform:5000
        resources:
          requests:
            memory: 2Gi
            cpu: 1000m
    
    - name: deploy-model
      container:
        image: bentoml/bentoml:latest
        command: [bentoml, deploy]
        args:
          - --yatai-endpoint=http://yatai.ml-platform:3000
          - my-model:latest
        resources:
          requests:
            memory: 1Gi
            cpu: 500m
```

## Monitoring

### Argo Workflows Metrics

Argo Workflows exposes Prometheus metrics. Create a ServiceMonitor:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: argo-workflows-controller
  namespace: observability
spec:
  namespaceSelector:
    matchNames:
      - mlops
  selector:
    matchLabels:
      app: argo-workflows-controller-metrics
  endpoints:
    - port: metrics
      path: /metrics
      interval: 30s
```

### Dagster Telemetry

Dagster is configured with OTLP environment variables and sends telemetry to:
`otel-collector.observability.svc.cluster.local:4317`.

If your Dagster image exposes Prometheus metrics on `/metrics`, keep the
`dagster-webserver` ServiceMonitor in `kubernetes/observability/prometheus/servicemonitors.yaml`
enabled for pull-based dashboards.

### BentoML Service Metrics

BentoML services expose metrics automatically. Monitor in Grafana:

- Request latency
- Request throughput
- Error rates
- Resource usage

## Best Practices

1. **Use Workflow Templates**: Reusable pipeline definitions
2. **Version Models**: Track all model versions in MLFlow
3. **Test Before Deploy**: Validate models before production
4. **Monitor Resources**: Watch CPU/memory usage
5. **Automate Pipelines**: Trigger workflows on events
6. **Use Artifacts**: Store intermediate results in MinIO

## Troubleshooting

### Workflow Not Starting

```bash
# Check workflow status
kubectl get workflows -n mlops

# Check workflow logs
argo logs <workflow-name> -n mlops

# Check pod events
kubectl describe pod <pod-name> -n mlops
```

### BentoML Deployment Issues

```bash
# Check Yatai logs
kubectl logs -n ml-platform -l app=yatai

# Check deployment status
kubectl get deployments -n ml-platform

# Check service endpoints
kubectl get endpoints -n ml-platform
```

## Apache Flink (Stream Processing)

### Overview

Apache Flink provides real-time stream processing for the algorithmic trading pipeline. It consumes market data from Kafka, computes technical indicators and normalized features, and writes to multiple sinks (PostgreSQL, MinIO, VictoriaMetrics, and downstream Kafka topics for backtesting and ML inference).

### Architecture

Market data is produced by either the sample producers under
[`samples/market-data-producers/`](../samples/market-data-producers/) or the
external **agentic_quant_platform** ingesters (`IBKRIngester`,
`AlpacaIngester`). Records land on twelve canonical Avro-schemed topics.
Two runtimes process the stream in parallel: **PyFlink** for the MVP set
and **Java Flink + TA-Lib** for the full indicator catalog.

```
IBKR / Alpaca / Polygon / yfinance / synthetic                 Java sample
               │                                                    │
               └──────────── Strimzi Kafka ───────────── Apicurio Registry
                                 (data-services)             (Avro schemas)
               │
               ▼
  market.trade.v1   market.quote.v1   market.bar.v1
  market.snapshot.v1  market.scanner.v1  market.contract.v1
  market.imbalance.v1  market.status.v1  market.correction.v1
               │
   ┌───────────┴───────────┐
   ▼                       ▼
PyFlink jobs         Java TA-Lib jobs (full catalog)
├─ dedupe            ├─ indicators-overlap (SMA, EMA, BBANDS, SAR, ...)
├─ indicator_compute ├─ indicators-momentum (RSI, MACD, ADX, STOCH*, ...)
├─ normalize_sink    ├─ indicators-volume (AD, ADOSC, OBV)
└─ scanner_alert     ├─ indicators-volatility (ATR, NATR, TRANGE)
                     ├─ indicators-price-transform
                     ├─ indicators-cycle (HT_DCPERIOD, HT_PHASOR, ...)
                     ├─ indicators-statistic (LINEARREG, CORREL, STDDEV)
                     ├─ indicators-patterns (61 CDL* candlestick patterns)
                     ├─ indicators-math-transform (ACOS ... TANH)
                     └─ indicators-math-operator (ADD, MIN, MAX, SUM, ...)
               │
               ▼
  features.indicators.v1 + features.normalized.v1 + features.signals.v1
               │
   ┌───────────┼────────────┐
   ▼           ▼            ▼
 Kafka       KafkaDataFeed  Kafka Connect
 Bridge      (aqp.trading)  S3 / JDBC sinks
               │
               ▼
 strategies / paper trader / /live WS / Dagster materializations
```

Full architecture: see [docs/ta-indicators.md](./ta-indicators.md) for the
per-category indicator mapping and
[agentic_quant_platform/docs/streaming.md](https://github.com/julianwiley/agentic_quant_platform/blob/main/docs/streaming.md)
for the upstream producer patterns.

### Access

- **Flink Web UI**: `http://flink.local` (via ingress) or `kubectl port-forward -n flink svc/flink-trading-rest 8081:8081`
- **Kafka Bootstrap**: `trading-kafka-kafka-bootstrap.data-services.svc.cluster.local:9092` (internal only)

### Deployment Model

Flink runs as a **Session Cluster** managed by the Flink Kubernetes Operator. The operator watches the `flink` namespace and manages `FlinkDeployment` and `FlinkSessionJob` custom resources.

- **JobManager**: 1 replica, 1Gi memory, on control plane
- **TaskManagers**: 2 replicas, 1.5Gi memory each, spread across workers
- **State Backend**: RocksDB with incremental checkpoints stored in MinIO
- **High Availability**: Kubernetes-based HA with leader election

### Kafka Topics

| Topic | Partitions | Retention | Purpose |
|-------|-----------|-----------|---------|
| `market.trade.v1` | 12 | 1d | Tick-level trades (IBKR tickByTick + Alpaca trades) |
| `market.quote.v1` | 12 | 1d | Tick-level NBBO quotes |
| `market.bar.v1` | 6 | 7d | 5s/1m/1d OHLCV bars |
| `market.snapshot.v1` | 6 | 7d | IBKR `reqMktData` tick map (delayed + live) |
| `market.scanner.v1` | 3 | 7d | IBKR `reqScannerSubscription` rows |
| `market.contract.v1` | 1 | compacted | IBKR `reqContractDetails` metadata |
| `market.imbalance.v1` | 3 | 7d | Alpaca order imbalances |
| `market.status.v1` | 3 | 7d | Halts / LULDs / trading status |
| `market.correction.v1` | 3 | 7d | Alpaca trade corrections and cancels |
| `features.indicators.v1` | 6 | 30d | Per-symbol SMA/EMA/RSI/MACD/... |
| `features.normalized.v1` | 6 | 30d | Z-score normalized feature vectors |
| `features.signals.v1` | 6 | 30d | Strategy-ready trading signals |
| `market.deadletter.v1` | 1 | 30d | Producer-failure fallback |

### FlinkSessionJob Manifests

Session job CRs ship in two directories:

- [`kubernetes/base-services/flink/jobs/`](../kubernetes/base-services/flink/jobs/) -- PyFlink jobs (dedupe, indicator-compute, normalize-sink, scanner-alert).
- [`kubernetes/base-services/flink/jobs-java/`](../kubernetes/base-services/flink/jobs-java/) -- Java TA-Lib jobs (10 categories).

All CRs start `state: suspended`. Activate via kubectl or the management API:

```bash
# List all session jobs
kubectl get flinksessionjobs -n flink

# Build + push images / upload JARs
bash bootstrap/scripts/build-flink-jobs.sh --push
bash bootstrap/scripts/build-flink-jobs-java.sh --push

# Activate via kubectl
kubectl patch flinksessionjob indicator-compute -n flink \
  --type merge -p '{"spec":{"job":{"state":"running"}}}'

# ... or via the management API / Python SDK
curl -XPOST http://control.local/api/flink/sessionjobs/indicators-momentum/activate
```

Consume from Python using the [Python SDK](../management/sdk/):

```python
from rpi_k8s_sdk import configure_tracing
from rpi_k8s_sdk.kafka import AvroConsumer

configure_tracing("strategy-consumer")
async with AvroConsumer(
    bootstrap="trading-kafka-kafka-bootstrap.data-services:9094",
    topics=["features.indicators.v1"],
    group_id="my-strategy",
    username="consumer-management",
    password=password,
    ssl_cafile="/etc/kafka/ca/ca.crt",
) as consumer:
    async for msg in consumer:
        print(msg.value["vt_symbol"], msg.value.get("extras"))
```

### PostgreSQL Integration

Flink writes to the `flink_trading` schema in the existing PostgreSQL instance:

- `flink_trading.market_data` -- raw tick storage
- `flink_trading.indicators` -- computed technical indicators
- `flink_trading.signals` -- normalized signals with feature vectors
- `flink_trading.job_metadata` -- job execution tracking

```bash
# Verify schema
kubectl exec -n data-services deploy/postgresql -- \
  psql -U postgres -c "\dt flink_trading.*"
```

### Connecting Flink to Argo / Dagster

**Argo triggering Flink savepoints:**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: WorkflowTemplate
metadata:
  name: flink-savepoint
  namespace: mlops
spec:
  entrypoint: trigger-savepoint
  templates:
    - name: trigger-savepoint
      container:
        image: bitnami/kubectl:latest
        command: [kubectl]
        args:
          - patch
          - flinksessionjob/market-data-ingest
          - -n
          - flink
          - --type
          - merge
          - -p
          - '{"spec":{"job":{"state":"suspended","upgradeMode":"savepoint"}}}'
```

**Dagster materializing from Flink sink tables:**

```python
from dagster import asset
import pandas as pd
from sqlalchemy import create_engine

@asset(group_name="trading")
def flink_signals_snapshot():
    """Materialize a snapshot of Flink-produced signals for ML training."""
    engine = create_engine(
        "postgresql://postgres:postgres123@postgresql.data-services:5432/postgres"
    )
    return pd.read_sql(
        "SELECT * FROM flink_trading.signals WHERE signal_timestamp > NOW() - INTERVAL '1 day'",
        engine,
    )
```

### Monitoring

Flink exposes Prometheus metrics on port 9249. A dedicated Grafana dashboard ("Flink Trading Pipeline") is provisioned automatically and shows:

- Running jobs and available task slots
- Records in/out per second per task
- Checkpoint duration and size
- JVM heap usage (JobManager and TaskManagers)
- Kafka consumer lag
- Backpressure indicators

Metrics flow: Flink :9249 -> Prometheus scrape -> remote_write -> VictoriaMetrics (90-day retention).

## Additional Resources

- [Data Pipeline Recipes](data-pipeline-recipes.md)
- [Argo Workflows Documentation](https://argoproj.github.io/argo-workflows/)
- [Dagster Documentation](https://docs.dagster.io/)
- [BentoML Documentation](https://docs.bentoml.com/)
- [MLFlow Documentation](https://mlflow.org/docs/latest/index.html)
- [Ray Documentation](https://docs.ray.io/)
- [Apache Flink Documentation](https://nightlies.apache.org/flink/flink-docs-stable/)
- [Flink Kubernetes Operator](https://nightlies.apache.org/flink/flink-kubernetes-operator-docs-stable/)
- [Strimzi Kafka Operator](https://strimzi.io/documentation/)
