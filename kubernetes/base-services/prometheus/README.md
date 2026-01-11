# Prometheus and Grafana

We recommend using the kube-prometheus-stack Helm chart for Prometheus and Grafana deployment.

## Installation

```bash
# Add Helm repository
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Install with custom values
helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace observability \
  --create-namespace \
  --values values.yaml
```

## values.yaml

```yaml
# Grafana configuration
grafana:
  enabled: true
  adminPassword: "admin123"  # Change in production!
  
  service:
    type: LoadBalancer
    port: 3000
  
  ingress:
    enabled: true
    ingressClassName: nginx
    hosts:
      - grafana.local
  
  # ARM64 compatible image
  image:
    repository: grafana/grafana
    tag: latest
  
  # Default dashboards
  dashboardProviders:
    dashboardproviders.yaml:
      apiVersion: 1
      providers:
        - name: 'default'
          orgId: 1
          folder: ''
          type: file
          disableDeletion: false
          editable: true
          options:
            path: /var/lib/grafana/dashboards/default
  
  dashboards:
    default:
      # k3s Cluster Dashboard
      k3s-cluster:
        gnetId: 15757
        revision: 1
        datasource: Prometheus
      # Node Exporter Full
      node-exporter:
        gnetId: 1860
        revision: 27
        datasource: Prometheus

# Prometheus configuration
prometheus:
  prometheusSpec:
    retention: 15d
    
    # Resource limits
    resources:
      requests:
        cpu: 200m
        memory: 512Mi
      limits:
        cpu: 1000m
        memory: 2Gi
    
    # Storage
    storageSpec:
      volumeClaimTemplate:
        spec:
          storageClassName: local-path
          accessModes: ["ReadWriteOnce"]
          resources:
            requests:
              storage: 20Gi
    
    # Service monitors
    serviceMonitorSelectorNilUsesHelmValues: false
    podMonitorSelectorNilUsesHelmValues: false

# AlertManager configuration
alertmanager:
  alertmanagerSpec:
    storage:
      volumeClaimTemplate:
        spec:
          storageClassName: local-path
          accessModes: ["ReadWriteOnce"]
          resources:
            requests:
              storage: 5Gi

# Node exporter
nodeExporter:
  enabled: true

# Kube-state-metrics
kubeStateMetrics:
  enabled: true

# Default rules
defaultRules:
  create: true
  rules:
    alertmanager: true
    etcd: true
    general: true
    k8s: true
    kubeApiserver: true
    kubePrometheusGeneral: true
    kubePrometheusNodeAlerting: true
    kubeScheduler: true
    kubeStateMetrics: true
    kubelet: true
    network: true
    node: true
    prometheus: true
```

## Accessing Services

After installation:

| Service | URL | Default Credentials |
|---------|-----|---------------------|
| Grafana | http://grafana.local:3000 | admin / admin123 |
| Prometheus | http://prometheus.local:9090 | - |
| Alertmanager | http://alertmanager.local:9093 | - |

## Pre-configured Dashboards

The following dashboards are automatically imported:
- **k3s Cluster Overview** (ID: 15757)
- **Node Exporter Full** (ID: 1860)

## Custom ServiceMonitors

To monitor additional services, create ServiceMonitor resources:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: my-service
  namespace: observability
spec:
  selector:
    matchLabels:
      app: my-service
  endpoints:
    - port: metrics
      interval: 30s
```

## Raspberry Pi Specific Metrics

To collect RPi-specific metrics (temperature, throttling), deploy node-exporter with textfile collector:

```yaml
nodeExporter:
  extraArgs:
    - --collector.textfile.directory=/host/textfile
  extraHostPathMounts:
    - name: textfile
      hostPath: /var/lib/node_exporter/textfile
      mountPath: /host/textfile
      readOnly: true
```

Then create a script on each RPi to write metrics:

```bash
#!/bin/bash
# /usr/local/bin/rpi-metrics.sh
OUTPUT="/var/lib/node_exporter/textfile/rpi.prom"

# Temperature
TEMP=$(vcgencmd measure_temp | grep -oP '\d+\.\d+')
echo "rpi_temperature_celsius $TEMP" > $OUTPUT

# Throttling
THROTTLE=$(vcgencmd get_throttled | grep -oP '0x\w+')
echo "rpi_throttled_state $((THROTTLE))" >> $OUTPUT
```

Add to crontab: `* * * * * /usr/local/bin/rpi-metrics.sh`
