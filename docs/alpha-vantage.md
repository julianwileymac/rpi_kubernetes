# Alpha Vantage Integration

Alpha Vantage is the **primary market-data provider** for the rpi_kubernetes
cluster. This document covers every layer of the integration: the custom
Python client engine, the data models, the FastAPI admin surface, the Kafka
streaming producer, the Argo bulk-load WorkflowTemplates, and the new
`/alphavantage` route in the management UI.

## Architecture at a glance

```
+-------------------+      +-----------------------+      +--------------------+
| alphavantage.co   | <--- |  alphavantage-client  | <--- | alphavantage-      |
|  REST API (poll)  |      |  (integrations/)      |      | producer (Kafka)   |
|                   | <--- |                       | <--- | management API     |
+-------------------+      +----------+------------+      | (FastAPI)          |
                                      |                   | pipelines.cli      |
                                      |                   | (Argo batch)       |
                                      v                   +---------+----------+
                              +-------+--------+                    |
                              |  Kafka topics  | <------------------+
                              | alphavantage.* |
                              +-------+--------+
                                      |
                                      v
                              +-------+--------+      +-----------+
                              |   Flink jobs   | ---> |  features |
                              |  (enrichment)  |      |  topics   |
                              +----------------+      +-----------+
```

## 1. The client engine - `integrations/alphavantage/`

A drop-in replacement for `RomelTorres/alpha_vantage` with modern tooling:

- Unified **sync + async** facade (`AlphaVantageClient.timeseries.global_quote("IBM")`
  / `await client.timeseries.aglobal_quote("IBM")`).
- Token-bucket **rate limiter** (RPM + optional daily cap) shared across callers.
- Typed error hierarchy (`RateLimitError(kind=DAILY|RPM)`, `InvalidApiKeyError`,
  `PremiumEndpointError`, `TransientError`, ...) - rate-limit signals extracted
  from `Note`/`Information` JSON keys (AV returns HTTP 200 on throttling).
- Automatic retries with exponential backoff + jitter for RPM throttles and
  5xx/transport errors.
- Pluggable response cache (memory LRU, SQLite, Redis) with sensible
  per-endpoint TTL defaults (immutable history cached for 24h, realtime
  endpoints for 30s).
- Pydantic v2 response models for every category.
- Optional fallback to the upstream `alpha_vantage>=3.0` package when the
  community parsers are useful.

### Credentials

Resolution order (first match wins):

1. Explicit `api_key=` kwarg on `AlphaVantageClient(...)`.
2. `ALPHAVANTAGE_API_KEY` env var.
3. File at `ALPHAVANTAGE_API_KEY_FILE` (env).
4. Default local file -
   `C:\Users\Julian Wiley\Documents\alphavantage_api_token.txt`
   (Windows) or `~/.alphavantage/api_key` (Unix).
5. K8s secret mount: `/var/run/secrets/alphavantage/api-key`.

Raises `InvalidApiKeyError` when none resolve.

### Module layout

```
integrations/alphavantage/src/alphavantage_client/
  client.py                # AlphaVantageClient facade
  _transport.py            # httpx sync+async transport with retry/cache
  _rate_limiter.py         # token bucket
  _cache.py                # MemoryCache / SqliteCache / RedisCache
  _credentials.py          # API key resolver
  _errors.py               # typed exception hierarchy
  _types.py                # Interval / OutputSize / SeriesType / ... enums
  _parsers.py              # JSON helpers
  fallback.py              # optional alpha_vantage>=3.0 bridge
  endpoints/
    timeseries.py          # intraday/daily/..., GLOBAL_QUOTE, bulk quotes, search
    indices.py             # DJI/SPX/IXIC/NDX/VIX/RUT + index catalog
    options.py             # realtime + historical chains, PCR, VOI ratios
    intelligence.py        # news, top movers, insider, institutional, transcript, analytics
    fundamentals.py        # overview, ETF, IS/BS/CF, dividends, splits, earnings, calendars
    forex.py               # rate + intraday/daily/weekly/monthly FX bars
    crypto.py              # rate + intraday/daily/weekly/monthly crypto bars
    commodities.py         # WTI/Brent/natural gas/metals/ags/global index/gold+silver
    economics.py           # REAL_GDP, CPI, TREASURY_YIELD, FFR, UNEMPLOYMENT, ...
    technicals.py          # all 52 indicators through a unified `get` method
  models/                  # Pydantic v2 response models
```

