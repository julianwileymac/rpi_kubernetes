# Data Pipeline Recipes (Argo + Dagster + Flink)

This guide provides runnable MVP recipes for moving, processing, and loading data across:

- Sources: HTTP files, REST APIs, S3-compatible sources, PostgreSQL tables, filesystem/NFS, Kafka topics
- Sinks: MinIO, PostgreSQL, Milvus, ChromaDB, Kafka topics, VictoriaMetrics

## Prerequisites

```bash
# Argo and Dagster must be deployed first
helm list -n mlops

# Build and publish runtime image used by Argo and Dagster user-code
docker build -f pipelines/Dockerfile -t ghcr.io/julianwiley/rpi-k8s-pipelines:latest .
docker push ghcr.io/julianwiley/rpi-k8s-pipelines:latest

# Apply pipeline manifests (templates, cron, secrets, bootstrap SQL, RBAC)
kubectl apply -k kubernetes/mlops/pipelines/
```

## Recipe 1: Raw ingest to MinIO

### Goal
Download from HTTP/REST/S3/filesystem and store raw immutable objects in MinIO.

### Run

```bash
argo submit --from workflowtemplate/pipeline-raw-ingest -n mlops \
  -p source_type=http \
  -p source_name=sample-http \
  -p source_uri=https://example.com/data.json \
  -p output_prefix=raw/manual \
  -p target_bucket=dagster-artifacts
```

### Verify

```bash
argo list -n mlops
argo logs @latest -n mlops
kubectl exec -n data-services deploy/minio -- mc ls local/dagster-artifacts/raw/manual/
```

### Hardening TODO
- Add pagination per source type
- Add dead-letter bucket path for failed pulls
- Add retention lifecycle policies

## Recipe 2: Dagster asset load MinIO -> PostgreSQL

### Goal
Materialize processed objects from MinIO into curated PostgreSQL tables.

### Run

Use Dagster UI at `http://dagster.local`, materialize asset:
- `minio_to_postgres_curated`

Default asset config:
- `source_bucket`: `dagster-artifacts`
- `source_key`: `processed/heavy/sample.json`
- `target_table`: `pipeline_curated_records`

### Verify

```bash
kubectl exec -n data-services deploy/postgresql -- \
  psql -U postgres -d dagster -c "select count(*) from pipeline_curated_records;"
```

### Hardening TODO
- Add schema contracts and validation checks
- Add typed target table models per pipeline

## Recipe 3: Hybrid Dagster -> Argo heavy transform

### Goal
Use Dagster for control/lineage while Argo runs heavy K8s-native transforms.

### Run

Materialize Dagster asset:
- `hybrid_argo_heavy_transform`

This submits Argo `WorkflowTemplate`:
- `pipeline-heavy-transform`

### Verify

```bash
argo list -n mlops
argo get @latest -n mlops
```

### Hardening TODO
- Add per-template retry and timeout policies
- Add resource classes for heavy workloads

## Recipe 4: Vector sync to Milvus and ChromaDB

### Goal
Chunk text payloads, generate embeddings, and dual-write vectors to Milvus and ChromaDB.

### Run

```bash
argo submit --from workflowtemplate/pipeline-vector-sync -n mlops \
  -p source_key=processed/heavy/sample.json \
  -p source_bucket=dagster-artifacts \
  -p collection_name=pipeline_documents
```

### Verify

```bash
kubectl exec -n data-services deploy/postgresql -- \
  psql -U postgres -d dagster -c "select count(*) from pipeline_vector_audit;"
```

### Hardening TODO
- Replace deterministic fallback embedding with production model endpoint
- Add model version + re-embedding strategy

## Recipe 5: CDC incremental sync

### Goal
Incrementally pull changed rows from source PostgreSQL and persist deltas to MinIO + sink tables.

### Run

```bash
argo submit --from workflowtemplate/pipeline-cdc-sync -n mlops \
  -p pipeline_name=cdc-source-events \
  -p source_table=source_events \
  -p primary_key=id \
  -p updated_at_column=updated_at
```

### Verify

```bash
kubectl exec -n data-services deploy/postgresql -- \
  psql -U postgres -d dagster -c "select * from pipeline_cdc_state;"
kubectl exec -n data-services deploy/minio -- mc ls local/dagster-artifacts/cdc/
```

### Hardening TODO
- Add conflict handling rules (upsert vs append)
- Add replay window for late-arriving rows

## Recipe 6: Real-time Stream Processing (Flink + AQP ingesters)

