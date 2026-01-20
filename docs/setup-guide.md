# RPi Kubernetes Cluster - Setup Guide

This guide walks you through setting up your Raspberry Pi Kubernetes cluster from scratch.

## Prerequisites

### Hardware Requirements

- **4x Raspberry Pi 5** (8GB RAM recommended)
- **1x Ubuntu Desktop** (for control plane + ML workloads)
- **5x MicroSD cards** (32GB+ for boot)
- **4x USB SSDs** (256GB+ recommended for worker storage)
- **1x Gigabit Ethernet switch** (5+ ports)
- **5x Ethernet cables**
- **Power supplies** (official 27W for RPi5, standard for desktop)

### Software Requirements

On your **workstation** (not the cluster nodes):

```bash
# Install Ansible
pip install ansible ansible-lint

# Install kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl && sudo mv kubectl /usr/local/bin/

# Install Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Install Ansible collections
ansible-galaxy collection install kubernetes.core community.general ansible.posix
```

## Step 1: Prepare the Hardware

### 1.1 Flash Operating Systems

**For Raspberry Pi nodes:**
1. Download [Raspberry Pi OS Lite (64-bit)](https://www.raspberrypi.com/software/operating-systems/)
2. Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
3. Configure SSH, hostname, and WiFi (optional) in Imager settings
   - **Recommended**: Set username to `julian` in Imager to skip the prep step
   - See [docs/raspberry-pi-setup.md](raspberry-pi-setup.md#initial-sd-card-imaging) for detailed instructions
4. Flash to SD cards

> **Note**: If you used default Imager settings or already have Raspberry Pi OS flashed, you'll need to prepare the OS before bootstrapping. See [Preparing Existing OS Installations](raspberry-pi-setup.md#preparing-existing-os-installations) for instructions.

**For Ubuntu Desktop:**
1. Download [Ubuntu Desktop 22.04+](https://ubuntu.com/download/desktop)
2. Create bootable USB with [Balena Etcher](https://www.balena.io/etcher/)
3. Install Ubuntu on the desktop machine

### 1.2 Network Setup

1. Connect all nodes to the Gigabit switch
2. Connect switch to your router
3. Note the IP addresses assigned to each node

**Recommended IP Scheme:**
| Node | Hostname | IP Address |
|------|----------|------------|
| Ubuntu Desktop | k8s-control | 192.168.1.100 |
| RPi5 Node 1 | rpi1 | 192.168.1.101 |
| RPi5 Node 2 | rpi2 | 192.168.1.102 |
| RPi5 Node 3 | rpi3 | 192.168.1.103 |
| RPi5 Node 4 | rpi4 | 192.168.1.104 |

### 1.3 Connect External Storage

1. Connect USB SSDs to each Raspberry Pi
2. The bootstrap scripts will automatically partition and mount them

## Step 2: Configure Ansible Inventory

```bash
# Clone the repository
git clone https://github.com/your-repo/rpi_kubernetes.git
cd rpi_kubernetes

# Copy and edit inventory
cp ansible/inventory/cluster.example.yml ansible/inventory/cluster.yml
```

Edit `ansible/inventory/cluster.yml` with your actual IP addresses:

```yaml
all:
  vars:
    ansible_user: julian
    k3s_version: "v1.29.0+k3s1"
    
  children:
    control_plane:
      hosts:
        k8s-control:
          ansible_host: 192.168.1.100  # Your Ubuntu IP
          ansible_user: ubuntu
          
    workers:
      hosts:
        rpi1:
          ansible_host: 192.168.1.101  # Your RPi IPs
        rpi2:
          ansible_host: 192.168.1.102
        rpi3:
          ansible_host: 192.168.1.103
        rpi4:
          ansible_host: 192.168.1.104
```

## Step 3: Prepare Existing OS Installations (If Needed)

If you have Raspberry Pi OS already flashed **without** the `julian` user configured during imaging, you need to prepare the OS first.

**Option A: Automated (Windows Workstation)**

```powershell
# From your workstation
cd C:\Users\Julian Wiley\Documents\GitHub\rpi_kubernetes

.\bootstrap\scripts\port-to-rpi.ps1 `
    -Hosts @(
        "rpi1=192.168.1.101",
        "rpi2=192.168.1.102",
        "rpi3=192.168.1.103",
        "rpi4=192.168.1.104"
    ) `
    -AuthMethod "key" `
    -SshKey "~\.ssh\id_ed25519" `
    -DefaultUser "pi"

# Or with password authentication:
.\bootstrap\scripts\port-to-rpi.ps1 `
    -Hosts @(
        "rpi1=192.168.1.101",
        "rpi2=192.168.1.102",
        "rpi3=192.168.1.103",
        "rpi4=192.168.1.104"
    ) `
    -AuthMethod "password" `
    -DefaultUser "pi"
```

This script will create the `julian` user, install prerequisites, and copy the bootstrap scripts to each Pi.

**Option B: Manual**

```bash
# For each Pi, copy and run the prep script
scp bootstrap/scripts/prep-existing-os.sh pi@192.168.1.101:~/
ssh pi@192.168.1.101
sudo ./prep-existing-os.sh --hostname rpi1 --auth-method key --ssh-key ~/.ssh/id_ed25519.pub

# Or with password authentication:
sudo ./prep-existing-os.sh --hostname rpi1 --auth-method password
```

For detailed instructions, see [Preparing Existing OS Installations](raspberry-pi-setup.md#preparing-existing-os-installations).

## Step 4: Setup SSH Keys

```bash
# Generate SSH key if needed
ssh-keygen -t ed25519 -C "ansible@rpi-cluster"

# Copy to all nodes
ssh-copy-id ubuntu@192.168.1.100
ssh-copy-id julian@192.168.1.101
ssh-copy-id julian@192.168.1.102
ssh-copy-id julian@192.168.1.103
ssh-copy-id julian@192.168.1.104

# Test connectivity
ansible all -m ping -i ansible/inventory/cluster.yml
```

## Step 5: Bootstrap Nodes

### Option A: Windows-Native PowerShell (Recommended for Windows)

Use the PowerShell scripts to bootstrap nodes without Ansible:

**Method 1: Auto-discover and bootstrap all nodes**

```powershell
# Discover and bootstrap worker nodes
.\bootstrap\scripts\port-to-rpi.ps1 -Discover -RunBootstrap -AuthMethod "password"

# Then bootstrap control plane separately
.\bootstrap\scripts\bootstrap-cluster.ps1 -ControlPlane "ubuntu@192.168.1.100"
```

**Method 2: Manual node list with bootstrap**

```powershell
# Bootstrap worker nodes with auto-discovery
.\bootstrap\scripts\port-to-rpi.ps1 `
    -Discover `
    -RunBootstrap `
    -AuthMethod "password" `
    -NetworkRange "192.168.1.0/24"

# Or specify nodes manually
.\bootstrap\scripts\port-to-rpi.ps1 `
    -Hosts @("rpi1=192.168.1.101","rpi2=192.168.1.102","rpi3=192.168.1.103","rpi4=192.168.1.104") `
    -RunBootstrap `
    -AuthMethod "password"
```

**Method 3: Bootstrap control plane and workers together**

```powershell
.\bootstrap\scripts\bootstrap-cluster.ps1 `
    -ControlPlane "ubuntu@192.168.1.100" `
    -Workers @("julian@192.168.1.101","julian@192.168.1.102","julian@192.168.1.103","julian@192.168.1.104")
```

**Verify bootstrap completed:**

```powershell
.\bootstrap\scripts\diagnose-cluster.ps1 `
    -ControlPlane "ubuntu@192.168.1.100" `
    -Workers @("julian@192.168.1.101","julian@192.168.1.102","julian@192.168.1.103","julian@192.168.1.104")
```

### Option B: Ansible (Linux/Mac/WSL)

> **⚠️ Windows Users**: If you encounter `OSError: [WinError 1] Incorrect function` when running `ansible-playbook` on Windows, use Option A above or WSL.

```bash
# Run bootstrap playbook
ansible-playbook -i ansible/inventory/cluster.yml ansible/playbooks/bootstrap.yml

# Setup external storage on workers
ansible-playbook -i ansible/inventory/cluster.yml ansible/playbooks/storage-setup.yml

# Reboot all nodes to apply changes
ansible all -m reboot -i ansible/inventory/cluster.yml
```

**Wait for nodes to come back online (~2-3 minutes), then verify:**

```powershell
# PowerShell diagnostics
.\bootstrap\scripts\diagnose-cluster.ps1 -ControlPlane "ubuntu@192.168.1.100" -Workers @("julian@192.168.1.101","julian@192.168.1.102","julian@192.168.1.103","julian@192.168.1.104")

# Or manually check each node
ssh julian@192.168.1.101 "uname -m && free -h | grep Swap && cat /proc/cgroups | grep memory"
```

## Step 6: Install k3s Cluster

```bash
# Install k3s on all nodes
ansible-playbook -i ansible/inventory/cluster.yml ansible/playbooks/k3s-install.yml
```

This will:
1. Install k3s server on the control plane
2. Install k3s agent on all workers
3. Install MetalLB for load balancing
4. Install cert-manager for TLS

## Step 7: Configure kubectl

```bash
# Copy kubeconfig to your workstation
scp ubuntu@192.168.1.100:~/.kube/config ~/.kube/config-rpi-cluster

# Set KUBECONFIG
export KUBECONFIG=~/.kube/config-rpi-cluster

# Verify cluster
kubectl get nodes
```

Expected output:
```
NAME           STATUS   ROLES                  AGE   VERSION
k8s-control    Ready    control-plane,master   5m    v1.29.0+k3s1
rpi1           Ready    <none>                 4m    v1.29.0+k3s1
rpi2           Ready    <none>                 4m    v1.29.0+k3s1
rpi3           Ready    <none>                 4m    v1.29.0+k3s1
rpi4           Ready    <none>                 4m    v1.29.0+k3s1
```

## Step 8: Deploy Base Services

### 7.1 Deploy Core Services

```bash
# Deploy namespaces and base services
kubectl apply -k kubernetes/
```

### 7.2 Deploy Observability Stack

```bash
# Add Helm repos
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# Install Prometheus/Grafana
helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace observability \
  --create-namespace \
  -f kubernetes/base-services/prometheus/values.yaml

# Deploy VictoriaMetrics (via Kustomize)
kubectl apply -k kubernetes/observability/victoriametrics/

# Install Loki
helm install loki grafana/loki \
  --namespace observability \
  -f kubernetes/observability/loki/values.yaml
```

### 7.3 Deploy MLOps Services

```bash
# Add Helm repos
helm repo add kuberay https://ray-project.github.io/kuberay-helm/
helm repo add milvus https://milvus-io.github.io/milvus-helm
helm repo add argo https://argoproj.github.io/argo-helm
helm repo add bentoml https://bentoml.github.io/yatai-chart
helm repo update

# Deploy KubeRay Operator (for Ray)
helm install kuberay-operator kuberay/kuberay-operator --namespace ml-platform

# Deploy Milvus
helm install milvus milvus/milvus \
  --namespace data-services \
  -f kubernetes/base-services/milvus/values.yaml

# Deploy Argo Workflows
helm install argo-workflows argo/argo-workflows \
  --namespace mlops \
  --create-namespace \
  -f kubernetes/mlops/argo-workflows/values.yaml
kubectl apply -f kubernetes/mlops/argo-workflows/secret.yaml

# Deploy BentoML/Yatai
helm install yatai bentoml/yatai \
  --namespace ml-platform \
  -f kubernetes/mlops/bentoml/values.yaml
kubectl apply -f kubernetes/mlops/bentoml/secret.yaml
```

## Step 9: Configure Local DNS (Optional)

Add entries to your workstation's `/etc/hosts`:

```bash
# Get MetalLB IPs
kubectl get svc -A | grep LoadBalancer

# Add to /etc/hosts (use actual IPs from above)
192.168.1.200  grafana.local
192.168.1.201  mlflow.local
192.168.1.202  jupyter.local
192.168.1.203  minio.local
192.168.1.204  jaeger.local

# Ingress hosts (control.local, etc.) use the ingress-nginx LoadBalancer IP
kubectl -n ingress get svc ingress-nginx-controller
192.168.1.205  control.local
```

## Step 10: Access Services

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | http://grafana.local:3000 | admin / admin123 |
| Prometheus | http://prometheus.local:9090 | - |
| VictoriaMetrics | http://vm.local:8428 | - |
| Loki | http://loki.local:3100 | - |
| Jaeger | http://jaeger.local:16686 | - |
| MLFlow | http://mlflow.local:5000 | - |
| JupyterHub | http://jupyter.local | admin / jupyter |
| Argo Workflows | http://argo.local:2746 | - |
| ChromaDB | http://chromadb.local:8000 | - |
| Milvus | http://milvus.local:19530 | - |
| BentoML/Yatai | http://yatai.local:3000 | - |
| MinIO | http://minio.local:9001 | minioadmin / minioadmin123 |
| Control Panel | http://control.local | - |

Control panel access options:
- Ingress: `http://control.local` (hosts entry required)
- LoadBalancer: `http://<management-ui-external-ip>`
- NodePort: `http://<node-ip>:30080`

## Step 11: Deploy Management Control Panel

```bash
# Build and deploy backend
cd management/backend
docker build -t rpi-k8s-management:latest .

# Build and deploy frontend
cd ../frontend
docker build -t rpi-k8s-control-panel:latest .

# Deploy to cluster
kubectl apply -f kubernetes/management/
```

## Troubleshooting

### Nodes not joining cluster

```bash
# Check k3s agent logs on worker
ssh julian@192.168.1.101 "sudo journalctl -u k3s-agent -f"

# Verify token
ssh ubuntu@192.168.1.100 "sudo cat /var/lib/rancher/k3s/server/node-token"
```

### Pods stuck in Pending

```bash
# Check events
kubectl describe pod <pod-name> -n <namespace>

# Check node resources
kubectl describe nodes | grep -A 5 "Allocated resources"
```

### Storage issues

```bash
# Verify external storage on workers
ansible workers -a "df -h /mnt/storage" -i ansible/inventory/cluster.yml

# Check PVCs
kubectl get pvc -A
```

### Service not accessible

```bash
# Check LoadBalancer IP assignment
kubectl get svc -A | grep LoadBalancer

# Check MetalLB
kubectl logs -n metallb-system -l app=metallb
```

## Next Steps

1. **Explore JupyterHub**: Create notebooks and connect to MLFlow
2. **Configure Grafana dashboards**: Import additional dashboards
3. **Deploy your applications**: Use the deployment API or kubectl
4. **Scale workers**: Add more Raspberry Pi nodes as needed

See [extending-framework.md](extending-framework.md) for advanced configuration.
