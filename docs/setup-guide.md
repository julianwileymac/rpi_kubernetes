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
3. Nodes will be discoverable via mDNS (hostname.local) after bootstrap

**mDNS Discovery (Recommended - No Static IPs Required):**

After bootstrapping, nodes are accessible by hostname without knowing their IP:

| Node | Hostname | mDNS Address |
|------|----------|--------------|
| Ubuntu Desktop | k8s-control | k8s-control.local |
| RPi5 Node 1 | rpi1 | rpi1.local |
| RPi5 Node 2 | rpi2 | rpi2.local |
| RPi5 Node 3 | rpi3 | rpi3.local |
| RPi5 Node 4 | rpi4 | rpi4.local |

```bash
# After bootstrap, connect using mDNS hostname
ssh julian@rpi1.local
ping k8s-control.local
```

**Alternative: Static IP Reservation**

If your router supports DHCP reservation, you can assign static IPs based on MAC address. This is optional with mDNS discovery enabled.

### 1.3 Connect External Storage

1. Connect USB SSDs to each Raspberry Pi (one or more per node)
2. The auto-mount playbook will detect, partition, format, and mount **every** external drive
3. Each drive is exposed to Kubernetes as a PersistentVolume automatically

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

**Option A: Automated with Discovery (Windows Workstation - Recommended)**

```powershell
# From your workstation
cd C:\Users\Julian Wiley\Documents\GitHub\rpi_kubernetes

# Auto-discover nodes and prepare them (no IP addresses needed)
.\bootstrap\scripts\port-to-rpi.ps1 -Discover -AuthMethod "password" -DefaultUser "pi"

# Or use mDNS hostnames directly
.\bootstrap\scripts\port-to-rpi.ps1 -UseMDNS -Hostnames "rpi1,rpi2,rpi3,rpi4" -AuthMethod "password"
```

**Option B: Manual with IP addresses (Windows Workstation)**

```powershell
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

# Auto-mount all external drives and create Kubernetes PVs
ansible-playbook -i ansible/inventory/cluster.yml ansible/playbooks/auto-mount-storage.yml

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

This applies MinIO and a bucket bootstrap Job that creates:
`mlflow-artifacts`, `argo-workflows`, `bentoml-artifacts`, `dagster-artifacts`,
`milvus-bucket`, and `loki-data`.

If Argo CRDs are not installed yet, apply the MLOps Helm releases in Step 7.3 first,
then re-run `kubectl apply -k kubernetes/` (or specifically `kubernetes/mlops/pipelines/`).

### 7.2 Deploy Observability Stack

```bash
# Add Helm repos
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# Install or upgrade Prometheus/Grafana
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
  --namespace observability \
  --create-namespace \
  -f kubernetes/base-services/prometheus/values.yaml

# Deploy VictoriaMetrics (via Kustomize)
kubectl apply -k kubernetes/observability/victoriametrics/

# Create/refresh Loki MinIO credentials
kubectl apply -f kubernetes/observability/loki/minio-secret.yaml

# Install or upgrade Loki
helm upgrade --install loki grafana/loki \
  --namespace observability \
  --create-namespace \
  -f kubernetes/observability/loki/values.yaml
```

### 7.2.1 Verify Ingress and Telemetry Prerequisites

```bash
# Ensure ingress controller exists for *.local hosts
kubectl -n ingress get svc ingress-nginx-controller
kubectl get ingressclass nginx

# Ensure LoadBalancer allocator exists (bare-metal clusters)
kubectl -n metallb-system get pods

# Verify telemetry backends and collector
kubectl -n observability get deploy jaeger
kubectl -n observability get ds otel-collector
kubectl -n observability get statefulset,deploy | grep loki
```

### 7.3 Deploy MLOps Services

```bash
# Add Helm repos
helm repo add kuberay https://ray-project.github.io/kuberay-helm/
helm repo add milvus https://milvus-io.github.io/milvus-helm
helm repo add argo https://argoproj.github.io/argo-helm
helm repo add bentoml https://bentoml.github.io/yatai-chart
helm repo add dagster https://dagster-io.github.io/helm
helm repo update

# Deploy KubeRay Operator (for Ray)
helm upgrade --install kuberay-operator kuberay/kuberay-operator --namespace ml-platform

