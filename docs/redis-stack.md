# Redis 8 Stack Guide

This guide covers the shared **Redis 8 Stack** deployment that powers
caching, vector search, semantic LLM caching, agent memory, and the
self-service [Document Store](document-store.md) UI across the cluster.

## Why Redis 8 Stack?

The Redis 8 (or `redis-stack-server`) image bundles every module needed
to satisfy the workloads in this repository in a single binary:

| Module           | Purpose                                                        |
| ---------------- | -------------------------------------------------------------- |
| RediSearch       | Full-text search + HNSW/FLAT vector indexes                    |
| RedisJSON        | First-class JSON documents (used as the chunk + doc primary)   |
| RedisTimeSeries  | Observability counters + market-data demos                     |
| RedisBloom       | Top-K, Bloom, Cuckoo, t-digest probabilistic structures        |

This replaces the previous standalone Valkey deployment that backed
RAGFlow and adds capacity for the framework, the management API, the
Next.js portal, and the agent stack to share one cache cluster.

## Deployment

The manifests live under
[kubernetes/base-services/redis/](../kubernetes/base-services/redis/):

| File                              | Role                                                     |
| --------------------------------- | -------------------------------------------------------- |
| [secret.yaml](../kubernetes/base-services/redis/secret.yaml)             | `redis-credentials` Secret (password, URL).      |
| [configmap.yaml](../kubernetes/base-services/redis/configmap.yaml)       | `redis.conf` (AOF, latency monitor, slowlog).    |
| [pvc.yaml](../kubernetes/base-services/redis/pvc.yaml)                   | 10 Gi PVC backed by `local-path`.                |
| [deployment.yaml](../kubernetes/base-services/redis/deployment.yaml)     | `redis/redis-stack-server:7.4.0-v3` Deployment.  |
| [service.yaml](../kubernetes/base-services/redis/service.yaml)           | `redis` Service + `ragflow-redis` alias Service. |
| [exporter-deployment.yaml](../kubernetes/base-services/redis/exporter-deployment.yaml) | `oliver006/redis_exporter` sidecar (port 9121).  |
| [exporter-service.yaml](../kubernetes/base-services/redis/exporter-service.yaml) | Service in front of the exporter.               |
| [servicemonitor.yaml](../kubernetes/base-services/redis/servicemonitor.yaml) | Prometheus ServiceMonitor for the exporter.     |
| [kustomization.yaml](../kubernetes/base-services/redis/kustomization.yaml) | Apply order.                                    |

Install with:

```bash
kubectl apply -k kubernetes/base-services/redis/

# Smoke test
bash bootstrap/scripts/install-redis.sh
```

The root [kubernetes/kustomization.yaml](../kubernetes/kustomization.yaml)
already includes `base-services/redis/`, so a full
`kubectl apply -k kubernetes/` brings up Redis alongside everything
else.

## RAGFlow migration

The previous `kubernetes/base-services/ragflow/redis-deployment.yaml`
Valkey Deployment was removed.  The new Redis Stack ships an alias
Service named `ragflow-redis`, so the existing
`ragflow-redis.data-services.svc.cluster.local` host in
[ragflow/configmap.yaml](../kubernetes/base-services/ragflow/configmap.yaml)
and `redis-host` in
[ragflow/secret.yaml](../kubernetes/base-services/ragflow/secret.yaml)
keep working without changes.  RAGFlow continues to use **db=1**.

## Database / keyspace allocation

| DB | Owner                | Notes                                              |
| -- | -------------------- | -------------------------------------------------- |
| 0  | Shared framework     | Default for the management API, pipelines, agents. |
| 1  | RAGFlow              | Unchanged; managed by the upstream RAGFlow image.  |

Within db 0, keys are namespaced by prefix:

```
doc:{id}                  RedisJSON document metadata
chunk:{id}                RedisJSON chunk + HNSW vector
ann:{doc}:{id}            RedisJSON freehand annotation
artifact:{bucket}:{sha}   MinIO ingestion receipt
cache:{module}:{sha256}   cache-aside string entries (TTL)
semcache:{name}           RedisVL semantic cache
agent:{thread}:*          LangGraph checkpoints + store
stats:*                   counters + RedisTimeSeries series
```

The RediSearch indexes managed by the framework:

| Index             | Prefix    | Purpose                                |
| ----------------- | --------- | -------------------------------------- |
| `idx:documents`   | `doc:`    | Document store metadata                |
| `idx:chunks`      | `chunk:`  | RAG chunks + vector field (HNSW)       |
| `idx:annotations` | `ann:`    | Freehand annotations                   |

## Connecting from Python