### Quick start

```python
from alphavantage_client import AlphaVantageClient

client = AlphaVantageClient(rate_limit_rpm=75)
quote = client.timeseries.global_quote("IBM")
print(quote.price, quote.change_percent)

# News sentiment
payload = client.intelligence.news(tickers=["AAPL", "MSFT"], limit=100)
for article in payload.feed:
    print(article.title, article.overall_sentiment_label)
```

Async:

```python
import asyncio
from alphavantage_client import AlphaVantageClient

async def main():
    async with AlphaVantageClient() as client:
        series = await client.timeseries.adaily("IBM", outputsize="compact")
        for bar in series.bars[:5]:
            print(bar.timestamp, bar.close)

asyncio.run(main())
```

## 2. Data models

### Pydantic (backend + client)

Every endpoint returns a Pydantic v2 model; the backend at
`management/backend/src/models/alphavantage.py` re-exports these so routes
stay thin.

### Avro (Kafka)

14 Avro schemas live under `flink-jobs/jobs/schemas/alphavantage/` and back
the 14 dedicated topics. Each record shares:

- `ts_ns` - event-time epoch nanoseconds.
- `av_function` - the Alpha Vantage function that produced the record.
- `ingest_ts_ns` - producer-side timestamp for lag monitoring.

See `flink-jobs/jobs/schemas/alphavantage/README.md` for the full table.

### Redis-OM

The new `pipelines/alphavantage_om.py` module defines JsonModels for company
overviews, ETF profiles, statements, earnings, insider transactions, news
articles, earnings transcripts, IPO calendar entries, and listing status.
All live under the `rpi:av:` key prefix. Use `ensure_av_migrated()` to
(re)create RediSearch indexes.

## 3. Management API - `/api/alphavantage/*`

