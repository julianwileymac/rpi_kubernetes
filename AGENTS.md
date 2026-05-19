# AGENTS.md

Agent entry point for `rpi_kubernetes`.

## Primary scope

This repository owns:

- Raspberry Pi / Ubuntu cluster bootstrap and operations automation.
- Kubernetes base services, operators, and shared cluster infrastructure.
- Streaming and data-service templates/samples.

This repository does **not** own new AQP control-plane or operator-frontend
features. Those live in `agentic_quant_platform`.

## Canonical docs

- [README.md](README.md)
- [docs/index.md](docs/index.md)
- [docs/setup-guide.md](docs/setup-guide.md)
- [docs/operations/kubernetes-deploy.md](docs/operations/kubernetes-deploy.md)

## Hard boundaries

1. `management/backend` and `management/frontend` are deprecated. Do not add
   new features there; only rollback maintenance.
2. AQP application workload deployment instructions must point to
   `agentic_quant_platform/deployments/kubernetes`.
3. Keep Kubernetes apply order explicit when CRDs/operators are prerequisites.
   Do not present `kubectl apply -k kubernetes/` as universally sufficient.
4. New top-level incident or point-in-time docs belong under `docs/archive/`
   with date/context labels, not as canonical root docs.
5. Keep docs path-accurate: do not reference missing runbooks or manifests.

## Editing guidance

- Prefer additive docs updates with clear `active`/`deprecated` labels.
- Keep commands copy-pastable for PowerShell and bash where possible.
- Verify referenced files exist before linking.
