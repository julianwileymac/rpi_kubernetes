# cloudflared-aqp — AQP.FUND Cloudflare Tunnel

Outbound-only Cloudflare Tunnel connector for the AQP platform domain.
This is separate from the existing `cloudflared` deployment that serves
`julianwiley.com`, so AQP changes cannot disrupt the personal portal.

## Public hostnames

The Cloudflare-managed tunnel `aqp-fund-edge`
(`0cd12089-38ee-4dfb-95ba-65d2daa7b88b`) routes:

| Hostname | In-cluster service |
| --- | --- |
| `aqp.fund` | `http://aqp-client.aqp.svc.cluster.local:80` |
| `api.aqp.fund` | `http://aqp-core.aqp.svc.cluster.local:8000` |
| `manage.aqp.fund` | `http://aqp-cp.aqp-admin.svc.cluster.local:80` |

DNS records are proxied CNAMEs to:

`0cd12089-38ee-4dfb-95ba-65d2daa7b88b.cfargotunnel.com`

## One-time setup

Create the token secret out-of-band. Do not commit the token.

PowerShell:

```powershell
$token = cloudflared tunnel token aqp-fund-edge
kubectl -n edge create secret generic cloudflared-aqp-token `
  --from-literal=token=$token `
  --dry-run=client -o yaml | kubectl apply -f -
```

Bash:

```bash
token="$(cloudflared tunnel token aqp-fund-edge)"
kubectl -n edge create secret generic cloudflared-aqp-token \
  --from-literal=token="$token" \
  --dry-run=client -o yaml | kubectl apply -f -
```

## Deploy

Apply only this connector:

```powershell
kubectl apply -k kubernetes/base-services/cloudflared-aqp/
kubectl -n edge rollout status deploy/cloudflared-aqp --timeout=180s
```

Or apply the root after CRD/operator prerequisites are installed:

```powershell
kubectl apply -k kubernetes/
```

## Verify

```powershell
kubectl -n edge get deploy,pods,svc -l app=cloudflared-aqp
kubectl -n edge logs -l app=cloudflared-aqp --tail=50
```

Healthy logs include:

```text
Registered tunnel connection ...
Updated to new configuration config_version=...
```

Public checks:

```powershell
curl https://aqp.fund
curl https://api.aqp.fund/livez
curl https://manage.aqp.fund/manage/livez
```