# Ensure Milvus MinIO credentials are applied
kubectl apply -f kubernetes/base-services/milvus/secret.yaml

# Deploy Milvus
helm upgrade --install milvus milvus/milvus \
  --namespace data-services \
  -f kubernetes/base-services/milvus/values.yaml \
  --set externalS3.host="$(kubectl get secret -n data-services milvus-minio -o jsonpath='{.data.host}' | base64 -d)" \
  --set externalS3.port="$(kubectl get secret -n data-services milvus-minio -o jsonpath='{.data.port}' | base64 -d)" \
  --set externalS3.accessKey="$(kubectl get secret -n data-services milvus-minio -o jsonpath='{.data.accesskey}' | base64 -d)" \
  --set externalS3.secretKey="$(kubectl get secret -n data-services milvus-minio -o jsonpath='{.data.secretkey}' | base64 -d)" \
  --set externalS3.bucketName="$(kubectl get secret -n data-services milvus-minio -o jsonpath='{.data.bucket}' | base64 -d)"

# Ensure Argo MinIO credentials are applied
kubectl apply -f kubernetes/mlops/argo-workflows/secret.yaml

# Deploy Argo Workflows
helm upgrade --install argo-workflows argo/argo-workflows \
  --namespace mlops \
  --create-namespace \
  -f kubernetes/mlops/argo-workflows/values.yaml

# Deploy Argo Events CRDs/controller to satisfy Sensor/EventSource API discovery
helm upgrade --install argo-events argo/argo-events \
  --namespace mlops \
  --create-namespace \
  -f kubernetes/mlops/argo-events/values.yaml

# Create default EventBus in mlops namespace
kubectl apply -k kubernetes/mlops/argo-events/

# Ensure Dagster baseline secret/config are applied
kubectl apply -k kubernetes/mlops/dagster/

# Deploy Dagster
helm upgrade --install dagster dagster/dagster \
  --namespace mlops \
  --create-namespace \
  -f kubernetes/mlops/dagster/values.yaml \
  --set postgresql.postgresqlHost="$(kubectl get secret -n mlops dagster-postgresql -o jsonpath='{.data.host}' | base64 -d)" \
  --set postgresql.service.port="$(kubectl get secret -n mlops dagster-postgresql -o jsonpath='{.data.port}' | base64 -d)" \
  --set postgresql.postgresqlDatabase="$(kubectl get secret -n mlops dagster-postgresql -o jsonpath='{.data.database}' | base64 -d)" \
  --set postgresql.postgresqlUsername="$(kubectl get secret -n mlops dagster-postgresql -o jsonpath='{.data.user}' | base64 -d)" \
  --set postgresql.postgresqlPassword="$(kubectl get secret -n mlops dagster-postgresql -o jsonpath='{.data.password}' | base64 -d)"

# Wait for Dagster webserver to become ready
kubectl rollout status deployment/dagster-dagster-webserver -n mlops --timeout=240s

# Optional: build and push pipeline runtime image, then enable Dagster user-code deployment
# (default install uses a lightweight example user-code location for reliable reachability)
docker build -f pipelines/Dockerfile -t ghcr.io/julianwiley/rpi-k8s-pipelines:latest .
docker push ghcr.io/julianwiley/rpi-k8s-pipelines:latest
helm upgrade --install dagster dagster/dagster \
  --namespace mlops \
  --create-namespace \
  -f kubernetes/mlops/dagster/values.yaml \
  -f kubernetes/mlops/dagster/values-pipelines-user-code.yaml

# Apply Argo + Dagster pipeline recipes and bootstrap state tables
kubectl apply -k kubernetes/mlops/pipelines/

# See docs/data-pipeline-recipes.md for first-run commands for all five recipes

# Ensure BentoML PostgreSQL and MinIO credentials are applied
kubectl apply -f kubernetes/mlops/bentoml/secret.yaml

