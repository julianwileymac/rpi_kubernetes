# Observability Stack Guide

This guide covers the comprehensive observability stack deployed on the RPi Kubernetes cluster, including metrics, logs, and traces.

## Architecture Overview

The observability stack consists of:

- **Prometheus** - Short-term metrics storage (15 days)
- **VictoriaMetrics** - Long-term metrics storage (90 days)
- **Loki** - Log aggregation system
- **Jaeger** - Distributed tracing
- **Grafana** - Unified visualization and dashboards
- **OpenTelemetry Collector** - Unified telemetry pipeline

## Metrics Collection

### Prometheus

Prometheus collects metrics from:
- Kubernetes cluster components
- Node exporters (hardware metrics)
- Application services via ServiceMonitors
- OpenTelemetry Collector

**Access**: `http://prometheus.local:9090`

### VictoriaMetrics

VictoriaMetrics serves as long-term storage for Prometheus metrics:
- Receives metrics via Prometheus `remote_write`
- 90-day retention period
- 50GB persistent storage
- PromQL-compatible queries

**Access**: `http://vm.local:8428`

**Query Example**:
```promql
# Query metrics from VictoriaMetrics
rate(container_cpu_usage_seconds_total[5m])
```

## Log Aggregation

### Loki

Loki aggregates logs from all cluster services:
- Receives logs from OpenTelemetry Collector via Loki push API
- 30-day retention period
- MinIO object storage backend (`loki-data` bucket)
- Label-based indexing (efficient storage)

The `loki-data` bucket is bootstrapped by `kubernetes/base-services/minio/bootstrap-buckets-job.yaml`.

**Access**: `http://loki.local:3100`

**Query Example (LogQL)**:
```logql
# Query logs from a specific namespace
{namespace="ml-platform"} |= "error"

# Query with time range
{namespace="ml-platform"} |= "error" | json | line_format "{{.message}}"
```

## Distributed Tracing

### Jaeger

Jaeger collects and visualizes distributed traces:
- Receives traces via OpenTelemetry Collector
- Persistent Badger storage (10GB)
- Integrated with Prometheus for Service Performance Monitoring
- Trace-to-metrics correlation

**Access**: `http://jaeger.local:16686`

**Features**:
- Service dependency graphs
- Trace timeline visualization
- Performance analysis
- Error tracking

## Unified Visualization

### Grafana

Grafana provides unified dashboards for all observability data:

**Data Sources**:
- Prometheus (short-term metrics)
- VictoriaMetrics (long-term metrics)
- Loki (logs)
- Jaeger (traces)

**Access**: `http://grafana.local:3000`  
**Default Credentials**: `admin` / `admin123`

