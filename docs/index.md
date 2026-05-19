# rpi_kubernetes documentation index

Canonical documentation entry point for this repository.

## Status taxonomy

- `active` — current operational guidance.
- `migration` — transitional guidance while moving to AQP control plane/client.
- `deprecated` — retained for backward compatibility; do not extend.
- `archive` — historical incident material.

## Core runbooks

| Doc | Status | Purpose |
| --- | --- | --- |
| [../README.md](../README.md) | active | Hardware + cluster overview and quickstart |
| [../AGENTS.md](../AGENTS.md) | active | Agent-facing repository boundaries |
| [setup-guide.md](setup-guide.md) | active | Detailed bootstrap + cluster setup |
| [operations/kubernetes-deploy.md](operations/kubernetes-deploy.md) | migration | AQP integration rollout path for this cluster |
| [management-api.md](management-api.md) | migration | Legacy management API reference while migration completes |
| [extending-framework.md](extending-framework.md) | migration | Extension patterns with active/deprecated boundaries |

## Domain docs

| Doc family | Status | Notes |
| --- | --- | --- |
| `kafka-*.md`, `flink-*.md`, `alpha-vantage.md`, `data-pipeline-recipes.md` | active | Streaming and ingestion guides |
| `document-store.md`, `redis-stack.md`, `vector-stores.md` | active | Storage + retrieval architecture |
| `management/backend/**`, `management/frontend/**` docs | deprecated | Superseded by `agentic_quant_platform` control plane and frontend surfaces |

## Deprecated surfaces

- [../management/backend/DEPRECATED.md](../management/backend/DEPRECATED.md)
- [../management/frontend/DEPRECATED.md](../management/frontend/DEPRECATED.md)

## Archive guidance

Point-in-time operator notes should be moved under `docs/archive/` and linked
from this index. They should not remain as top-level canonical setup docs.

## Operational snippet catalog

```bash
# Cluster health
kubectl get nodes

# Apply full cluster manifests after CRDs/operators are installed
kubectl apply -k kubernetes/

# Apply AQP integration prerequisites from this repo
kubectl apply -k kubernetes/base-services/aqp/
```
