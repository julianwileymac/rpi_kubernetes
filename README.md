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
- **Base Services** - JupyterHub, MLFlow, MinIO, PostgreSQL, Prometheus, Grafana, Dask/Ray, ChromaDB, Milvus
- **Management Framework** - Python FastAPI backend + Next.js control panel
- **OpenTelemetry** - Distributed tracing and observability
- **Ansible Automation** - Reproducible cluster provisioning

## Quick Start

> **First Time?** See the [Detailed Raspberry Pi Setup Guide](docs/raspberry-pi-setup.md) for step-by-step instructions on imaging SD cards, first boot configuration, and troubleshooting.

### Prerequisites

**Hardware:**
- 4x Raspberry Pi 5 (8GB RAM recommended)
- 1x Ubuntu Desktop (22.04+) for control plane
- Gigabit Ethernet switch
- External USB SSDs for persistent storage (one per node)
- MicroSD cards (32GB+ Class 10/A2)
- Official 27W USB-C power supplies

**Software (on your workstation):**
- [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
- SSH client (built-in on Mac/Linux, Windows Terminal on Windows)
- Ansible 2.15+ (`pip install ansible`)
- kubectl (`brew install kubectl` or [install guide](https://kubernetes.io/docs/tasks/tools/))

### Step 1: Image SD Cards

Use Raspberry Pi Imager to flash **Raspberry Pi OS Lite (64-bit)** to each SD card.

For each node, configure in Imager's advanced settings (gear icon):
- **Hostname**: `rpi1`, `rpi2`, `rpi3`, `rpi4`
- **Enable SSH**: Yes (with public key authentication)
- **Username/Password**: `julian` / your-password
- **Timezone**: Your timezone

See [docs/raspberry-pi-setup.md](docs/raspberry-pi-setup.md) for detailed imaging instructions.

### Step 2: First Boot & Network Setup

1. Insert SD card, connect USB SSD, Ethernet, then power
2. Wait 1-2 minutes for boot
3. Find the IP address via router or `nmap -sn 192.168.1.0/24`
4. Test SSH: `ssh julian@<ip-address>`

**Recommended Static IPs:**

| Node | Hostname | IP Address |
|------|----------|------------|
| Control Plane | k8s-control | 192.168.1.100 |
| Worker 1 | rpi1 | 192.168.1.101 |
| Worker 2 | rpi2 | 192.168.1.102 |
| Worker 3 | rpi3 | 192.168.1.103 |
| Worker 4 | rpi4 | 192.168.1.104 |

### Step 3: Configure Ansible Inventory

```bash
# Clone the repository
git clone https://github.com/your-repo/rpi_kubernetes.git
cd rpi_kubernetes

# Copy and edit inventory with your node IPs
cp ansible/inventory/cluster.example.yml ansible/inventory/cluster.yml
nano ansible/inventory/cluster.yml
```

### Step 4: Bootstrap All Nodes

**Windows Users - PowerShell (Recommended):**

```powershell
# Auto-discover and bootstrap all nodes
.\bootstrap\scripts\port-to-rpi.ps1 -Discover -RunBootstrap -AuthMethod "password"

# Bootstrap control plane
.\bootstrap\scripts\bootstrap-cluster.ps1 -ControlPlane "ubuntu@192.168.1.100"

# Verify with diagnostics
.\bootstrap\scripts\diagnose-cluster.ps1 `
    -ControlPlane "ubuntu@192.168.1.100" `
    -Workers @("julian@192.168.1.101","julian@192.168.1.102","julian@192.168.1.103","julian@192.168.1.104")
```

**Linux/Mac/WSL Users - Ansible:**

```bash
# Prepare all nodes (disable swap, enable cgroups, configure storage)
ansible-playbook -i ansible/inventory/cluster.yml ansible/playbooks/bootstrap.yml

# Nodes will reboot automatically
# Wait 2-3 minutes, then verify:
ansible all -i ansible/inventory/cluster.yml -m ping
```

The bootstrap process:
- Disables swap (required by Kubernetes)
- Enables memory cgroups in kernel
- Installs required packages
- Configures external USB storage (auto-detects and mounts USB drives)
- Sets up firewall rules
- Installs systemd service for automatic drive mounting on boot

### Step 5: Install k3s Cluster

```bash
# Install k3s server on control plane and agents on workers
ansible-playbook -i ansible/inventory/cluster.yml ansible/playbooks/k3s-install.yml
```

### Step 6: Configure kubectl

```bash
# Get kubeconfig from control plane
scp ubuntu@192.168.1.100:~/.kube/config ~/.kube/config-rpi-cluster

# Set as default or use with flag
export KUBECONFIG=~/.kube/config-rpi-cluster

# Verify cluster access
kubectl get nodes
```

### Step 7: Deploy Base Services

```bash
# Deploy all base services via Kustomize
kubectl apply -k kubernetes/

# Wait for services to be ready
kubectl wait --for=condition=available --timeout=300s deployment/management-ui -n management
kubectl wait --for=condition=available --timeout=300s deployment/minio -n data-services

# Verify services are accessible
./bootstrap/scripts/verify-control-panel.sh
./bootstrap/scripts/verify-minio.sh
```

### Step 8: Access Services

Add these entries to your workstation's hosts file (`/etc/hosts` or `C:\Windows\System32\drivers\etc\hosts`),
using the ingress-nginx LoadBalancer IP (`kubectl -n ingress get svc ingress-nginx-controller`):

```
192.168.1.200  jupyter.local mlflow.local grafana.local minio.local control.local \
               prometheus.local vm.local loki.local jaeger.local argo.local \
               chromadb.local milvus.local yatai.local
```

| Service | URL | Default Credentials |
|---------|-----|---------------------|
| JupyterHub | http://jupyter.local | admin / admin |
| MLFlow | http://mlflow.local:5000 | - |
| Grafana | http://grafana.local:3000 | admin / admin123 |
| Prometheus | http://prometheus.local:9090 | - |
| VictoriaMetrics | http://vm.local:8428 | - |
| Loki | http://loki.local:3100 | - |
| Jaeger | http://jaeger.local:16686 | - |
| Argo Workflows | http://argo.local:2746 | - |
| ChromaDB | http://chromadb.local:8000 | - |
| Milvus | http://milvus.local:19530 | - |
| BentoML/Yatai | http://yatai.local:3000 | - |
| MinIO Console | http://minio.local:9001 | minioadmin / minioadmin |
| Control Panel | http://control.local | - |

Control panel access options:
- Ingress: `http://control.local` (hosts entry required)
- LoadBalancer: `http://<management-ui-external-ip>`
- NodePort: `http://<node-ip>:30080`

### Reimaging a Node

If you need to reimage a faulty or misconfigured node, see the [Reimaging Guide](docs/raspberry-pi-setup.md#reimaging-a-node) which covers:
- Draining and removing the node from the cluster
- Backing up data from external storage
- Reimaging the SD card
- Rejoining the cluster

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
- **MLFlow** - Experiment tracking and model registry (PostgreSQL backend)
- **JupyterHub** - Multi-user notebook environment
- **Dask** - Distributed computing framework
- **Ray** - ML distributed runtime
- **ChromaDB** - Lightweight vector database for development
- **Milvus** - Production-grade vector database

### Observability
- **Prometheus** - Metrics collection
- **Grafana** - Visualization and dashboards
- **VictoriaMetrics** - Long-term metrics storage
- **Loki** - Log aggregation
- **Jaeger** - Distributed tracing
- **OpenTelemetry Collector** - Unified telemetry pipeline

### MLOps
- **Argo Workflows** - ML pipeline orchestration
- **BentoML / Yatai** - Model serving platform

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

# Check mount service status
sudo systemctl status mount-external-drive.service

# View mount service logs
sudo journalctl -u mount-external-drive.service -f

# Manually mount external drive (if needed)
sudo /usr/local/bin/mount-external-drive.sh --verbose

# Or use local script for ad-hoc mounting
sudo ./bootstrap/scripts/mount-drive-local.sh --verbose
```

**External drive not auto-mounting:**
```bash
# Check if systemd service is enabled
sudo systemctl is-enabled mount-external-drive.service

# Enable and start the service
sudo systemctl enable mount-external-drive.service
sudo systemctl start mount-external-drive.service

# Check service logs for errors
sudo journalctl -u mount-external-drive.service -n 50
```

**Control Panel not accessible:**
```bash
# Verify control panel deployment and accessibility
./bootstrap/scripts/verify-control-panel.sh

# Check ingress controller status
kubectl get pods -n ingress
kubectl get svc -n ingress ingress-nginx-controller

# Check ingress resource
kubectl get ingress -n management management-ui

# Verify DNS/hosts file entry
# Add to /etc/hosts (or C:\Windows\System32\drivers\etc\hosts):
# <ingress-ip>  control.local

# Access via LoadBalancer (if ingress not working)
kubectl get svc -n management management-ui-external
# Then access: http://<loadbalancer-ip>:8080
```

**Minio endpoint not accessible:**
```bash
# Verify Minio health and accessibility
./bootstrap/scripts/verify-minio.sh

# Check Minio pod status
kubectl get pods -n data-services -l app=minio

# Test health endpoints directly
kubectl exec -n data-services <minio-pod-name> -- curl http://localhost:9000/minio/health/live
kubectl exec -n data-services <minio-pod-name> -- curl http://localhost:9000/minio/health/ready

# Check Minio services
kubectl get svc -n data-services minio
kubectl get svc -n data-services minio-external

# Access via LoadBalancer
kubectl get svc -n data-services minio-external
# Console: http://<loadbalancer-ip>:9001
# API: http://<loadbalancer-ip>:9000
```

**Service not accessible:**
```bash
# Check pod status
kubectl get pods -A
# Check service endpoints
kubectl get endpoints -A

# Check ingress resources
kubectl get ingress -A

# Verify ingress controller
kubectl get pods -n ingress
kubectl get svc -n ingress ingress-nginx-controller
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Please read the contributing guidelines before submitting PRs.