The new `api/alphavantage.py` router exposes every category. Full reference
lives in [`management-api.md`](./management-api.md#alpha-vantage) but the
high-level map:

| Route | Notes |
|-------|-------|
| `GET /api/alphavantage/health` | Client + credentials status |
| `GET /api/alphavantage/usage` | Live rate-limit snapshot |
| `GET /api/alphavantage/search?keywords=...` | Symbol search typeahead |
| `GET /api/alphavantage/market-status` | Global market open/close |
| `GET /api/alphavantage/timeseries/{fn}` | intraday/daily/.../global_quote |
| `GET /api/alphavantage/fundamentals/{kind}` | overview/etf/is/bs/cf/... |
| `GET /api/alphavantage/technicals/{indicator}` | any of 52 indicators |
| `GET /api/alphavantage/intelligence/{kind}` | news/transcript/movers/insider/institutional |
| `GET /api/alphavantage/forex/{kind}` | rate/intraday/daily/weekly/monthly |
| `GET /api/alphavantage/crypto/{kind}` | rate/intraday/daily/weekly/monthly |
| `GET /api/alphavantage/options/{kind}` | chains + PCR + VOI ratios |
| `GET /api/alphavantage/commodities/{commodity}` | WTI/Brent/metals/ags/global |
| `GET /api/alphavantage/economics/{indicator}` | GDP/CPI/yields/unemployment |
| `GET /api/alphavantage/indices/{name}` | DJI/SPX/IXIC/NDX/VIX/RUT |
| `POST /api/alphavantage/bulk-load` | Submit an Argo Workflow |
| `GET /api/alphavantage/workflows` | Recent AV workflow runs |
| `POST /api/alphavantage/stream` | Enable/disable the producer |

## 4. Streaming producer - `templates/alphavantage-producer/`

Poll-and-emit producer with one asyncio task per stream (quote / bar / fx /
crypto / news / gainers / indicator). All streams share a single rate
limiter; failures go to `alphavantage.deadletter.v1` with a typed
`error_kind`. See [`alphavantage-producer.md`](./alphavantage-producer.md).

## 5. Argo bulk loads - `kubernetes/mlops/pipelines/alphavantage/`

WorkflowTemplates:

- `av-bulk` (generic entrypoint used by all other templates).
- `av-bulk-timeseries`, `av-intraday-backfill`, `av-fundamentals`,
  `av-universe-sync`, `av-news-ingest`, `av-fx-backfill`,
  `av-crypto-backfill`, `av-technicals`, `av-commodities`, `av-economics`,
  `av-earnings`.

CronWorkflows:

- `av-universe-sync-hourly` - hourly LISTING_STATUS + IPO_CALENDAR refresh.
- `av-daily-refresh` - nightly fundamentals + adjusted daily bars for the
  watch list.

All templates use `pipelines.cli alphavantage-bulk` under the hood and write
JSON slices to `s3://av-raw/...` in MinIO. See
[`data-pipeline-recipes.md`](./data-pipeline-recipes.md#alpha-vantage-recipes)
for runnable examples.

## 6. UI - `/alphavantage`

Dashboard + 11 sub-routes (Time Series, Fundamentals, Technical Indicators,
Alpha Intelligence, Forex, Crypto, Options, Commodities, Economic Indicators,
Indices, Admin). All pages live under
`management/frontend/src/app/alphavantage/` and reuse the shared components
in `management/frontend/src/components/alphavantage/`.

## 7. Installation

```bash
bootstrap/scripts/install-alphavantage.sh
# or PowerShell on Windows:
pwsh bootstrap/scripts/install-alphavantage.ps1
```

The script loads the token from
`C:\Users\Julian Wiley\Documents\alphavantage_api_token.txt` (override with
`TOKEN_FILE=...`), creates the `alphavantage-credentials` Secret in both
`data-services` and `mlops`, applies the Kafka topics + Argo templates +
producer manifests, and runs a live smoke call.

## 8. Rate limit & entitlement

Alpha Vantage tiers:

| Tier | RPM | Daily | Realtime US equities |
|------|-----|-------|----------------------|
| Free | 5 | 25 | 15-min delayed, EOD |
| Premium $49.99/mo | 75 | unlimited | 15-min delayed |
| Premium $99.99/mo | 150 | unlimited | realtime |
| Premium $149.99/mo | 300 | unlimited | realtime |
| Premium $199.99/mo | 600 | unlimited | realtime |
| Premium $249.99/mo | 1200 | unlimited | realtime |

Tune `AV_PRODUCER_AV_RPM_LIMIT` / `AV_PRODUCER_AV_DAILY_LIMIT` env on the
producer Deployment and `alphavantage.rpm_limit` / `alphavantage.daily_limit`
on the management backend to match your tier.

## 9. Troubleshooting

- **`InvalidApiKeyError` in logs** - verify the secret:
  `kubectl -n data-services get secret alphavantage-credentials -o json | jq '.data."api-key"' -r | base64 -d`.
- **`RateLimitError(kind=DAILY)`** - the free tier cap resets at UTC midnight.
  Upgrade or wait.
- **No bars appearing on the dashboard** - check the Grafana dashboards for
  the `alphavantage_producer_messages_total` metric; deadletter counts should
  be zero.
- **Streaming producer stuck in Pending** - the Deployment starts at
  `replicas=0`. Scale it to 1 via the Admin UI or
  `kubectl -n data-services scale deploy/alphavantage-producer --replicas=1`.
