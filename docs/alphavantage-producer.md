# Alpha Vantage streaming producer

The `templates/alphavantage-producer/` scaffold runs a Python asyncio
supervisor that polls each Alpha Vantage endpoint on its own cadence and
emits Avro-encoded records to the dedicated `alphavantage.*.v1` Kafka topics.
Deploy it with `kubectl apply -k` or via the management UI at
`/alphavantage/admin`.

## Streams

| Stream    | AV function(s)                            | Default cadence | Topic                         |
|-----------|-------------------------------------------|-----------------|-------------------------------|
| `quote`   | `GLOBAL_QUOTE`                            | 60s / symbol    | `alphavantage.quote.v1`      |
| `bar`     | `TIME_SERIES_INTRADAY` (tail)             | 300s / symbol   | `alphavantage.bar.v1`        |
| `fx`      | `CURRENCY_EXCHANGE_RATE`                  | 60s / pair      | `alphavantage.fx.v1`         |
| `crypto`  | `CRYPTO_INTRADAY` (tail)                  | 120s / pair     | `alphavantage.crypto.v1`     |
| `news`    | `NEWS_SENTIMENT`                          | 300s global     | `alphavantage.news.v1`       |
| `gainers` | `TOP_GAINERS_LOSERS`                      | 300s global     | `alphavantage.gainers.v1`    |
| `indicator` | Any of 52 technical indicators          | 600s / spec     | `alphavantage.indicator.v1`  |

Every failure routes to `alphavantage.deadletter.v1` with a typed
`error_kind` (`RATE_LIMIT_RPM`, `RATE_LIMIT_DAILY`, `INVALID_KEY`,
`INVALID_SYMBOL`, `PREMIUM_REQUIRED`, `PAYLOAD_ERROR`, `TRANSIENT`,
`PRODUCER_FAILURE`, `UNKNOWN`).

## Deployment topology

- **Namespace:** `data-services`
- **Deployment:** `alphavantage-producer`, default `replicas=0` (toggled via
  `POST /api/alphavantage/stream` or the Admin UI).
- **Secrets:**
  - `producer-market` (Strimzi `KafkaUser` password).
  - `alphavantage-credentials` (AV API token, mounted at
    `/var/run/secrets/alphavantage/api-key`).
  - `trading-kafka-cluster-ca-cert` (mounted at `/etc/kafka/ca/ca.crt`).
- **ConfigMaps:**
  - `alphavantage-producer-config` - Kafka + AV env defaults.
  - `alphavantage-producer-universe` - symbol universe + per-stream cadence
    (`/etc/alphavantage-producer/config.yaml`).

Edit the universe ConfigMap and `kubectl rollout restart
deployment/alphavantage-producer -n data-services` to apply.

## Configuration schema

`config.yaml` supports three top-level sections:

```yaml
streams:
  quote:
    enabled: true
    interval_seconds: 60
  bar:
    enabled: true
    interval_seconds: 300
    interval: "5min"
    outputsize: "compact"
  indicator:
    enabled: true
    interval_seconds: 600
universe:
  equities: [IBM, AAPL, MSFT, SPY]
  fx_pairs:
    - {from: EUR, to: USD}
  crypto_pairs:
    - {symbol: BTC, market: USD}
indicators:
  - {name: SMA, symbol: IBM, interval: daily, time_period: 20}
  - {name: RSI, symbol: IBM, interval: daily, time_period: 14}
  - {name: MACD, symbol: IBM, interval: daily}
```

## Avro schema registration

On startup the producer loads every `alphavantage_*.avsc` from
`/opt/alphavantage-producer/schemas/` (baked into the image) and upserts
them into Apicurio. Setting `AV_PRODUCER_REGISTER_SCHEMAS_ON_START=false`
skips the upsert if the operator prefers to pre-register schemas out of
band.

## Metrics

Exposed on `:9312/metrics`:

- `alphavantage_producer_messages_total{stream,topic,status}`
- `alphavantage_producer_api_request_seconds{stream,function}`
- `alphavantage_producer_rate_limiter_tokens`
- `alphavantage_producer_rate_limiter_requests_this_minute`
- `alphavantage_producer_rate_limiter_requests_today`
- `alphavantage_producer_deadletter_total{stream,reason}`

Prometheus scrapes via standard `prometheus.io/scrape` annotations on the
Deployment's Pod template.

## Building & publishing the image

```bash
docker build \
  --file templates/alphavantage-producer/Dockerfile \
  --tag ghcr.io/julianwiley/alphavantage-producer:0.1.0 \
  .
docker push ghcr.io/julianwiley/alphavantage-producer:0.1.0
```

The build context must be the repo root so the Dockerfile can `COPY
integrations/alphavantage ...` and bundle the client library.

## Local development

```bash
export ALPHAVANTAGE_API_KEY_FILE='C:\Users\Julian Wiley\Documents\alphavantage_api_token.txt'
export AV_PRODUCER_BOOTSTRAP_SERVERS=localhost:9092
export AV_PRODUCER_SECURITY_PROTOCOL=PLAINTEXT
export AV_PRODUCER_SCHEMA_REGISTRY_URL=http://localhost:8080/apis/registry/v2
python -m alphavantage_producer --config ./templates/alphavantage-producer/tests/fixtures/config.yaml
```

## Extending with new streams

1. Add an AVRO schema under `flink-jobs/jobs/schemas/alphavantage/`.
2. Add a new KafkaTopic entry to
   `kubernetes/base-services/kafka/topics.yaml`.
3. Add a `async def <name>_stream(app, cfg): ...` coroutine in
   `templates/alphavantage-producer/src/alphavantage_producer/streams.py`.
4. Register it in `STREAMS`.
5. Update the default runtime config in `config.py` if useful.

The shared rate limiter + retry loop handles the API-side work; your
coroutine's job is to map the AV response to the Avro record shape and call
`app.publish(...)`.