```python
from pipelines.redis_io import get_redis, ping, require_modules
from pipelines.redis_vectors import ensure_index, upsert_chunks, vector_search
from pipelines.redis_cache import cache_aside, SemanticCache

assert ping()
require_modules(("search", "rejson", "timeseries", "bf"))

ensure_index("idx:chunks", vector_dims=1536)
upsert_chunks("idx:chunks", records=[...])
hits = vector_search("idx:chunks", query_vector=[...], top_k=5)

@cache_aside(ttl=60, namespace="examples")
def expensive(symbol: str) -> dict: ...

cache = SemanticCache(name="my_llm_cache", distance_threshold=0.15)
```

For LangGraph agent memory:

```python
from pipelines.agent_memory import get_checkpointer, get_store

checkpointer = get_checkpointer()
store = get_store(vector_dims=1536, distance="cosine")
```

## Connecting from the management API

`management/backend/src/services/redis_service.py` wraps the async
`redis.asyncio` client with health checks, OTel spans, and a
`cached_call` helper used by the cluster + hardware endpoints.  The
service is exposed via the new routers:

- `GET /api/redis/health`
- `GET /api/redis/stats`
- `GET /api/redis/indexes`
- `DELETE /api/redis/cache/{namespace}`

and the document-store endpoints under `/api/documents/...`.

## Observability

See [observability-stack.md](observability-stack.md) for the full
breakdown.  Highlights:

- Prometheus scrapes `oliver006/redis_exporter` via the ServiceMonitor in
  this directory.
- The `redis-overview` (grafana.com #11835) and custom
  `redis-document-store` dashboards are provisioned via the Grafana
  Helm values in
  [observability/prometheus/values.yaml](../kubernetes/observability/prometheus/values.yaml).
- The `redis-datasource` Grafana plugin enables direct-query panels
  (`TS.RANGE`, `FT.INFO`, `JSON.GET`, `HGETALL`).
- The OTel Collector runs a `redis` receiver as a secondary metrics
  source; the Redis password is mirrored into the `observability`
  namespace via
  [otel-collector/redis-secret.yaml](../kubernetes/observability/otel-collector/redis-secret.yaml).
- `OpenTelemetry RedisInstrumentor` is enabled in
  [management/backend/src/telemetry/setup.py](../management/backend/src/telemetry/setup.py)
  so every `redis.*` command appears as a Jaeger span.

## Operational playbook

```bash
# Health
kubectl -n data-services exec deploy/redis -- \
  redis-cli -a "$REDIS_PASSWORD" --no-auth-warning ping

# Loaded modules
kubectl -n data-services exec deploy/redis -- \
  redis-cli -a "$REDIS_PASSWORD" --no-auth-warning MODULE LIST

# Latency / slowlog triage
kubectl -n data-services exec deploy/redis -- \
  redis-cli -a "$REDIS_PASSWORD" --no-auth-warning LATENCY LATEST
kubectl -n data-services exec deploy/redis -- \
  redis-cli -a "$REDIS_PASSWORD" --no-auth-warning SLOWLOG GET 10

# Index sizes
kubectl -n data-services exec deploy/redis -- \
  redis-cli -a "$REDIS_PASSWORD" --no-auth-warning FT._LIST
kubectl -n data-services exec deploy/redis -- \
  redis-cli -a "$REDIS_PASSWORD" --no-auth-warning FT.INFO idx:chunks
```

## Examples

The following scripts under
[pipelines/examples/](../pipelines/examples/) demonstrate end-to-end
usage:

- [ingest_pdf_to_redis.py](../pipelines/examples/ingest_pdf_to_redis.py)
- [ingest_minio_json_to_redis.py](../pipelines/examples/ingest_minio_json_to_redis.py)
- [redis_semantic_cache_demo.py](../pipelines/examples/redis_semantic_cache_demo.py)
- [redis_object_cache_demo.py](../pipelines/examples/redis_object_cache_demo.py)
- [redis_om_document_demo.py](../pipelines/examples/redis_om_document_demo.py)
- [redis_agent_memory_demo.py](../pipelines/examples/redis_agent_memory_demo.py)
- [redis_timeseries_dashboard_demo.py](../pipelines/examples/redis_timeseries_dashboard_demo.py)

## Inspiration

Patterns and conventions come from:

- [redis-developer/langgraph-redis](https://github.com/redis-developer/langgraph-redis/tree/main/examples)
- [vector-arxiv-paper-qa](https://redis.io/tutorials/vector-arxiv-paper-qa/)
- [semantic-caching-with-redis-langcache](https://redis.io/tutorials/semantic-caching-with-redis-langcache/)
- [build-a-document-agent-with-redis-rag-and-agent-memory](https://redis.io/tutorials/build-a-document-agent-with-redis-rag-and-agent-memory/)
- [build-a-real-time-stock-watchlist-with-redis](https://redis.io/tutorials/build-a-real-time-stock-watchlist-with-redis/)
- [redis-at-scale/observability](https://redis.io/tutorials/operate/redis-at-scale/observability/)
- [observability/redisdatasource](https://redis.io/tutorials/operate/observability/redisdatasource/)
- [microservices/caching](https://redis.io/tutorials/howtos/solutions/microservices/caching/)
