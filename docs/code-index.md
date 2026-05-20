# Code Index

Status: active.

This repository indexes cluster bootstrap and shared Kubernetes platform
services. AQP application code is indexed in `agentic_quant_platform` (see `docs/aqp-monorepo-paths.md`).

## Ownership Map

| Area | Path | Owner |
| --- | --- | --- |
| Cluster bootstrap | `bootstrap/`, `ansible/` | `rpi_kubernetes` |
| Kubernetes platform services | `kubernetes/base-services/`, `kubernetes/storage/`, `kubernetes/observability/` | `rpi_kubernetes` |
| Streaming examples | `flink-jobs/`, `templates/`, `samples/` | `rpi_kubernetes` |
| AQP prerequisites | `kubernetes/base-services/aqp/` | `rpi_kubernetes` bridge |
| AQP workloads | `agentic_quant_platform/deployments/kubernetes/` | AQP |
| AQP workload controllers | `agentic_quant_platform/aqp_control_plane/` | AQP |
| Legacy management | `management/backend`, `management/frontend`, `kubernetes/legacy-management/` | rollback only |

## Agent Search Rules

- Search `kubernetes/AGENTS.md` before editing manifests.
- Search `management/AGENTS.md` before touching SDK or deprecated
  management surfaces.
- Do not route new AQP controller work to `management/backend`.
- Do not document legacy management as the default operator path.
- Keep `rpi_k8s_sdk.AqpControlPlaneClient` as the bridge for AQP control
  operations from this repo.

## Boundary Checks

```bash
rg "control.local/api|management/backend|management/frontend" docs README.md
kubectl kustomize kubernetes/
```

References to deprecated management should be marked as legacy or rollback.

