# Kubernetes deployment runbook (AQP integration)

This runbook documents how `rpi_kubernetes` hosts AQP workloads during the
control-plane migration.

## Scope

- This repo provides cluster bootstrap, platform operators, and shared base
  services.
- `agentic_quant_platform` provides the AQP application workloads
  (`aqp-client`, `aqp-core`, `aqp-worker`, `aqp-cp`) and their canonical
  deployment overlays.

## Prerequisites

- Cluster is healthy (`kubectl get nodes` all `Ready`).
- Base operators and service namespaces are installed from this repo.
- Auth0/K8s settings are synced in `agentic_quant_platform/deployments`.
- `aqp-config` / `aqp-secrets` values are rendered with real environment values
  (not placeholder templates) before workload rollout.

## Deployment sequence

1. Apply the AQP namespace/config prerequisites from this repo:

   ```powershell
   kubectl apply -k kubernetes/base-services/aqp/
   ```

2. Deploy AQP workloads from `agentic_quant_platform`:

   ```powershell
   cd ..\\agentic_quant_platform
   kubectl apply -k deployments/kubernetes/overlays/dev
   ```

3. Verify both namespaces:

   ```powershell
   kubectl -n aqp get pods,svc,hpa,pdb
   kubectl -n aqp-admin get pods,svc
   ```

## Validation

- AQP client responds over ingress/service.
- Control plane health endpoint is reachable:

  ```powershell
  curl http://<control-plane-host>/manage/health
  ```

- No new routes/services are added under deprecated
  `management/backend` or `management/frontend`.

## Migration guardrails

- `management/backend` and `management/frontend` are deprecated and must not
  receive new feature work.
- New management features belong in `agentic_quant_platform` under
  `aqp_control_plane` and `frontend`.
- Keep this runbook aligned with
  `agentic_quant_platform/docs/operations/kubernetes-deploy.md`.
