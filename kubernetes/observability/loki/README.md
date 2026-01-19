# Loki - Log Aggregation System

Loki is a horizontally scalable, highly available log aggregation system inspired by Prometheus.

## Installation

```bash
# Add Grafana Helm repository
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# Install Loki
helm install loki grafana/loki \
  --namespace observability \
  --create-namespace \
  -f values.yaml
```

## Configuration

This deployment uses:
- **Single Binary Mode**: Appropriate for the RPi cluster size
- **Filesystem Storage**: 20GB PVC for log retention
- **30-day Retention**: Configurable in `values.yaml`
- **OTLP Gateway**: Enabled for OpenTelemetry log ingestion

## Access

After installation, Loki is accessible at:
- **Internal**: `http://loki.observability:3100`
- **External**: `http://loki.local` (via Ingress)

## Integration with Grafana

Loki is automatically configured as a datasource in Grafana. You can query logs using LogQL:

```logql
{namespace="ml-platform"} |= "error"
```

## OpenTelemetry Integration

The OpenTelemetry Collector is configured to export logs to Loki via OTLP. Logs from all services are automatically collected and forwarded to Loki.

## Retention

Logs are retained for 30 days by default. To adjust retention, modify the `retention_period` in `values.yaml`.
