# rpi Kubernetes Governance

Use this skill when editing rpi cluster docs, Kubernetes manifests, the local
SDK, or deprecated management surfaces.

## Workflow

1. Read `AGENTS.md`.
2. Read `docs/code-index.md`.
3. If editing manifests, read `kubernetes/AGENTS.md`.
4. If editing `management/`, read `management/AGENTS.md`.
5. Route new AQP workload control to
   `agentic_quant_platform/aqp_control_plane`, not this repo.

## Checks

```bash
kubectl kustomize kubernetes/
rg "control.local/api|management/backend|management/frontend" docs README.md
python -m pytest management/sdk/tests
```

Deprecated management references must be labeled legacy, migration, or
rollback.



AQP path contract: `docs/aqp-monorepo-paths.md`.
