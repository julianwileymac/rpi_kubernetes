# Kafka Client Templating

This guide walks through the Python and Java client templates bundled with
this repo, the Avro + Apicurio wire format the cluster standardizes on, and
the observability plumbing every template ships with.

## Quick map

| Template | Path | Runtime | Role |
|----------|------|---------|------|
| Python producer | [`templates/kafka-python-producer/`](../templates/kafka-python-producer/) | `confluent-kafka` | Publish Avro records to a topic |
| Python consumer | [`templates/kafka-python-consumer/`](../templates/kafka-python-consumer/) | `aiokafka` | Async consume + decode Avro |
| Java producer | [`templates/kafka-java-producer/`](../templates/kafka-java-producer/) | `org.apache.kafka:kafka-clients` | Gradle shadow JAR with OTel agent |
| Java consumer | [`templates/kafka-java-consumer/`](../templates/kafka-java-consumer/) | `org.apache.kafka:kafka-clients` | Gradle shadow JAR with OTel agent |
| Flink Java job | [`templates/flink-java-job/`](../templates/flink-java-job/) | Flink 1.20 | Skeleton DataStream job |

## Wire format

The cluster uses the **Confluent-compatible Apicurio wire format**:

```
| magic (0) | 4-byte big-endian global schema id | schemaless Avro payload |
```

Producers encode using `Apicurio Avro serde` (Java) or the `httpx` +
`fastavro` helpers in [`samples/market-data-producers/python/common/avro_codec.py`](../samples/market-data-producers/python/common/avro_codec.py)
(Python). Consumers decode the same way. Apicurio exposes the schemas over
its REST v2 API at
`http://apicurio-registry.data-services.svc.cluster.local:8080/apis/registry/v2`
and via the Confluent-compat shim at
`http://apicurio-registry.data-services:8080/apis/ccompat/v7`.

## Authentication

All templates authenticate via the Strimzi SCRAM-SHA-512 listener on port
9094 using the KafkaUser CRs defined in
[`kubernetes/base-services/kafka/users.yaml`](../kubernetes/base-services/kafka/users.yaml):

| User | Purpose | Topic ACL scope |
|------|---------|------------------|
| `producer-market` | Market data producers | `market.*` write |
| `producer-features` | Flink jobs writing features | `features.*` write |
| `consumer-flink` | Flink consumers | read `market.*`, read+write `features.*`, transactional prefix `flink-` |
| `consumer-management` | Management UI and SDK read paths | `market.*`, `features.*` read |
| `connect-sinks` | Kafka Connect sink connectors | read `features.*` |
| `bridge-gateway` | Kafka Bridge HTTP gateway | read + write all pipeline topics |
| `admin-sdk` | Super user for the Python SDK | full cluster admin |

The User Operator generates a Secret with the same name as the KafkaUser;
templates mount the `password` key from it into
`KAFKA_PRODUCER_SASL_PASSWORD` / `KAFKA_CONSUMER_SASL_PASSWORD`.

The cluster CA is mounted from `trading-kafka-cluster-ca-cert`:

- Python clients read `ca.crt` directly via `ssl.ca.location`.
- Java clients convert `ca.crt` into a JKS truststore in an init-container
  (`keytool -import ...`) and point `ssl.truststore.location` at it.

## Tracing

Every template exports OpenTelemetry traces to the in-cluster collector at
`http://otel-collector.observability.svc.cluster.local:4317`:

- **Python**: `opentelemetry-instrumentation-confluent-kafka` /
  `opentelemetry-instrumentation-aiokafka` auto-instrument producer / consumer
  calls; `opentelemetry-instrumentation-httpx` covers schema-registry lookups.
- **Java**: the OpenTelemetry Java Agent is attached via
  `JAVA_TOOL_OPTIONS=-javaagent:/opt/otel/opentelemetry-javaagent.jar`. The
  agent auto-instruments Kafka and HTTP clients without code changes.

See [`docs/observability-stack.md`](./observability-stack.md) for the
collector config.

## Python workflow

```bash
cp -r templates/kafka-python-producer my-producer
cd my-producer

# Customise src/producer/config.py + kubernetes/configmap.yaml

docker build -t ghcr.io/you/my-producer:0.1.0 .
docker push ghcr.io/you/my-producer:0.1.0

kubectl apply -k kubernetes/
```

Local dev runs straight off the schema files in
[`flink-jobs/jobs/schemas/`](../flink-jobs/jobs/schemas/):

```bash
pip install -e .
python -m producer                       # synthetic sample loop
```

## Java workflow

```bash
cp -r templates/kafka-java-producer my-java-producer
cd my-java-producer

./gradlew shadowJar
docker build -t ghcr.io/you/my-java-producer:0.1.0 .
docker push ghcr.io/you/my-java-producer:0.1.0

kubectl apply -k kubernetes/
```

## Using the Python SDK

For strategy code and notebooks that don't need a full deployment, use the
[Python SDK](../management/sdk/) directly:

```python
from rpi_k8s_sdk import configure_tracing
from rpi_k8s_sdk.kafka import AvroProducer

configure_tracing("my-strategy")

with AvroProducer(
    bootstrap="trading-kafka-kafka-bootstrap.data-services:9094",
    username="producer-market",
    password=os.environ["KAFKA_PASSWORD"],
    ssl_cafile="/etc/kafka/ca/ca.crt",
) as p:
    p.registry.load_local("market_trade_v1", "market_trade_v1.avsc")
    p.produce(
        topic="market.trade.v1",
        schema="market_trade_v1",
        record=record,
        key=record["vt_symbol"],
    )
```

See [`management/sdk/README.md`](../management/sdk/README.md) for the full
API surface (`AvroProducer`, `AvroConsumer`, `KafkaAdmin`, `ApicurioClient`,
`ManagementFlinkClient`).
