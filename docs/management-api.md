# Management API Reference

The FastAPI backend under [`management/backend/`](../management/backend/)
exposes the cluster control plane. The Kafka and Flink endpoints documented
here were added alongside the streaming platform expansion; see the other
routers for cluster / node / deployment / hardware / MLFlow operations.

Base URL:

- In-cluster: `http://management-api.management.svc.cluster.local:8080/api`
- Via ingress: `http://control.local/api`

All endpoints emit OTel spans via `@traced(...)` decorators, so requests
are visible in Jaeger / Tempo in the same trace as the downstream Kafka or
Flink operation they trigger.

## Kafka

### Topics

```
GET    /api/kafka/topics
GET    /api/kafka/topics/{name}
POST   /api/kafka/topics          body: KafkaTopicCreate
DELETE /api/kafka/topics/{name}
POST   /api/kafka/topics/{name}/produce   body: KafkaProduceRequest
```

`KafkaTopicCreate`:

```json
{
  "name": "market.sample.v1",
  "partitions": 6,
  "replicas": 1,
  "cluster": "trading-kafka",
  "config": {
    "retention.ms": "604800000",
    "cleanup.policy": "delete"
  }
}
```

`KafkaProduceRequest` (proxied to the Kafka Bridge):

```json
{
  "records": [
    {"ts_ns": 1, "vt_symbol": "AAPL.NASDAQ", "price": 180.5}
  ],
  "key_field": "vt_symbol"
}
```

### Users

```
GET    /api/kafka/users
POST   /api/kafka/users
DELETE /api/kafka/users/{name}
GET    /api/kafka/users/{name}/secret        # returns the SCRAM credentials
```

### Connectors

```
GET    /api/kafka/connectors
PATCH  /api/kafka/connectors/{name}/state    # ?state=running | paused | stopped
```

### Consumer groups + schema registry

```
GET    /api/kafka/consumer-groups
GET    /api/kafka/schema-registry/subjects
```

## Flink

### Deployments

```
GET /api/flink/deployments
```

### Session jobs

```
GET    /api/flink/sessionjobs
GET    /api/flink/sessionjobs/{name}
POST   /api/flink/sessionjobs            body: FlinkSessionJobCreate
PATCH  /api/flink/sessionjobs/{name}     body: FlinkSessionJobPatch
DELETE /api/flink/sessionjobs/{name}
```

Convenience wrappers for common operations (all accept the job name as the
path param):

```
POST   /api/flink/sessionjobs/{name}/activate        # set state=running
POST   /api/flink/sessionjobs/{name}/suspend         # set state=suspended
POST   /api/flink/sessionjobs/{name}/savepoint       # annotate to trigger
POST   /api/flink/sessionjobs/{name}/scale?parallelism=N
```

`FlinkSessionJobCreate`:

```json
{
  "name": "indicators-overlap",
  "jar_uri": "s3://flink-jobs/java/indicators-overlap.jar",
  "entry_class": "io.rpi.flink.indicators.overlap.OverlapJob",
  "args": ["--kafka.bootstrap.servers", "trading-kafka-kafka-bootstrap.data-services:9092"],
  "parallelism": 1,
  "upgrade_mode": "savepoint",
  "deployment": "flink-trading-session",
  "state": "suspended"
}
```

### Flink REST proxy

```
GET /api/flink/jobs
GET /api/flink/jobs/{job_id}
```

The proxy reads from the in-cluster service
`flink-trading-session-rest:8081` so callers don't need a direct Ingress.

## Alpha Vantage

The `/api/alphavantage/*` router wraps the
[`alphavantage_client`](../integrations/alphavantage/) engine. The service
automatically reloads the API key from
[`/var/run/secrets/alphavantage/api-key`](./alpha-vantage.md#credentials) and
shares a Redis-backed response cache.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/alphavantage/health` | Enabled flag, credentials check, rate-limit config, client version |
| GET | `/api/alphavantage/usage` | Live `RateLimiter` snapshot (tokens, rpm, daily, reset) |
| GET | `/api/alphavantage/search?keywords=...` | Symbol search typeahead |
| GET | `/api/alphavantage/market-status` | Global market open/close |
| GET | `/api/alphavantage/timeseries/{function}` | `intraday` / `daily` / `daily_adjusted` / `weekly` / `weekly_adjusted` / `monthly` / `monthly_adjusted` / `global_quote` / `bulk_quotes` |
| GET | `/api/alphavantage/fundamentals/{kind}` | `overview` / `etf` / `income` / `balance` / `cashflow` / `earnings` / `estimates` / `shares` / `dividends` / `splits` / `earnings_calendar` / `ipo` / `listing` |
| GET | `/api/alphavantage/technicals/{indicator}` | Any of the 52 AV technical indicators (SMA, EMA, MACD, RSI, BBANDS, ...) |
| GET | `/api/alphavantage/intelligence/{kind}` | `news` / `top-movers` / `insider` / `institutional` / `transcript` / `analytics-fixed` / `analytics-sliding` |
| GET | `/api/alphavantage/forex/{kind}` | `rate` / `intraday` / `daily` / `weekly` / `monthly` |
| GET | `/api/alphavantage/crypto/{kind}` | `rate` / `intraday` / `daily` / `weekly` / `monthly` |
| GET | `/api/alphavantage/options/{kind}` | `realtime` / `historical` / `pcr-realtime` / `pcr-historical` / `voi-realtime` / `voi-historical` |
| GET | `/api/alphavantage/commodities/{commodity}` | WTI/Brent/etc. |
| GET | `/api/alphavantage/economics/{indicator}` | GDP/CPI/yields/unemployment/... |
| GET | `/api/alphavantage/indices/{name}` | DJI/SPX/IXIC/NDX/VIX/RUT |
| GET | `/api/alphavantage/indices/catalog` | Full AV index catalog |
| POST | `/api/alphavantage/bulk-load` | Submit an Argo Workflow (`BulkLoadRequest`) |
| GET | `/api/alphavantage/workflows` | Recent AV workflow runs (labelled with `alphavantage/category`) |
| POST | `/api/alphavantage/stream` | Enable/disable the streaming producer by patching its Deployment replicas |

CSV endpoints (earnings/IPO calendar + listing status) return
`text/csv` directly; everything else returns JSON. Rate-limit / transport
errors are surfaced as typed `AlphaVantageError` subclasses by the client
engine and mapped to HTTP 500/503 by the router.

Example `bulk-load` payload:

```json
{
  "category": "fundamentals",
  "symbols": ["IBM", "AAPL", "MSFT"],
  "extra_params": {"kinds": "overview,income,balance,cashflow,earnings"},
  "target_bucket": "av-raw"
}
```

## Python SDK

Use the [Python SDK](../management/sdk/) to avoid hand-crafting HTTP calls:

```python
from rpi_k8s_sdk.flink import ManagementFlinkClient

with ManagementFlinkClient("http://control.local/api") as flink:
    for job in flink.list_session_jobs():
        print(job["name"], job["state"])
    flink.activate("indicators-momentum")
    flink.savepoint("indicators-momentum")
```

## Error handling

All endpoints return `5xx` on backend failures with a JSON body of the form
`{"detail": "<error message>"}`. Not-found resources return `404`. The
Python SDK raises `httpx.HTTPStatusError` on any non-2xx response.
