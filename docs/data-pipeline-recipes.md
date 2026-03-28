# Data Pipeline Recipes (Argo + Dagster)

This guide provides runnable MVP recipes for moving, processing, and loading data across:

- Sources: HTTP files, REST APIs, S3-compatible sources, PostgreSQL tables, filesystem/NFS
- Sinks: MinIO, PostgreSQL, Milvus, ChromaDB

## Prerequisites

```bash
# Argo and Dagster must be deployed first
helm list -n mlops

# Build and publish runtime image used by Argo and Dagster user-code
docker build -f pipelines/Dockerfile -t ghcr.io/julianwiley/rpi-k8s-pipelines:latest .
docker push ghcr.io/julianwiley/rpi-k8s-pipelines:latest

# Apply pipeline manifests (templates, cron, secrets, bootstrap SQL, RBAC)
kubectl apply -k kubernetes/mlops/pipelines/
```

## Recipe 1: Raw ingest to MinIO

### Goal
Download from HTTP/REST/S3/filesystem and store raw immutable objects in MinIO.

### Run

```bash
argo submit --from workflowtemplate/pipeline-raw-ingest -n mlops \
  -p source_type=http \
  -p source_name=sample-http \
  -p source_uri=https://example.com/data.json \
  -p output_prefix=raw/manual \
  -p target_bucket=dagster-artifacts
```

### Verify

```bash
argo list -n mlops
argo logs @latest -n mlops
kubectl exec -n data-services deploy/minio -- mc ls local/dagster-artifacts/raw/manual/
```

### Hardening TODO
- Add pagination per source type
- Add dead-letter bucket path for failed pulls
- Add retention lifecycle policies

## Recipe 2: Dagster asset load MinIO -> PostgreSQL

### Goal
Materialize processed objects from MinIO into curated PostgreSQL tables.

### Run

Use Dagster UI at `http://dagster.local`, materialize asset:
- `minio_to_postgres_curated`

Default asset config:
- `source_bucket`: `dagster-artifacts`
- `source_key`: `processed/heavy/sample.json`
- `target_table`: `pipeline_curated_records`

### Verify

```bash
kubectl exec -n data-services deploy/postgresql -- \
  psql -U postgres -d dagster -c "select count(*) from pipeline_curated_records;"
```

### Hardening TODO
- Add schema contracts and validation checks
- Add typed target table models per pipeline

## Recipe 3: Hybrid Dagster -> Argo heavy transform

### Goal
Use Dagster for control/lineage while Argo runs heavy K8s-native transforms.

### Run

Materialize Dagster asset:
- `hybrid_argo_heavy_transform`

This submits Argo `WorkflowTemplate`:
- `pipeline-heavy-transform`

### Verify

```bash
argo list -n mlops
argo get @latest -n mlops
```

### Hardening TODO
- Add per-template retry and timeout policies
- Add resource classes for heavy workloads

## Recipe 4: Vector sync to Milvus and ChromaDB

### Goal
Chunk text payloads, generate embeddings, and dual-write vectors to Milvus and ChromaDB.

### Run

```bash
argo submit --from workflowtemplate/pipeline-vector-sync -n mlops \
  -p source_key=processed/heavy/sample.json \
  -p source_bucket=dagster-artifacts \
  -p collection_name=pipeline_documents
```

### Verify

```bash
kubectl exec -n data-services deploy/postgresql -- \
  psql -U postgres -d dagster -c "select count(*) from pipeline_vector_audit;"
```

### Hardening TODO
- Replace deterministic fallback embedding with production model endpoint
- Add model version + re-embedding strategy

## Recipe 5: CDC incremental sync

### Goal
Incrementally pull changed rows from source PostgreSQL and persist deltas to MinIO + sink tables.

### Run

```bash
argo submit --from workflowtemplate/pipeline-cdc-sync -n mlops \
  -p pipeline_name=cdc-source-events \
  -p source_table=source_events \
  -p primary_key=id \
  -p updated_at_column=updated_at
```

### Verify

```bash
kubectl exec -n data-services deploy/postgresql -- \
  psql -U postgres -d dagster -c "select * from pipeline_cdc_state;"
kubectl exec -n data-services deploy/minio -- mc ls local/dagster-artifacts/cdc/
```

### Hardening TODO
- Add conflict handling rules (upsert vs append)
- Add replay window for late-arriving rows

## First Run Checklist

1. Build/push `pipelines/Dockerfile` image and confirm image pull succeeds in cluster.
2. Apply `kubernetes/mlops/pipelines/` manifests and confirm:
   - `workflowtemplate` resources exist in `mlops`
   - `cronworkflow` resources exist in `mlops`
   - `pipeline-bootstrap-state` job completes successfully
3. Run Recipe 1 to create fresh raw data in MinIO.
4. Run Recipe 3 or 2 to process and load into PostgreSQL curated table.
5. Run Recipe 4 for vector sinks and check `pipeline_vector_audit`.
6. Run Recipe 5 twice and confirm second run uses advanced watermark with only deltas.
7. In Grafana, open `Workflow Orchestrators - Argo and Dagster` and confirm targets stay healthy.