# Deploy BentoML/Yatai
helm upgrade --install yatai bentoml/yatai \
  --namespace ml-platform \
  -f kubernetes/mlops/bentoml/values.yaml \
  --set yatai.minio.external.endpoint="$(kubectl get secret -n ml-platform yatai-minio -o jsonpath='{.data.endpoint}' | base64 -d)" \
  --set yatai.minio.external.accessKey="$(kubectl get secret -n ml-platform yatai-minio -o jsonpath='{.data.accesskey}' | base64 -d)" \
  --set yatai.minio.external.secretKey="$(kubectl get secret -n ml-platform yatai-minio -o jsonpath='{.data.secretkey}' | base64 -d)" \
  --set yatai.minio.external.bucket="$(kubectl get secret -n ml-platform yatai-minio -o jsonpath='{.data.bucket}' | base64 -d)"
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
192.168.1.205  control.local argo.local dagster.local yatai.local
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
| Argo Workflows | http://argo.local | - |
| Dagster | http://dagster.local | - |
| ChromaDB | http://chromadb.local:8000 | - |
| Milvus | http://milvus.local:19530 | - |
| BentoML/Yatai | http://yatai.local:3000 | - |
| MinIO | http://minio.local:9001 | minioadmin / minioadmin123 |
| Control Panel | http://control.local | - |

### 10.1 Verify Argo and Dagster Telemetry

```bash
# Confirm ServiceMonitors are present
kubectl get servicemonitor -n observability | grep -E "argo|dagster"

# Check Prometheus scrape targets
kubectl port-forward -n observability svc/prometheus-prometheus 9090:9090
# Open http://127.0.0.1:9090/targets and verify Argo/Dagster targets are UP

# Check OTLP telemetry path from Dagster webserver
kubectl logs -n mlops deploy/dagster-dagster-webserver --tail=200
# (Daemon logs are available when using values-pipelines-user-code.yaml)
```

In Grafana, open the pre-provisioned dashboard:
`Workflow Orchestrators - Argo and Dagster`.

### 10.2 Verify Pipeline Orchestrators End-to-End

```bash
# Verify Argo Events CRDs and default EventBus
kubectl get crd sensors.argoproj.io eventsources.argoproj.io eventbus.argoproj.io
kubectl get eventbus -n mlops

# Verify workflow templates and schedules are installed
kubectl get workflowtemplate -n mlops
kubectl get cronworkflow -n mlops

# Submit a raw ingest run
argo submit --from workflowtemplate/pipeline-raw-ingest -n mlops \
  -p source_type=http \
  -p source_name=sample-http \
  -p source_uri=https://example.com/data.json

# Submit a CDC run
argo submit --from workflowtemplate/pipeline-cdc-sync -n mlops \
  -p pipeline_name=cdc-source-events \
  -p source_table=source_events

# Check Dagster core components
kubectl get deploy -n mlops | grep dagster
kubectl logs -n mlops deploy/dagster-dagster-webserver --tail=200

# Confirm Argo server no longer reports Sensor/EventSource "NotFound" errors
kubectl logs -n mlops deploy/argo-workflows-server --tail=200 | grep -E "sensors.argoproj.io|eventsources.argoproj.io" || true

# Verify state tables exist in PostgreSQL
kubectl exec -n data-services deploy/postgresql -- psql -U postgres -d dagster -c "\dt pipeline_*"
```

### 10.3 Verify DataHub Source Linking Jobs

```bash
# Confirm DataHub ingestion/bridge CronJobs exist (created suspended by default)
kubectl get cronjob -n data-services | grep datahub-

# Review dedicated ingestion config and secret objects
kubectl get configmap -n data-services datahub-ingestion-settings datahub-ingestion-recipes datahub-metadata-bridge
kubectl get secret -n data-services datahub-ingestion-secrets

# IMPORTANT: set real values for DATAHUB_TOKEN / source credentials before unsuspending jobs
kubectl edit secret -n data-services datahub-ingestion-secrets

# Unsuspend and trigger a native source ingestion run (example: PostgreSQL)
kubectl patch cronjob -n data-services datahub-ingest-postgres --type merge -p '{"spec":{"suspend":false}}'
kubectl create job -n data-services --from=cronjob/datahub-ingest-postgres datahub-ingest-postgres-manual
kubectl logs -n data-services job/datahub-ingest-postgres-manual

# Run metadata bridge for Argo/Dagster/Milvus/Chroma
kubectl patch cronjob -n data-services datahub-metadata-bridge --type merge -p '{"spec":{"suspend":false}}'
kubectl create job -n data-services --from=cronjob/datahub-metadata-bridge datahub-metadata-bridge-manual
kubectl logs -n data-services job/datahub-metadata-bridge-manual
```

