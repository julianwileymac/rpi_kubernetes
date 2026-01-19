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
- Receives logs via OpenTelemetry Collector (OTLP)
- 30-day retention period
- 20GB persistent storage
- Label-based indexing (efficient storage)

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

## OpenTelemetry Collector

The OpenTelemetry Collector runs as a DaemonSet on all nodes and:
- Receives telemetry data via OTLP (gRPC/HTTP)
- Processes and enriches telemetry
- Routes to appropriate backends:
  - **Traces** → Jaeger
  - **Metrics** → Prometheus + VictoriaMetrics
  - **Logs** → Loki

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

## Troubleshooting

### Metrics Not Appearing

```bash
# Check Prometheus targets
kubectl port-forward -n observability svc/prometheus-kube-prometheus-prometheus 9090:9090
# Open http://localhost:9090/targets

# Check ServiceMonitor
kubectl get servicemonitor -A
```

### Logs Not Appearing in Loki

```bash
# Check OTel Collector logs
kubectl logs -n observability -l app=otel-collector

# Check Loki logs
kubectl logs -n observability -l app=loki
```

### Traces Not Appearing in Jaeger

```bash
# Check Jaeger collector
kubectl logs -n observability deployment/jaeger

# Verify OTel Collector export
kubectl logs -n observability -l app=otel-collector | grep jaeger
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
