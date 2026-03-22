# Prometheus and Grafana (kube-prometheus-stack)

**Configuration for this stack lives in** [kubernetes/observability/prometheus/values.yaml](../observability/prometheus/values.yaml).  
This directory no longer duplicates `values.yaml` so edits stay in one place.

## Install

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Install or upgrade with custom values
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
  --namespace observability \
  --create-namespace \
  -f kubernetes/observability/prometheus/values.yaml
```

ServiceMonitors applied via Kustomize: [kubernetes/observability/prometheus/](../observability/prometheus/).

For VictoriaMetrics integration and access URLs, see the previous content in git history or [docs/setup-guide.md](../../../docs/setup-guide.md) (Step 7.2).
