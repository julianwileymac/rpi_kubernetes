# AGENTS.md

Agent contract for `kubernetes/`.

## Purpose

This tree owns cluster bootstrap manifests, operators, shared base services,
storage, streaming infrastructure, observability, and rollback-only legacy
management manifests.

## Hard Boundaries

1. Do not add new AQP application Deployments here. They belong in
   `agentic_quant_platform/deployments/kubernetes`.
2. Do not add new AQP workload controllers here. They belong in
   `agentic_quant_platform/aqp_control_plane`.
3. Keep CRD/operator install order explicit in docs and scripts.
4. Default `kubectl apply -k kubernetes/` must not deploy deprecated
   `base-services/management`.
5. Secrets in manifests must remain placeholders or references to external
   secret managers.

## Where Changes Go

- Cluster base service: `base-services/<service>/`.
- Optional legacy management rollback: `legacy-management/`.
- AQP namespace/config prerequisites only: `base-services/aqp/`.
- AQP workload manifests: sibling repo `agentic_quant_platform` (see `docs/aqp-monorepo-paths.md`).

