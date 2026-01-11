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
4. Flash to SD cards

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
| RPi5 Node 1 | rpi5-node-1 | 192.168.1.101 |
| RPi5 Node 2 | rpi5-node-2 | 192.168.1.102 |
| RPi5 Node 3 | rpi5-node-3 | 192.168.1.103 |
| RPi5 Node 4 | rpi5-node-4 | 192.168.1.104 |

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
    ansible_user: pi
    k3s_version: "v1.29.0+k3s1"
    
  children:
    control_plane:
      hosts:
        k8s-control:
          ansible_host: 192.168.1.100  # Your Ubuntu IP
          ansible_user: ubuntu
          
    workers:
      hosts:
        rpi5-node-1:
          ansible_host: 192.168.1.101  # Your RPi IPs
        rpi5-node-2:
          ansible_host: 192.168.1.102
        rpi5-node-3:
          ansible_host: 192.168.1.103
        rpi5-node-4:
          ansible_host: 192.168.1.104
```

## Step 3: Setup SSH Keys

```bash
# Generate SSH key if needed
ssh-keygen -t ed25519 -C "ansible@rpi-cluster"

# Copy to all nodes
ssh-copy-id ubuntu@192.168.1.100
ssh-copy-id pi@192.168.1.101
ssh-copy-id pi@192.168.1.102
ssh-copy-id pi@192.168.1.103
ssh-copy-id pi@192.168.1.104

# Test connectivity
ansible all -m ping -i ansible/inventory/cluster.yml
```

## Step 4: Bootstrap Nodes

```bash
# Run bootstrap playbook
ansible-playbook -i ansible/inventory/cluster.yml ansible/playbooks/bootstrap.yml

# Setup external storage on workers
ansible-playbook -i ansible/inventory/cluster.yml ansible/playbooks/storage-setup.yml

# Reboot all nodes to apply changes
ansible all -m reboot -i ansible/inventory/cluster.yml
```

Wait for nodes to come back online (~2-3 minutes).

## Step 5: Install k3s Cluster

```bash
# Install k3s on all nodes
ansible-playbook -i ansible/inventory/cluster.yml ansible/playbooks/k3s-install.yml
```

This will:
1. Install k3s server on the control plane
2. Install k3s agent on all workers
3. Install MetalLB for load balancing
4. Install cert-manager for TLS

## Step 6: Configure kubectl

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
rpi5-node-1    Ready    <none>                 4m    v1.29.0+k3s1
rpi5-node-2    Ready    <none>                 4m    v1.29.0+k3s1
rpi5-node-3    Ready    <none>                 4m    v1.29.0+k3s1
rpi5-node-4    Ready    <none>                 4m    v1.29.0+k3s1
```

## Step 7: Deploy Base Services

### 7.1 Deploy Core Services

```bash
# Deploy namespaces and base services
kubectl apply -k kubernetes/
```

### 7.2 Deploy Prometheus/Grafana

```bash
# Add Helm repo
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Install with our values
helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace observability \
  --create-namespace \
  -f kubernetes/base-services/prometheus/values.yaml
```

### 7.3 Deploy KubeRay Operator (for Ray)

```bash
helm repo add kuberay https://ray-project.github.io/kuberay-helm/
helm install kuberay-operator kuberay/kuberay-operator --namespace ml-platform
```

## Step 8: Configure Local DNS (Optional)

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
```

## Step 9: Access Services

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | http://grafana.local:3000 | admin / admin123 |
| MLFlow | http://mlflow.local:5000 | - |
| JupyterHub | http://jupyter.local | admin / jupyter |
| MinIO | http://minio.local:9001 | minioadmin / minioadmin123 |
| Jaeger | http://jaeger.local:16686 | - |
| Control Panel | http://control.local:8080 | - |

## Step 10: Deploy Management Control Panel

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
ssh pi@192.168.1.101 "sudo journalctl -u k3s-agent -f"

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
