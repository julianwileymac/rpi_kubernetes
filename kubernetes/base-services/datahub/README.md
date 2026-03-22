# DataHub - Data Catalog

DataHub is an open-source metadata platform for data discovery, governance, and lineage tracking. This deployment includes the built-in Iceberg Catalog backed by MinIO.

## Prerequisites

- Existing PostgreSQL in `data-services` namespace with `datahub` database
- Existing MinIO in `data-services` namespace
- All DataHub components require amd64 (Java-based); scheduled on the control plane node

## Installation

### 1. Apply Kustomize Resources (secrets, ingress)

```bash
kubectl apply -k kubernetes/base-services/datahub/
```

### 2. Create MinIO Bucket for Iceberg

```bash
kubectl exec -n data-services deploy/minio -- \
  sh -c 'mc alias set local http://localhost:9000 minioadmin minioadmin123 && \
         mc mb local/iceberg-warehouse --ignore-existing'
```

### 3. Add Helm Repository

```bash
helm repo add datahub https://helm.datahubproject.io/
helm repo update
```

### 4. Install Prerequisites (Kafka, Elasticsearch)

```bash
helm install prerequisites datahub/datahub-prerequisites \
  --namespace data-services \
  -f values-prerequisites.yaml
```

Wait for all prerequisite pods to become ready:

```bash
kubectl get pods -n data-services -l app.kubernetes.io/instance=prerequisites --watch
```

### 5. Install DataHub

```bash
helm install datahub datahub/datahub \
  --namespace data-services \
  -f values-datahub.yaml
```

Wait for DataHub pods and the system-update job to complete:

```bash
kubectl get pods -n data-services -l app.kubernetes.io/instance=datahub --watch
```

## Access

| Endpoint | URL |
|----------|-----|
| DataHub UI | `http://datahub.local` |
| GMS API | `http://datahub.local:8080` (internal: `datahub-datahub-gms.data-services:8080`) |
| Iceberg REST Catalog | `http://datahub-datahub-gms.data-services:8080/iceberg` |

Default credentials: `datahub` / `datahub`

## Architecture

```
                   ┌──────────────┐
                   │   Frontend   │ :9002
                   └──────┬───────┘
                          │
                   ┌──────▼───────┐
                   │     GMS      │ :8080  ─── Iceberg REST Catalog
                   └──┬───┬───┬───┘
                      │   │   │
         ┌────────────┘   │   └────────────┐
         ▼                ▼                ▼
  ┌──────────────┐ ┌─────────────┐ ┌──────────────┐
  │ PostgreSQL   │ │Elasticsearch│ │    Kafka      │
  │ (existing)   │ │  (new)      │ │   (new)       │
  └──────────────┘ └─────────────┘ └───┬──────┬────┘
                                       │      │
                                ┌──────▼──┐ ┌─▼────────┐
                                │MAE Cons.│ │MCE Cons.  │
                                └─────────┘ └───────────┘
```

## DataHub dbt Ingestion

To ingest dbt metadata into DataHub, create a recipe file:

```yaml
source:
  type: dbt
  config:
    manifest_path: /path/to/target/manifest.json
    catalog_path: /path/to/target/catalog.json
    target_platform: postgres
    include_column_lineage: true

sink:
  type: datahub-rest
  config:
    server: "http://datahub-datahub-gms.data-services:8080"
```

Run ingestion:

```bash
datahub ingest -c dbt-recipe.yaml
```

## Upgrade

```bash
helm upgrade prerequisites datahub/datahub-prerequisites \
  --namespace data-services \
  -f values-prerequisites.yaml

helm upgrade datahub datahub/datahub \
  --namespace data-services \
  -f values-datahub.yaml
```

## Uninstall

```bash
helm uninstall datahub --namespace data-services
helm uninstall prerequisites --namespace data-services
```
