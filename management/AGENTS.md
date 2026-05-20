# AGENTS.md

Agent contract for `management/`.

## Status

`management/backend` and `management/frontend` are deprecated rollback
surfaces. Do not add features there.

`management/sdk` remains the supported local interaction interface for the
cluster. New AQP workload operations should use
`rpi_k8s_sdk.AqpControlPlaneClient`, which calls the AQP control plane
`/manage/*` API.

## Hard Boundaries

1. No new backend routes or frontend pages under deprecated management
   surfaces.
2. New AQP control-plane behavior belongs in
   `agentic_quant_platform/aqp_control_plane`.
3. New AQP operator UI behavior belongs in `agentic_quant_platform/aqp_client`
   under the `aqp_client` boundary.
4. SDK additions should preserve backwards-compatible imports when possible
   and mark legacy management clients as compatibility-only.
5. Never print bearer tokens, kubeconfigs, tunnel credentials, or service
   account secrets.

## Validation

```bash
python -m pytest management/sdk/tests
```



AQP path contract: `docs/aqp-monorepo-paths.md`.
