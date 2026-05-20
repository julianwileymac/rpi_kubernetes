# AQP Monorepo Paths

Status: active.

Use this path contract when `rpi_kubernetes` documentation or SDK code needs
to refer to AQP-owned surfaces. Avoid host-specific absolute paths.

| AQP responsibility | Canonical path inside `agentic_quant_platform` |
| --- | --- |
| Control plane | `aqp_control_plane/` |
| Shared platform contracts | `aqp_platform_core/` |
| Active client | `aqp_client/` |
| Bot runtime/templates | `aqp_bots/` |
| Snippet corpus | `aqp_snippets/` |
| Kubernetes workloads | `deployments/kubernetes/` |

`rpi_kubernetes` owns cluster bootstrap and shared base services. It may keep
AQP prerequisites under `kubernetes/base-services/aqp/`, but new AQP
workload controllers and UI features belong to the paths above.

