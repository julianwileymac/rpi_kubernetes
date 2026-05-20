# Kafka Resources (Strimzi)

Strimzi provides a complete operator model for Kafka. This cluster deploys
the full set of "common" resources so every piece of the Kafka ecosystem is
addressable declaratively.

| Resource | Manifest | Purpose |
|----------|----------|---------|
| `Kafka` + `KafkaNodePool` | [`kafka-cluster.yaml`](../kubernetes/base-services/kafka/kafka-cluster.yaml) | Single-broker KRaft cluster with plain, TLS, and SCRAM listeners + native OTel tracing |
| `KafkaTopic` (13 market + 14 alphavantage) | [`topics.yaml`](../kubernetes/base-services/kafka/topics.yaml) | Canonical market / features / deadletter topics + dedicated `alphavantage.*.v1` streams (see below) |
| `KafkaUser` (7 users) | [`users.yaml`](../kubernetes/base-services/kafka/users.yaml) | SCRAM-SHA-512 identities with per-topic ACLs |
| `KafkaConnect` | [`connect.yaml`](../kubernetes/base-services/kafka/connect.yaml) | Shared connector runtime (S3, JDBC, Apicurio converter plugins) |
| `KafkaConnector` (2 samples) | [`connectors/`](../kubernetes/base-services/kafka/connectors/) | Paused S3 + JDBC sinks for features |
| `KafkaBridge` | [`bridge.yaml`](../kubernetes/base-services/kafka/bridge.yaml) | HTTP gateway backing the `/kafka/topics/{name}/produce` endpoint |
| `KafkaMirrorMaker2` | [`mirrormaker2.yaml`](../kubernetes/base-services/kafka/mirrormaker2.yaml) | DR / multi-cluster replication (replicas=0 until activated) |
| `KafkaRebalance` | [`rebalance.yaml`](../kubernetes/base-services/kafka/rebalance.yaml) | Cruise Control template (paused; activate once `spec.cruiseControl` is enabled on the Kafka CR) |
| Apicurio Schema Registry | [`schema-registry/`](../kubernetes/base-services/schema-registry/) | Kafka-backed Avro registry (REST v2 + Confluent compat) |

## Listener layout

| Port | Name   | TLS | Auth          | Intended use                              |
|------|--------|-----|---------------|-------------------------------------------|
| 9092 | plain  | No  | None          | In-cluster trusted producers / brokers    |
| 9093 | tls    | Yes | Mutual TLS    | Inter-broker / Connect TLS                |
| 9094 | scram  | Yes | SCRAM-SHA-512 | All authenticated clients (templates, SDK)|

The `scram` listener is the default for new clients; the plain listener
remains available for Flink jobs that would otherwise need to rotate
credentials on every upgrade.

## Users

Each `KafkaUser` materializes a Secret of the same name holding `password`
(SCRAM) or `user.crt`/`user.key` (mTLS) keys. Templates reference the
secret via `secretKeyRef` so passwords rotate automatically when the
operator regenerates them.

ACL scoping uses Strimzi's literal + prefix patterns:

- `producer-market`: write `market.*` and `market.deadletter.v1`.
- `producer-features`: write `features.*`.
- `consumer-flink`: read `market.*`, read+write `features.*`, group/transactional prefix `flink-`.
- `consumer-management`: read `market.*` + `features.*`, group prefix `management-`.
- `connect-sinks`: read `features.*` + `connect-*` internal topics.
- `bridge-gateway`: read+write all pipeline topics + group prefix `bridge-`.
- `admin-sdk`: declared as a cluster super user.

## Kafka Connect

The `trading-connect` `KafkaConnect` CR builds its own image at deploy time
using `spec.build`:

1. Camel AWS S3 sink (`camel-aws-s3-sink`).
2. Confluent JDBC sink (`kafka-connect-jdbc`) + PostgreSQL driver.
3. Apicurio Avro converter for Confluent-compatible Avro payloads.

After the build finishes, connectors defined under
[`connectors/`](../kubernetes/base-services/kafka/connectors/) are
reconciled by the operator. They start in `paused` state; prefer direct
`kubectl` patches. The legacy management API example is rollback-only:

```bash
curl -XPATCH \
  -H "Content-Type: application/json" \
  -d '{"state":"running"}' \
  http://control.local/api/kafka/connectors/s3-sink-features-indicators/state
```

Preferred direct `kubectl` path:

```bash
kubectl patch kafkaconnector s3-sink-features-indicators -n data-services \
  --type merge -p '{"spec":{"state":"running"}}'
```

## Kafka Bridge

The Bridge exposes Kafka over HTTP at
`http://trading-bridge-bridge-service.data-services.svc.cluster.local:8080`
and via the Ingress at `http://kafka-bridge.local`. Payloads are JSON with
Strimzi's content type:

```bash
curl -XPOST http://kafka-bridge.local/topics/market.trade.v1 \
  -H "Content-Type: application/vnd.kafka.json.v2+json" \
  -d '{"records":[{"key":"AAPL.NASDAQ","value":{"ts_ns":1,"vt_symbol":"AAPL.NASDAQ","price":180.5,"size":100,"exchange":"NASDAQ","received_ts_ns":1}}]}'
```

The management API's `/kafka/topics/{name}/produce` endpoint proxies through
the Bridge, so notebooks can hit it without separate credentials.

## MirrorMaker 2

The `trading-mirror` CR is a template for cross-cluster replication but
ships with `replicas: 0`. To activate:

1. Set `spec.clusters[1].bootstrapServers` to the remote cluster's
   bootstrap servers and update auth.
2. `kubectl scale kafkamirrormaker2/trading-mirror --replicas=1`.

## Rebalance / Cruise Control

`KafkaRebalance` requires `spec.cruiseControl` on the Kafka CR. Cruise
Control adds ~256Mi of memory overhead, so we keep it off by default on a
single-broker cluster. When enabling:

1. Add `cruiseControl: {}` under `spec` in
   [`kafka-cluster.yaml`](../kubernetes/base-services/kafka/kafka-cluster.yaml).
2. Remove the `strimzi.io/pause-reconciliation` annotation from
   [`rebalance.yaml`](../kubernetes/base-services/kafka/rebalance.yaml).
3. `kubectl annotate kafkarebalance/trading-rebalance strimzi.io/rebalance=approve`.

## Schema Registry (Apicurio)

Apicurio is deployed as a dedicated Deployment +
Service + Ingress under
[`kubernetes/base-services/schema-registry/`](../kubernetes/base-services/schema-registry/).
Storage uses the `kafkasql` backend so schemas are persisted in a topic
`apicurio-kafkasql-journal` alongside the other KafkaTopics.

- REST v2: `http://apicurio-registry.data-services.svc.cluster.local:8080/apis/registry/v2`
- Confluent compat: `http://apicurio-registry.data-services:8080/apis/ccompat/v7`
- UI:   `http://schema-registry.local`

Clients can register artifacts at startup (auto-register) or require
operators to push them ahead of time (`find-latest`). The samples under
[`samples/market-data-producers/`](../samples/market-data-producers/) do
both via [`common/avro_codec.py`](../samples/market-data-producers/python/common/avro_codec.py).

## Alpha Vantage topics

The `alphavantage.*.v1` family is dedicated to Alpha Vantage-sourced data.
It lives alongside the existing `market.*.v1` topics so AV streams and the
IBKR/Alpaca trading streams stay independently evolvable. Avro schemas are
at [`flink-jobs/jobs/schemas/alphavantage/`](../flink-jobs/jobs/schemas/alphavantage/).

| Topic | Partitions | Retention | Policy | Produced by |
|-------|-----------:|-----------|--------|-------------|
| `alphavantage.quote.v1` | 6 | 1d | delete | `GLOBAL_QUOTE` poller |
| `alphavantage.bar.v1` | 6 | 7d | delete | `TIME_SERIES_INTRADAY` tail |
| `alphavantage.fx.v1` | 3 | 7d | delete | `CURRENCY_EXCHANGE_RATE` + FX_* |
| `alphavantage.crypto.v1` | 3 | 7d | delete | `CRYPTO_INTRADAY` + `DIGITAL_CURRENCY_*` |
| `alphavantage.indicator.v1` | 6 | 30d | compact+delete | 52 technical indicators |
| `alphavantage.news.v1` | 3 | 30d | compact+delete | `NEWS_SENTIMENT` |
| `alphavantage.gainers.v1` | 1 | 7d | delete | `TOP_GAINERS_LOSERS` |
| `alphavantage.insider.v1` | 1 | 365d | compact+delete | `INSIDER_TRANSACTIONS` |
| `alphavantage.overview.v1` | 1 | infinite | compact | `OVERVIEW` (keyed by symbol) |
| `alphavantage.earnings.v1` | 3 | 365d | compact+delete | `EARNINGS` / `EARNINGS_CALENDAR` / `EARNINGS_ESTIMATES` |
| `alphavantage.options.v1` | 3 | 7d | delete | `REALTIME_OPTIONS` / `HISTORICAL_OPTIONS` |
| `alphavantage.commodity.v1` | 1 | 365d | compact+delete | WTI/Brent/etc. |
| `alphavantage.econ.v1` | 1 | 365d | compact+delete | GDP/CPI/yields/... |
| `alphavantage.deadletter.v1` | 1 | 30d | delete | Any AV producer failure |

Producers of these topics:

- [`templates/alphavantage-producer/`](../templates/alphavantage-producer/) -
  streaming poll-and-emit Deployment.
- [`kubernetes/mlops/pipelines/alphavantage/`](../kubernetes/mlops/pipelines/alphavantage/)
  WorkflowTemplates (bulk loads primarily write JSON to MinIO but reuse the
  same Avro schemas on the dead-letter topic).