**Pre-configured Dashboards**:
- k3s Cluster Overview
- Node Exporter Full
- MinIO Metrics
- Ray Metrics
- MLFlow Metrics
- Workflow Orchestrators - Argo and Dagster
- Flink Trading Pipeline
- Redis Overview (grafana.com #11835 - server-level Redis metrics)
- Redis Document Store (direct-query panels: FT.INFO, TS.RANGE, HGETALL)

**Data Source Plugins**:
- `redis-datasource` - installed via `grafana.plugins` in the Helm values so
  the Redis direct-query data source can render `TS.RANGE`, `FT.INFO`,
  `JSON.GET`, and `INFO` panels against the shared Redis 8 Stack.

## OpenTelemetry Collector

The OpenTelemetry Collector runs as a DaemonSet on all nodes and:
- Receives telemetry data via OTLP (gRPC/HTTP)
- Collects pod logs from node log files
- Processes and enriches telemetry
- Routes to appropriate backends:
  - **Traces** → Jaeger
  - **Metrics** → Prometheus + VictoriaMetrics
  - **Logs** → Loki

> Note: Prometheus/Grafana and Loki are deployed via Helm values in this repository.
> `kubectl apply -k kubernetes/` does not install those charts automatically.

## Service Integration

### Adding Service Monitoring

1. **Expose Metrics Endpoint**:
   ```python
   # Example: FastAPI service
   from prometheus_client import Counter, generate_latest
   
   request_count = Counter('requests_total', 'Total requests')
   
   @app.get("/metrics")
   def metrics():
       return Response(generate_latest(), media_type="text/plain")
   ```

2. **Create ServiceMonitor**:
   ```yaml
   apiVersion: monitoring.coreos.com/v1
   kind: ServiceMonitor
   metadata:
     name: my-service
     namespace: my-namespace
   spec:
     selector:
       matchLabels:
         app: my-service
     endpoints:
       - port: metrics
         interval: 30s
   ```

3. **Instrument with OpenTelemetry**:
   ```python
   from opentelemetry import trace
   from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
   from opentelemetry.sdk.trace import TracerProvider
   from opentelemetry.sdk.trace.export import BatchSpanProcessor
   
   trace.set_tracer_provider(TracerProvider())
   tracer = trace.get_tracer(__name__)
   
   otlp_exporter = OTLPSpanExporter(
       endpoint="otel-collector.observability:4317",
       insecure=True
   )
   trace.get_tracer_provider().add_span_processor(
       BatchSpanProcessor(otlp_exporter)
   )
   ```

### Flink and Kafka Tracing + Metrics

#### Kafka (Strimzi)

**Native tracing** is turned on in [`kafka-cluster.yaml`](../kubernetes/base-services/kafka/kafka-cluster.yaml)
via `spec.tracing.type=opentelemetry` plus `OTEL_*` env vars on the
`KafkaNodePool` pod template. The broker emits a span per produce / fetch
request so downstream Jaeger traces show the full path from producer ->
broker -> consumer.

**Kafka Connect** and **Kafka Bridge** also enable `spec.tracing.opentelemetry`
and auto-instrument SASL/SSL + schema-registry HTTP calls.

**Schema Registry (Apicurio)** exports traces via Quarkus's OTel integration
(`QUARKUS_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`) so the lookup during serde is
visible as a child span of the producing client's span.

#### Python + Java clients

All templates under [`templates/`](../templates/) attach auto-instrumentation:

- **Python** templates import `opentelemetry-instrumentation-confluent-kafka`
  and `opentelemetry-instrumentation-aiokafka` which wrap `produce()` and
  the consumer iterator. HTTPX calls into Apicurio are covered by the same
  auto-instrumentation so schema loads show up as child spans.
- **Java** templates ship with the OpenTelemetry Java Agent attached via
  `-javaagent:/opt/otel/opentelemetry-javaagent.jar`; the agent instruments
  Kafka clients, HTTP clients, and the JVM runtime without code changes.

#### Flink

- **PyFlink jobs** inherit `OTEL_EXPORTER_OTLP_ENDPOINT` from the shared
  [`flink-trading-config`](../kubernetes/base-services/flink/flink-configmap.yaml)
  ConfigMap.
- **Java Flink jobs** (`flink-jobs-java/`) take the same approach - the
  session cluster image can optionally be launched with the OTel Java Agent
  by uncommenting the `env.java.opts.all` entry in
  [`session-cluster.yaml`](../kubernetes/base-services/flink/session-cluster.yaml).
- **Metrics**: Apache Flink exposes JVM and job-level metrics via the
  Prometheus reporter on port 9249. A dedicated `ServiceMonitor` scrapes
  these from the `flink` namespace at 15-second intervals.

Key Flink metrics:
- `flink_jobmanager_numRunningJobs` -- active jobs
- `flink_taskmanager_job_task_numRecordsIn/Out` -- throughput
- `flink_jobmanager_job_lastCheckpointDuration` -- checkpoint health
- `flink_taskmanager_job_task_backPressuredTimeMsPerSecond` -- backpressure

The pre-provisioned **Flink Trading Pipeline** dashboard in Grafana visualizes all of these.

**Kafka (Strimzi)** exposes JMX metrics via the Prometheus JMX exporter configured in the Kafka cluster CR. A `ServiceMonitor` scrapes the Kafka broker pods in `data-services`.

Key Kafka metrics:
- `kafka_server_BrokerTopicMetrics_MessagesInPerSec` -- ingest rate
- `kafka_server_BrokerTopicMetrics_BytesInPerSec` / `BytesOutPerSec` -- throughput
- `kafka_server_ReplicaManager_UnderReplicatedPartitions` -- replication health

Both Flink and Kafka metrics flow through the existing pipeline: Prometheus scrape -> `remote_write` -> VictoriaMetrics (90-day retention).

#### Redis 8 Stack

The shared Redis 8 Stack deployment (`kubernetes/base-services/redis/`) is
observed through two complementary paths:

1. **`oliver006/redis_exporter`** (Prometheus) - a sidecar Deployment in
   `data-services` exposes `/metrics` on port 9121.  The
   `ServiceMonitor` at `kubernetes/base-services/redis/servicemonitor.yaml`
   is scraped every 30 s and provides classic counters:
   - `redis_commands_processed_total` - ops/sec
   - `redis_keyspace_hits_total`, `redis_keyspace_misses_total` - hit ratio
   - `redis_memory_used_bytes`, `redis_memory_max_bytes`
   - `redis_slowlog_length`, `redis_latest_fork_usec`
   - `redis_connected_clients`, `redis_blocked_clients`

2. **Grafana Redis data source** (`redis-datasource` plugin) - runs
   `TS.RANGE`, `FT.INFO`, `JSON.GET`, `HGETALL`, and other commands
   directly against Redis from the Grafana UI.  The **Redis Document
   Store** dashboard wires this up for the document pipeline:
   - `FT.INFO idx:documents` / `idx:chunks` for index size and indexing
     progress
   - `HGETALL stats:cache` for cache-aside hit/miss counters
   - `TS.RANGE stats:ingest:count` and `stats:semcache:latency` for
     time-series visualization of ingest and semantic-cache behavior

The OpenTelemetry Collector also carries a `redis` receiver as a
secondary metrics source; it uses the mirrored Redis password Secret
in the `observability` namespace
(`kubernetes/observability/otel-collector/redis-secret.yaml`).

**Latency and slowlog playbook**

The Redis ConfigMap sets `latency-monitor-threshold 10` and
`slowlog-log-slower-than 1000000` (microseconds) so operators can
triage slow commands without restarting:

```bash
# Latest latency spikes by event class
kubectl -n data-services exec deploy/redis -- \
  redis-cli -a "$REDIS_PASSWORD" LATENCY LATEST
kubectl -n data-services exec deploy/redis -- \
  redis-cli -a "$REDIS_PASSWORD" LATENCY HISTORY command

# Slowest commands (top 10)
kubectl -n data-services exec deploy/redis -- \
  redis-cli -a "$REDIS_PASSWORD" SLOWLOG GET 10

# Big / hot key scans (non-intrusive)
kubectl -n data-services exec deploy/redis -- \
  redis-cli -a "$REDIS_PASSWORD" --keystats
```

See [redis-stack.md](redis-stack.md) for the full operations guide.

## Querying and Analysis

### Correlating Metrics, Logs, and Traces

In Grafana, you can:

1. **Start with Metrics**: Identify performance issues
2. **Drill into Logs**: Find error messages
3. **View Traces**: Understand request flow

**Example Workflow**:
1. Notice high latency in Prometheus metrics
2. Query Loki for error logs during that time
3. View Jaeger traces to identify slow spans
4. Correlate all three to find root cause

## Retention and Storage

| Component | Retention | Storage |
|-----------|-----------|---------|
| Prometheus | 15 days | 20GB |
| VictoriaMetrics | 90 days | 50GB |
| Loki | 30 days | 20GB |
| Jaeger | 5 days | 10GB |
| Flink Checkpoints (MinIO) | Manual | flink-checkpoints bucket |
| Kafka Logs | 7 days | 20GB PVC |

## Troubleshooting

### Metrics Not Appearing

```bash
# Check Prometheus targets
kubectl port-forward -n observability svc/prometheus-prometheus 9090:9090
# Open http://localhost:9090/targets

# Check ServiceMonitor
kubectl get servicemonitor -A
```

### Logs Not Appearing in Loki

```bash
# Check OTel Collector logs
kubectl logs -n observability -l app=otel-collector

# Check Loki logs
kubectl logs -n observability -l app.kubernetes.io/name=loki
```

### Traces Not Appearing in Jaeger

```bash
# Check Jaeger collector
kubectl logs -n observability deployment/jaeger

# Verify OTel Collector export
kubectl logs -n observability -l app=otel-collector --tail=200
```

## Best Practices

1. **Use Structured Logging**: JSON format for better parsing
2. **Add Context to Traces**: Include user IDs, request IDs
3. **Set Appropriate Retention**: Adjust based on storage capacity
4. **Monitor the Observability Stack**: Watch resource usage
5. **Use Sampling for High-Volume Traces**: Configure in OTel Collector

## Additional Resources

- [Prometheus Querying](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [LogQL Documentation](https://grafana.com/docs/loki/latest/logql/)
- [Jaeger Documentation](https://www.jaegertracing.io/docs/)
- [OpenTelemetry Documentation](https://opentelemetry.io/docs/)
