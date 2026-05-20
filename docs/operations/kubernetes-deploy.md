# Kubernetes deployment runbook (AQP integration)

This runbook documents how `rpi_kubernetes` hosts AQP workloads during the
control-plane migration.

## Scope

- This repo provides cluster bootstrap, platform operators, and shared base
  services.
- `agentic_quant_platform` provides the AQP application workloads
  (`aqp-client`, `aqp-core`, `aqp-worker`, `aqp-cp`) and their canonical
  deployment overlays.
- AQP domain paths are documented in
  [../aqp-monorepo-paths.md](../aqp-monorepo-paths.md).
- Deprecated `management/backend` and `management/frontend` are not deployed
  by the default root kustomization. Apply `kubernetes/legacy-management/`
  only for rollback.

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

2. Deploy AQP workloads from `agentic_quant_platform`. The canonical path
   is Terraform against the RPi environment; use Kustomize only as a
   manifest/debug fallback:

   ```powershell
   # From the agentic_quant_platform repository root
   terraform -chdir=terraform/environments/rpi init
   terraform -chdir=terraform/environments/rpi plan
   terraform -chdir=terraform/environments/rpi apply
   ```

   Fallback (rendered manifests only, after config/secrets are prepared):

   ```powershell
   kubectl apply -k deployments/kubernetes/base
   ```

3. Verify both namespaces:

   ```powershell
   kubectl -n aqp get pods,svc,hpa,pdb
   kubectl -n aqp-admin get pods,svc
   ```

## Validation

- AQP client responds over ingress/service or Cloudflare Tunnel:
  `https://aqp.fund`.
- AQP API liveness is reachable:

  ```powershell
  curl https://api.aqp.fund/livez
  ```
- Control plane health endpoint is reachable:

  ```powershell
  curl https://manage.aqp.fund/manage/livez
  ```

- No new routes/services are added under deprecated
  `management/backend` or `management/frontend`.
- The rendered default cluster manifests do not include the deprecated
  `management-api` or `management-ui` deployments.

## Migration guardrails

- `management/backend` and `management/frontend` are deprecated and must not
  receive new feature work.
- New management features belong in `agentic_quant_platform` under
  `aqp_control_plane` and `frontend`.
- Day-2 operations should use the AQP CLI (`aqp cp ...`) or the AQP Vite
  UI, not the deprecated management console.
- SDK callers should use `rpi_k8s_sdk.AqpControlPlaneClient` for AQP workload
  lifecycle operations.
- Keep this runbook aligned with
  `agentic_quant_platform/docs/operations/kubernetes-deploy.md`.
