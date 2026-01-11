# Raspberry Pi Kubernetes Cluster

A production-ready 4-node Raspberry Pi 5 Kubernetes (k3s) cluster with Ubuntu desktop as hybrid control plane, featuring a comprehensive management framework and pre-configured base services.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Control Plane                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Ubuntu Desktop (Control Plane + ML Workloads)                   │   │
│  │  - k3s server                                                    │   │
│  │  - GPU workloads (CUDA/ROCm)                                     │   │
│  │  - Heavy compute tasks                                           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────┬───────────┴───────────┬───────────────┐
        ▼               ▼                       ▼               ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│  RPi5 Node 1  │ │  RPi5 Node 2  │ │  RPi5 Node 3  │ │  RPi5 Node 4  │
│  8GB Worker   │ │  8GB Worker   │ │  8GB Worker   │ │  8GB Worker   │
│  ARM64        │ │  ARM64        │ │  ARM64        │ │  ARM64        │
└───────────────┘ └───────────────┘ └───────────────┘ └───────────────┘
```

## Features

- **k3s Kubernetes** - Lightweight, production-ready Kubernetes distribution
- **Base Services** - JupyterHub, MLFlow, MinIO, PostgreSQL, Prometheus, Grafana, Dask/Ray
- **Management Framework** - Python FastAPI backend + Next.js control panel
- **OpenTelemetry** - Distributed tracing and observability
- **Ansible Automation** - Reproducible cluster provisioning

## Quick Start

### Prerequisites

- 4x Raspberry Pi 5 (8GB RAM) with Raspberry Pi OS 64-bit
- 1x Ubuntu Desktop (22.04+) for control plane
- Gigabit Ethernet switch
- External USB SSDs for persistent storage (recommended)
- Ansible 2.15+ installed on your workstation

### 1. Configure Nodes

Edit the inventory file with your node IPs:

```bash
cp ansible/inventory/cluster.example.yml ansible/inventory/cluster.yml
# Edit cluster.yml with your node details
```

### 2. Bootstrap Nodes

```bash
# Prepare all nodes (disable swap, enable cgroups, etc.)
ansible-playbook -i ansible/inventory/cluster.yml ansible/playbooks/bootstrap.yml

# Setup external storage
ansible-playbook -i ansible/inventory/cluster.yml ansible/playbooks/storage-setup.yml
```

### 3. Install k3s Cluster

```bash
ansible-playbook -i ansible/inventory/cluster.yml ansible/playbooks/k3s-install.yml
```

### 4. Deploy Base Services

```bash
# Get kubeconfig from control plane
scp ubuntu@<control-plane-ip>:~/.kube/config ~/.kube/config-rpi-cluster

# Deploy services
kubectl apply -k kubernetes/
```

### 5. Access Services

| Service | URL | Default Credentials |
|---------|-----|---------------------|
| JupyterHub | http://jupyter.local | admin / admin |
| MLFlow | http://mlflow.local:5000 | - |
| Grafana | http://grafana.local:3000 | admin / prom-operator |
| MinIO Console | http://minio.local:9001 | minioadmin / minioadmin |
| Control Panel | http://control.local:8080 | - |

## Project Structure

```
rpi_kubernetes/
├── ansible/                    # Cluster provisioning
│   ├── inventory/              # Node definitions
│   ├── playbooks/              # Automation playbooks
│   └── roles/                  # Reusable roles
├── bootstrap/                  # Node setup scripts
│   ├── configs/                # Node configuration files
│   └── scripts/                # Setup scripts
├── kubernetes/                 # K8s manifests
│   ├── namespaces/             # Namespace definitions
│   ├── base-services/          # Core service deployments
│   └── observability/          # Monitoring stack
├── management/                 # Control panel
│   ├── backend/                # Python FastAPI
│   └── frontend/               # Next.js UI
└── docs/                       # Documentation
```

## Base Services

### Storage & Database
- **MinIO** - S3-compatible object storage for artifacts
- **PostgreSQL** - Relational database for MLFlow, JupyterHub

### Machine Learning
- **MLFlow** - Experiment tracking and model registry
- **JupyterHub** - Multi-user notebook environment
- **Dask** - Distributed computing framework
- **Ray** - ML distributed runtime

### Observability
- **Prometheus** - Metrics collection
- **Grafana** - Visualization and dashboards
- **Jaeger** - Distributed tracing
- **OpenTelemetry Collector** - Telemetry pipeline

## Management Framework

The control panel provides:
- Real-time cluster health monitoring
- Node hardware metrics (temperature, CPU, memory)
- One-click service deployment
- MLFlow experiment browser
- Log aggregation and viewing

## Hardware Recommendations

### Raspberry Pi 5 Nodes
- **RAM**: 8GB (minimum 4GB)
- **Storage**: 32GB+ SD card for boot, 256GB+ USB SSD for data
- **Cooling**: Active cooling recommended for sustained workloads
- **Power**: Official 27W USB-C power supply

### Ubuntu Desktop Control Plane
- **CPU**: Modern multi-core (Intel i5/i7 or AMD Ryzen)
- **RAM**: 16GB+ recommended
- **GPU**: NVIDIA GPU recommended for ML workloads
- **Storage**: 500GB+ SSD

## Extending the Framework

See [docs/extending-framework.md](docs/extending-framework.md) for:
- Adding custom services
- Creating deployment templates
- Plugin development
- CRD definitions

## Troubleshooting

### Common Issues

**Nodes not joining cluster:**
```bash
# Check k3s agent logs on worker
sudo journalctl -u k3s-agent -f
```

**Storage issues:**
```bash
# Verify external storage is mounted
df -h /mnt/storage
```

**Service not accessible:**
```bash
# Check pod status
kubectl get pods -A
# Check service endpoints
kubectl get endpoints -A
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Please read the contributing guidelines before submitting PRs.
