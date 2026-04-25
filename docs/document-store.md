# Document Store Portal

A self-service portal for loading documents into the cluster's Redis
8 Stack vector store, browsing JSON artifacts on MinIO, annotating
documents with freehand notes, and searching everything via keyword,
semantic, or hybrid retrieval.  All of it backed by the deployment
described in [redis-stack.md](redis-stack.md).

## URLs

| Page                        | Path                                | Purpose                              |
| --------------------------- | ----------------------------------- | ------------------------------------ |
| Document portal landing     | `/documents`                        | Upload + search + recent docs.       |
| MinIO artifact browser      | `/documents/artifacts`              | Self-service ingestion of JSON.      |
| Document detail             | `/documents/{id}`                   | Metadata + annotations + delete.     |

The portal is added as a primary nav entry in
[Sidebar.tsx](../management/frontend/src/components/layout/Sidebar.tsx).

## API

All endpoints sit under `/api/documents/*` on the management API.  See
[management-api.md](management-api.md) for the global conventions.

| Method | Path                                              | Description                              |
| ------ | ------------------------------------------------- | ---------------------------------------- |
| POST   | `/api/documents/upload`                           | Multipart upload + index.                |
| GET    | `/api/documents`                                  | List documents (filters: query, collection, tag). |
| GET    | `/api/documents/{id}`                             | Fetch document metadata.                 |
| DELETE | `/api/documents/{id}`                             | Delete doc + chunks + annotations.       |
| POST   | `/api/documents/search`                           | Keyword / semantic / hybrid search.      |
| POST   | `/api/documents/{id}/annotations`                 | Add annotation.                          |
| GET    | `/api/documents/{id}/annotations`                 | List annotations.                        |
| DELETE | `/api/documents/{id}/annotations/{ann_id}`        | Delete annotation.                       |
| GET    | `/api/documents/artifacts/buckets`                | List configured MinIO buckets.           |
| GET    | `/api/documents/artifacts/browse?bucket&prefix`   | List objects within a prefix.            |
| POST   | `/api/documents/artifacts/ingest`                 | Ingest a MinIO JSON object.              |

The Redis admin endpoints under `/api/redis/*` (see
[redis-stack.md](redis-stack.md)) round out the surface.

## Settings

`management/backend/src/config.py` adds two settings groups bound to
the new portal:

- `RedisSettings` (env prefix `REDIS_`) - URL, password, TTL,
  semantic-cache threshold.
- `DocumentStoreSettings` (env prefix `DOCSTORE_`) - bucket and prefix
  for uploaded blobs, allowed MIME types, chunk size/overlap, embedding
  dim, allowed artifact buckets, RediSearch index names.

The defaults match the in-cluster Redis 8 Stack and MinIO services.
Override via the ConfigMap in
[management/backend.yaml](../kubernetes/base-services/management/backend.yaml).

## Storage layout

| Where               | What                                                  |
| ------------------- | ----------------------------------------------------- |
| MinIO bucket        | Original uploaded blobs (`s3://dagster-artifacts/documents/{id}/{filename}`). |
| Redis `doc:{id}`    | RedisJSON document metadata.                          |
| Redis `chunk:{id}`  | RedisJSON chunk text + FLOAT32 embedding (HNSW vector index). |
| Redis `ann:{doc}:{id}` | RedisJSON freehand annotations.                    |
| Redis `artifact:{bucket}:{sha}` | RedisJSON ingestion receipt for MinIO objects. |

## Search modes

The `/api/documents/search` endpoint supports three modes:

- `keyword` - RediSearch full-text query against the chunk index.
- `semantic` - HNSW KNN against the chunk embeddings.
- `hybrid` (default) - reciprocal rank fusion of keyword + semantic.

Embeddings default to a deterministic SHA-256 fallback so the portal
works out-of-the-box; swap to a real provider via the standard
`EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` env vars from
[pipelines/embeddings.py](../pipelines/embeddings.py).

## Ingesting MinIO JSON artifacts

The `/documents/artifacts` page lists buckets configured via
`DOCSTORE_ARTIFACT_BUCKETS`.  The default set:

- `dagster-artifacts`
- `mlflow-artifacts`
- `pipeline-raw`
- `pipeline-processed`

Selecting any object launches `POST /api/documents/artifacts/ingest`
which:

1. Pulls the object from MinIO via boto3 (server-side).
2. Renders JSON as flattened `path: value` lines (or text otherwise).
3. Chunks + embeds with the same path as a fresh upload.
4. Writes a `doc:{id}`, N `chunk:{id}` records, and an
   `artifact:{bucket}:{sha}` receipt.

The CLI version is
[pipelines/examples/ingest_minio_json_to_redis.py](../pipelines/examples/ingest_minio_json_to_redis.py).

## Observability

Each request emits OTel spans under the `docstore.*` and `redis.*`
namespaces.  Counters land in:

- `stats:cache` (hits, misses, sets, deletes) - the same hash that the
  cache-aside decorator uses.
- `stats:ingest:documents`, `stats:ingest:chunks`,
  `stats:ingest:count` (RedisTimeSeries) - feeds the Grafana
  Document Store dashboard.

## Preservation notes

- Existing Milvus / ChromaDB ingest paths remain untouched in
  [pipelines/vector_io.py](../pipelines/vector_io.py) and
  [pipelines/retrieval.py](../pipelines/retrieval.py).  Choose the
  backend per-collection, not globally.
- The portal stores blobs in MinIO and only metadata + chunks in
  Redis, so disk pressure on the Pi nodes scales with metadata size,
  not document size.
- The MinIO health-check service in the management API is unchanged;
  the new document service uses its own boto3 client to avoid coupling
  to the existing healthcheck path.
