# portal — julianwiley.com personal portal

Next.js 15 personal portal serving:

- public marketing / blog / projects pages at `https://julianwiley.com`
- an auth-gated admin dashboard at `https://julianwiley.com/app/*`

Source: [julianwileymac/julianwiley-portal](https://github.com/julianwileymac/julianwiley-portal).
Image: `ghcr.io/julianwileymac/portal:latest` (multi-arch — `linux/amd64` and `linux/arm64`).

## Layout

| File              | Purpose                                                                  |
| ----------------- | ------------------------------------------------------------------------ |
| `configmap.yaml`  | Non-sensitive runtime env (NextAuth issuer, public site URL, etc.)       |
| `secret.yaml`     | `AUTH_SECRET` + Entra/Google OAuth credentials (PLACEHOLDERS — replace!) |
| `deployment.yaml` | 2 replicas, RollingUpdate, read-only rootfs, multi-arch                  |
| `service.yaml`    | ClusterIP only — no LoadBalancer (tunnel handles internet exposure)      |
| `ingress.yaml`    | Hosts: `julianwiley.com` (tunnel) + `portal.local` (LAN)                 |

## First-time setup

1. **Replace the secret placeholders** before applying — the values shipped in
   `secret.yaml` will not produce a working sign-in flow:

   ```bash
   kubectl -n web create secret generic portal-credentials \
     --from-literal=AUTH_SECRET="$(openssl rand -base64 32)" \
     --from-literal=AUTH_MICROSOFT_ENTRA_ID_ID="<entra-client-id>" \
     --from-literal=AUTH_MICROSOFT_ENTRA_ID_SECRET="<entra-client-secret>" \
     --from-literal=AUTH_GOOGLE_ID="<google-client-id>" \
     --from-literal=AUTH_GOOGLE_SECRET="<google-client-secret>" \
     --dry-run=client -o yaml | kubectl apply -f -
   ```

2. **Apply the manifests** (or rely on the root kustomization to pick them up):

   ```bash
   kubectl apply -k kubernetes/base-services/portal/
   ```

3. **Confirm rollout**:

   ```bash
   kubectl -n web rollout status deploy/portal
   kubectl -n web get pods,svc,ingress -l app=portal
   ```

4. **LAN smoke test** — get the ingress-nginx LoadBalancer IP and add it to
   your hosts file:

   ```bash
   kubectl -n ingress get svc ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
   # then on the dev machine:
   #   <IP>  portal.local
   # and visit  http://portal.local
   ```

5. **Public exposure** — see
   [`../cloudflared/README.md`](../cloudflared/README.md) for the
   Cloudflare Tunnel + DNS steps that wire `julianwiley.com` to this Service.

## Updating the image

The GitHub Actions workflow at
[`.github/workflows/docker.yml`](https://github.com/julianwileymac/julianwiley-portal/blob/main/.github/workflows/docker.yml)
builds and pushes on every push to `main`. To roll a new image:

```bash
kubectl -n web set image deploy/portal portal=ghcr.io/julianwileymac/portal:sha-<short>
kubectl -n web rollout status deploy/portal
```

`:latest` always tracks `main` but pinning to an immutable `sha-<short>` tag
makes rollbacks trivial.

## Why no PVC

Blog content (`content/posts/*.mdx`) is baked into the image at build time, so
the runtime container is fully stateless. Sessions are JWT-encoded — no Redis
or Postgres dependency. Adding persistence would only be necessary once the
admin section starts writing back to the cluster (Phase 3).

## Architecture / scheduling

The image is multi-arch, so the scheduler is free to place replicas on either
the amd64 control plane or the arm64 RPi5 workers.
`topologySpreadConstraints` prefers spreading across hostnames so that a
single node loss doesn't take both replicas down.

If you need to pin to a single arch (e.g. for debugging), patch the
deployment with:

```yaml
spec:
  template:
    spec:
      nodeSelector:
        kubernetes.io/arch: amd64
```