Control panel access options:
- Ingress: `http://control.local` (hosts entry required)
- LoadBalancer: `http://<management-ui-external-ip>:9280`
- NodePort: `http://<node-ip>:31280`

## Step 11: Deploy Management Control Panel

```bash
# Apply management API/UI manifests
# (UI uses public nginx image + in-cluster static control panel config)
kubectl apply -f kubernetes/base-services/management/frontend.yaml

# If you previously deployed legacy selector labels and apply fails,
# recreate only the UI deployment and re-apply:
kubectl delete deployment -n management management-ui --ignore-not-found
kubectl apply -f kubernetes/base-services/management/frontend.yaml

# Verify rollout
kubectl rollout status deployment/management-ui -n management --timeout=180s
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

# Check drive manifest on each worker
ansible workers -a "cat /var/lib/auto-mount-drives/manifest.json" -i ansible/inventory/cluster.yml

# Re-run auto-mount to pick up new drives or fix mounts
ansible-playbook -i ansible/inventory/cluster.yml ansible/playbooks/auto-mount-storage.yml

# Check PVs and PVCs
kubectl get pv -o wide
kubectl get pvc -A

# Check StorageClasses (should show both local-path and local-storage)
kubectl get storageclass
```

### Service not accessible

```bash
# Check LoadBalancer IP assignment
kubectl get svc -A | grep LoadBalancer

# Check MetalLB
kubectl logs -n metallb-system -l app=metallb

# Check ingress controller and class
kubectl -n ingress get svc ingress-nginx-controller
kubectl get ingressclass nginx
```

### Dagster release missing or `dagster.local` unavailable

```bash
# Verify Helm release presence
helm list -n mlops | grep dagster

# Re-apply required secrets
kubectl apply -k kubernetes/mlops/dagster/

# Install or upgrade Dagster baseline release
helm upgrade --install dagster dagster/dagster \
  --namespace mlops \
  --create-namespace \
  -f kubernetes/mlops/dagster/values.yaml

# Verify webserver deployment, service, and ingress
kubectl rollout status deployment/dagster-dagster-webserver -n mlops --timeout=240s
kubectl get svc -n mlops dagster-dagster-webserver
kubectl get ingress -n mlops dagster-ingress
kubectl get pods -n mlops | grep dagster

# If Dagster logs show postgres authentication failures, reconcile role password
kubectl exec -n data-services deploy/postgresql -- \
  psql -U postgres -d postgres -c "ALTER ROLE dagster WITH LOGIN PASSWORD 'dagster123';"
```

### Argo UI error: sensors.argoproj.io not found

```bash
# Install Argo Events CRDs/controller (required by Argo Workflows API discovery)
helm upgrade --install argo-events argo/argo-events \
  --namespace mlops \
  --create-namespace \
  -f kubernetes/mlops/argo-events/values.yaml

# Ensure default EventBus exists
kubectl apply -k kubernetes/mlops/argo-events/

# Verify CRDs are registered
kubectl get crd sensors.argoproj.io eventsources.argoproj.io eventbus.argoproj.io

# Restart Argo server to refresh discovery cache if needed
kubectl rollout restart deployment/argo-workflows-server -n mlops
```

### Logs not appearing in Loki / traces not appearing in Jaeger

```bash
# Collector export health (look for loki and jaeger exporter errors)
kubectl logs -n observability -l app=otel-collector --tail=200

# Loki and Jaeger health
kubectl get pods -n observability -l app.kubernetes.io/name=loki
kubectl get pods -n observability -l app=jaeger

# Service reachability from inside cluster
kubectl run -n observability netcheck --rm -it --image=curlimages/curl --restart=Never -- \
  sh -c "curl -sf http://loki.observability:3100/ready && curl -sf http://jaeger-query.observability:16686"
```

## Next Steps

1. **Explore JupyterHub**: Create notebooks and connect to MLFlow
2. **Configure Grafana dashboards**: Import additional dashboards
3. **Deploy your applications**: Use the deployment API or kubectl
4. **Scale workers**: Add more Raspberry Pi nodes as needed

See [extending-framework.md](extending-framework.md) for advanced configuration.