### Goal
Run the end-to-end streaming platform:
[agentic_quant_platform](https://github.com/julianwiley/agentic_quant_platform)
ingesters publish canonical Avro records to Kafka, PyFlink jobs on this
cluster compute indicators and normalize features, and consumers
(strategies, paper trader, KafkaDataFeed) read the processed stream
back.

### Prerequisites

```bash
# Flink + Kafka must be deployed (see setup-guide.md Step 7.4)
kubectl get flinkdeployments -n flink
kubectl get kafkatopics -n data-services

# PostgreSQL flink_trading schema must exist. aqp ships the migration
# at aqp/alembic/versions/0005_flink_trading_schema.py -- run
#   alembic upgrade head
# in that repo, or apply the schema ConfigMap manually:
kubectl exec -n data-services deploy/postgresql -- \
  psql -U postgres -c "\dn flink_trading"

# The custom Flink image must be built + pushed and job .py files
# uploaded to MinIO before the FlinkSessionJob CRs will resolve:
bash bootstrap/scripts/build-flink-jobs.sh --push
```

### Data Flow

```
IBKRIngester -+                              +---> market.trade.v1
              |                              |     market.quote.v1
              +----> Strimzi Kafka ----------+     market.bar.v1
              |       (data-services)        |     market.snapshot.v1
AlpacaIngester+                              +---> market.scanner.v1
                                             |     market.contract.v1
                                             |     market.imbalance.v1
                                             |     market.status.v1
                                             |     market.correction.v1
                                             |
                  +--------------------------+
                  v
         Flink Session Cluster (PyFlink jobs)
         - dedupe
         - indicator_compute   -> features.indicators.v1
         - normalize_sink      -> features.normalized.v1 + PG/MinIO/VM
         - scanner_alert       -> features.signals.v1
                  |
                  v
  KafkaDataFeed (aqp.trading.feeds.kafka_feed.KafkaDataFeed)
  -> strategies / paper trader / /live WebSocket
```

### Run

```bash
# 1. Start the aqp ingesters (produces to the canonical topics).
# In the aqp repo:
kubectl apply -k deploy/k8s/base/

# Or locally:
pip install -e ".[alpaca,ibkr,streaming]"
aqp-stream-ingest --venue all

# 2. Activate the Flink PyFlink jobs:
kubectl patch flinksessionjob market-data-dedupe -n flink \
  --type merge -p '{"spec":{"job":{"state":"running"}}}'
kubectl patch flinksessionjob indicator-compute -n flink \
  --type merge -p '{"spec":{"job":{"state":"running"}}}'
kubectl patch flinksessionjob normalize-sink -n flink \
  --type merge -p '{"spec":{"job":{"state":"running"}}}'
kubectl patch flinksessionjob scanner-alert -n flink \
  --type merge -p '{"spec":{"job":{"state":"running"}}}'
```

### Verify

```bash
# Check Flink job status
kubectl get flinksessionjobs -n flink

# Check Flink Web UI
kubectl port-forward -n flink svc/flink-trading-rest 8081:8081
# Open http://localhost:8081

# Check Kafka topic offsets (requires kafka CLI in the broker pod)
kubectl exec -n data-services trading-kafka-combined-0 -- \
  bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe

# Check ingester metrics (Prometheus endpoint on :9300 of each pod)
kubectl port-forward -n aqp svc/aqp-ingester-ibkr 9300:9300 &
curl -s http://localhost:9300/metrics | grep aqp_stream_ingest_total

# Check PostgreSQL sink
kubectl exec -n data-services deploy/postgresql -- \
  psql -U postgres -c "SELECT count(*) FROM flink_trading.market_data;"
kubectl exec -n data-services deploy/postgresql -- \
  psql -U postgres -c "SELECT count(*) FROM flink_trading.signals;"

# Check Grafana dashboard
# Open "Flink Trading Pipeline" dashboard for records in/out, checkpoint health,
# consumer lag, and backpressure
```

### Consume from aqp (KafkaDataFeed)

```python
# Directly from a strategy / notebook
from aqp.trading.feeds.kafka_feed import KafkaDataFeed

feed = KafkaDataFeed(emit_as="signal")
await feed.connect()
async for sig in feed.stream():
    print(sig.vt_symbol, sig.direction, sig.strength)
```

Or via the HTTP API:

```bash
curl -X POST http://aqp-api.aqp.svc.cluster.local:8000/live/subscribe \
  -H 'content-type: application/json' \
  -d '{"venue":"kafka","symbols":["AAPL.NASDAQ","MSFT.NASDAQ"],
       "kafka_topic":"features.normalized.v1","kafka_emit_as":"bar"}'
```

### Savepoint and Upgrade

```bash
# Trigger savepoint before upgrading a job
kubectl patch flinksessionjob indicator-compute -n flink \
  --type merge -p '{"spec":{"job":{"state":"suspended","upgradeMode":"savepoint"}}}'

# Check savepoint location
kubectl get flinksessionjob indicator-compute -n flink \
  -o jsonpath='{.status.jobStatus.savepointInfo}'

# Resume from savepoint (automatic when state set back to running)
kubectl patch flinksessionjob indicator-compute -n flink \
  --type merge -p '{"spec":{"job":{"state":"running"}}}'
```

### Hardening TODO
- Promote from the MVP SimpleStringSchema wrapper to full Avro ser-de end-to-end
  (the cluster now runs Apicurio Schema Registry - point PyFlink at
  `http://apicurio-registry.data-services.svc.cluster.local:8080/apis/registry/v2`)
- Add dedicated deadletter consumer + alerting
- Tune checkpoint interval based on observed throughput
- Add alerting rules for consumer lag and failed checkpoints
- Configure per-symbol partitioning strategy and multi-gateway IBKR fan-out

## Recipe 7: Full TA-Lib Indicator Catalog (Java Flink jobs)

### Goal
Run the complete TA-Lib indicator catalog (~158 indicators + ~61
candlestick patterns) against `market.bar.v1` using the Java Flink jobs
under [`flink-jobs-java/`](../flink-jobs-java/). See
[docs/ta-indicators.md](./ta-indicators.md) for the full per-job indicator
mapping.

### Prerequisites

```bash
# Kafka + Flink + Apicurio already deployed (bootstrap/scripts/install-flink.sh)
kubectl get kafka trading-kafka -n data-services
kubectl get flinkdeployments -n flink
kubectl get pods -n data-services -l app=apicurio-registry

# Build + push the Java image and upload per-category jars to MinIO
bash bootstrap/scripts/build-flink-jobs-java.sh --push
```

### Data Flow

```
Sample producers ---------------+
(synthetic, polygon,            |
 alpaca, ibkr, yfinance)        v
                    +------ Strimzi Kafka (data-services) -----+
                    | topic: market.bar.v1                      |
                    +-------------------------------------------+
                                       |
                                       v
        Flink Java Session Jobs (flink namespace)
          - indicators-overlap         (SMA, EMA, BBANDS, SAR, ...)
          - indicators-momentum        (RSI, MACD, ADX, STOCH*, ...)
          - indicators-volume          (AD, ADOSC, OBV)
          - indicators-volatility      (ATR, NATR, TRANGE)
          - indicators-price-transform (AVGPRICE, MEDPRICE, ...)
          - indicators-cycle           (HT_DCPERIOD, HT_PHASOR, ...)
          - indicators-statistic       (CORREL, LINEARREG, STDDEV, ...)
          - indicators-patterns        (61 CDL* candlestick patterns)
          - indicators-math-transform  (ACOS, SQRT, ...)
          - indicators-math-operator   (ADD, MAX, SUM, ...)
                                       |
                                       v
        topic: features.indicators.v1  (Avro + Apicurio)
                                       |
                                       v
        Downstream: normalize-sink, scanner-alert, Kafka Connect S3 sink,
                    JDBC sink -> flink_trading.kafka_signals
```

### Run

```bash
# 1. Apply the suspended CRs
kubectl apply -k kubernetes/base-services/flink/jobs-java/

# 2. Activate gradually (start with one category to confirm)
kubectl patch flinksessionjob indicators-momentum -n flink \
  --type merge -p '{"spec":{"job":{"state":"running"}}}'

# ... or via the rollback-only legacy management API
for cat in overlap momentum volume volatility price-transform \
           cycle statistic patterns math-transform math-operator; do
    curl -XPOST "http://control.local/api/flink/sessionjobs/indicators-${cat}/activate"
done
```

### Verify

```bash
# Check job status
kubectl get flinksessionjobs -n flink -l category

# Tail output
kubectl exec -n data-services trading-kafka-combined-0 -- \
  bin/kafka-console-consumer.sh \
    --bootstrap-server localhost:9092 \
    --topic features.indicators.v1 \
    --property print.key=true --max-messages 20

# The new Flink dashboard in Grafana shows per-category throughput
```

### Hardening TODO

- Enable `KafkaRebalance` (needs Cruise Control) when cluster grows beyond one broker
- Switch pipelines from `PLAINTEXT` to `SASL_SSL` via the `scram` listener
- Tune per-category `--buffer.size` based on observed symbol count + lookback
- Activate the paused `KafkaConnector` sinks
  (`s3-sink-features-indicators`, `jdbc-sink-features-signals`) once the
  target bucket + Postgres schema are provisioned

## First Run Checklist

1. Build/push `pipelines/Dockerfile` image and confirm image pull succeeds in cluster.
2. Apply `kubernetes/mlops/pipelines/` manifests and confirm:
   - `workflowtemplate` resources exist in `mlops`
   - `cronworkflow` resources exist in `mlops`
   - `pipeline-bootstrap-state` job completes successfully
3. Run Recipe 1 to create fresh raw data in MinIO.
4. Run Recipe 3 or 2 to process and load into PostgreSQL curated table.
5. Run Recipe 4 for vector sinks and check `pipeline_vector_audit`.
6. Run Recipe 5 twice and confirm second run uses advanced watermark with only deltas.
7. In Grafana, open `Workflow Orchestrators - Argo and Dagster` and confirm targets stay healthy.
8. Verify Flink session cluster is running: `kubectl get flinkdeployments -n flink`.
9. Once Flink job JARs are uploaded, activate Recipe 6 and verify in `Flink Trading Pipeline` dashboard.


## Alpha Vantage recipes

The AV integration ships a dedicated set of Argo `WorkflowTemplates` under
[`kubernetes/mlops/pipelines/alphavantage/`](../kubernetes/mlops/pipelines/alphavantage/)
that all delegate to the `pipelines.cli alphavantage-bulk` entrypoint. The
loader (see [`pipelines/alphavantage_io.py`](../pipelines/alphavantage_io.py))
writes JSON slices to `s3://av-raw/<category>/<symbol>/<slice>.json`.

Prerequisites: the `alphavantage-credentials` Secret in `mlops`
(`bootstrap/scripts/install-alphavantage.{sh,ps1}` handles it), the
`av-raw` MinIO bucket, and a pipeline image with `alphavantage-client` baked
in.

### Recipe: daily bars for a watch list

```bash
argo submit --from workflowtemplate/av-bulk-timeseries -n mlops \
  --parameter symbols=IBM,AAPL,MSFT,GOOGL,NVDA,SPY \
  --parameter function=daily_adjusted \
  --parameter outputsize=full \
  --parameter target_bucket=av-raw
```

### Recipe: 20-year intraday backfill for a symbol

```bash
argo submit --from workflowtemplate/av-intraday-backfill -n mlops \
  --parameter symbols=IBM \
  --parameter interval=5min \
  --parameter start_date=2005-01 \
  --parameter end_date=2026-04
```

### Recipe: nightly fundamentals + overview refresh

Already wired as the `av-daily-refresh` CronWorkflow (03:00 UTC). Ad hoc:

```bash
argo submit --from workflowtemplate/av-fundamentals -n mlops \
  --parameter symbols=IBM,AAPL,MSFT \
  --parameter kinds=overview,income,balance,cashflow,earnings,estimates
```

### Recipe: news sentiment ingest

```bash
argo submit --from workflowtemplate/av-news-ingest -n mlops \
  --parameter tickers=AAPL,MSFT,NVDA \
  --parameter topics=technology,earnings \
  --parameter limit=1000
```

Follow-up: [`pipelines/examples/alphavantage_news_to_redis.py`](../pipelines/examples/alphavantage_news_to_redis.py)
consumes the resulting MinIO blobs and upserts them into the `AVNewsArticle`
Redis-OM index for RAG retrieval.

### Recipe: economic indicators + commodities monthly

```bash
argo submit --from workflowtemplate/av-economics -n mlops \
  --parameter indicators=REAL_GDP,CPI,TREASURY_YIELD,FEDERAL_FUNDS_RATE \
  --parameter interval=monthly

argo submit --from workflowtemplate/av-commodities -n mlops \
  --parameter commodities=WTI,BRENT,NATURAL_GAS,COPPER,WHEAT,CORN \
  --parameter interval=monthly
```

### Recipe: submit bulk loads from the management UI

1. Open `/alphavantage/admin` on the control panel.
2. Pick a category, enter symbols + optional date range + JSON extras.
3. Click **Submit workflow**. The UI calls
   `POST /api/alphavantage/bulk-load` which submits an Argo Workflow
   referencing the matching template.
4. The workflow table below refreshes every 30s with phase + completion
   timestamps.
