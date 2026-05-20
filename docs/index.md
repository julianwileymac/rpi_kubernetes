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
| [code-index.md](code-index.md) | active | Agent-readable code ownership and search boundaries |
| [aqp-monorepo-paths.md](aqp-monorepo-paths.md) | active | AQP path contract used by this repo |

## Domain docs

| Doc family | Status | Notes |
| --- | --- | --- |
| `kafka-*.md`, `flink-*.md`, `alpha-vantage.md`, `data-pipeline-recipes.md` | active | Streaming and ingestion guides |
| `document-store.md`, `redis-stack.md`, `vector-stores.md` | active | Storage + retrieval architecture |
| `management/backend/**`, `management/frontend/**` docs | deprecated | Superseded by `agentic_quant_platform` control plane and frontend surfaces |

## Deprecated surfaces

- [../management/backend/DEPRECATED.md](../management/backend/DEPRECATED.md)
- [../management/frontend/DEPRECATED.md](../management/frontend/DEPRECATED.md)
- [../kubernetes/legacy-management/kustomization.yaml](../kubernetes/legacy-management/kustomization.yaml)

## Agent Governance

| Artifact | Purpose |
| --- | --- |
| [../AGENTS.md](../AGENTS.md) | Root repository boundaries |
| [../kubernetes/AGENTS.md](../kubernetes/AGENTS.md) | Manifest ownership rules |
| [../management/AGENTS.md](../management/AGENTS.md) | SDK and deprecated management guidance |
| [../.cursor/rules/](../.cursor/rules/) | Cursor-scoped rules |
| [../.cursor/skills/rpi-k8s-governance/SKILL.md](../.cursor/skills/rpi-k8s-governance/SKILL.md) | Repeatable setup/index governance workflow |

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

# Rollback only: apply deprecated management console explicitly
kubectl apply -k kubernetes/legacy-management/
```
