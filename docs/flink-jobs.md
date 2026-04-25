# Flink Jobs (PyFlink + Java TA-Lib)

The cluster's Flink session cluster runs two parallel job families:

| Runtime   | Location            | Role                                                                 |
|-----------|---------------------|----------------------------------------------------------------------|
| PyFlink   | [`flink-jobs/`](../flink-jobs/)   | MVP indicators + dedupe + normalize + scanner alerts        |
| Java      | [`flink-jobs-java/`](../flink-jobs-java/) | Full TA-Lib indicator catalog (~158 indicators + ~61 patterns) |

Both runtimes share the same `FlinkDeployment` session cluster (namespace
`flink`, name `flink-trading-session`) and publish to
`features.indicators.v1`. Consumers can merge records from both families by
inspecting the `category` field on the output record.

## PyFlink (existing)

### Image

[`flink-jobs/Dockerfile`](../flink-jobs/Dockerfile) builds a multi-arch image
based on `flink:1.20-java11`:

- Python 3 + pip + `apache-flink>=1.20,<1.21` + `fastavro`, `numpy`, `pandas`, `requests`
- Flink plugins: `flink-s3-fs-hadoop`, `flink-sql-connector-kafka`,
  `flink-connector-jdbc` + PostgreSQL JDBC driver
- `/opt/aqp-flink-jobs/jobs/` -- the job package from this repo, vendored at
  build time (including the Avro schemas)

Build + publish:

```bash
bash bootstrap/scripts/build-flink-jobs.sh --push \
  --image ghcr.io/julianwiley/flink-trading:1.20
```

### Layout

```
flink-jobs/
├── Dockerfile
├── pyproject.toml
└── jobs/
    ├── schemas/                          # Avro schemas (synced from aqp)
    ├── common/                           # Shared helpers (kafka, schemas, sinks)
    ├── dedupe.py                         # market.{trade,quote,bar}.v1 -> deduped
    ├── indicator_compute.py              # -> features.indicators.v1 (MVP set)
    ├── normalize_sink.py                 # -> features.normalized.v1 + PG/MinIO/VM
    └── scanner_alert.py                  # -> features.signals.v1
```

### FlinkSessionJob CRs

One CR per job lives under
[`kubernetes/base-services/flink/jobs/`](../kubernetes/base-services/flink/jobs/)
and points at the corresponding `.py` file in MinIO. Activate:

```bash
kubectl patch flinksessionjob <name> -n flink \
  --type merge -p '{"spec":{"job":{"state":"running"}}}'
```

Suspend + savepoint:

```bash
kubectl patch flinksessionjob <name> -n flink --type merge -p \
  '{"spec":{"job":{"state":"suspended","upgradeMode":"savepoint"}}}'
```

## Java TA-Lib jobs (new)

### Library

- **Flink 1.20** via Gradle dependency (matches the session cluster).
- **`com.tictactec:ta-lib:0.4.0`** - pure-Java port of TA-Lib with 1:1 API
  coverage of the ~200 native functions (indicators + candlestick patterns).
- **Apicurio Avro serde** for Kafka IO (Confluent-compatible wire format).

### Layout

```
flink-jobs-java/
├── README.md
├── settings.gradle
├── build.gradle
├── gradle.properties
├── Dockerfile
├── common/                              # shared POJOs + KafkaIO + pipeline helper
├── indicators-overlap/                  # SMA, EMA, WMA, DEMA, ..., BBANDS, SAR
├── indicators-momentum/                 # ADX, RSI, MACD, STOCH*, ROC*, WILLR, ...
├── indicators-volume/                   # AD, ADOSC, OBV
├── indicators-volatility/               # ATR, NATR, TRANGE
├── indicators-price-transform/          # AVGPRICE, MEDPRICE, TYPPRICE, WCLPRICE
├── indicators-cycle/                    # HT_DCPERIOD, HT_DCPHASE, HT_PHASOR, ...
├── indicators-statistic/                # BETA, CORREL, LINEARREG*, STDDEV, VAR, TSF
├── indicators-patterns/                 # ~61 candlestick patterns (CDL*)
├── indicators-math-transform/           # ACOS, ASIN, ATAN, CEIL, ..., SQRT, TANH
└── indicators-math-operator/            # ADD, DIV, MAX, MIN, MINMAX*, MULT, SUB, SUM
```

Each category is a Gradle subproject that produces a shadow JAR. The
per-category FlinkSessionJob CRs live under
[`kubernetes/base-services/flink/jobs-java/`](../kubernetes/base-services/flink/jobs-java/).

### Build + publish

```bash
bash bootstrap/scripts/build-flink-jobs-java.sh --push \
  --image ghcr.io/julianwiley/flink-trading-java:1.20
```

The script builds a multi-arch image, extracts each category's shadow JAR,
and uploads them to MinIO at `s3://flink-jobs/java/indicators-<category>.jar`
so the operator can resolve `spec.job.jarURI` without image churn.

### Activating the full catalog

```bash
# One-off: apply the suspended CRs if you haven't yet
kubectl apply -k kubernetes/base-services/flink/jobs-java/

# Activate the jobs gradually (memory permitting)
for cat in overlap momentum volume volatility price-transform \
           cycle statistic patterns math-transform math-operator; do
    kubectl patch flinksessionjob "indicators-${cat}" -n flink \
      --type merge -p '{"spec":{"job":{"state":"running"}}}'
done
```

### Pipeline anatomy

```
KafkaSource<GenericRecord>      (market.bar.v1)
    -> map(GenericRecord -> MarketBar)
    -> keyBy(vt_symbol)
    -> process(KeyedProcessFunction)   # per-category TA-Lib calls
    -> filter(non-empty IndicatorRecord)
    -> map(IndicatorRecord -> GenericRecord)
    -> KafkaSink<GenericRecord>        (features.indicators.v1)
```

The shared helper [`IndicatorPipeline`](../flink-jobs-java/common/src/main/java/io/rpi/flink/indicators/common/IndicatorPipeline.java)
owns the wiring so each category file contains only the TA-Lib calls.

## Adding a new job (either runtime)

1. Pick the runtime: PyFlink for small additions, Java for anything that
   wants full TA-Lib coverage or the Gradle test harness.
2. PyFlink: add `flink-jobs/jobs/<new_job>.py` with a `main(argv)` entrypoint.
   Java: copy [`templates/flink-java-job/`](../templates/flink-java-job/) into
   `flink-jobs-java/<new-job>/` and register it in
   [`flink-jobs-java/settings.gradle`](../flink-jobs-java/settings.gradle).
3. Rebuild + push the image (`build-flink-jobs.sh --push` or
   `build-flink-jobs-java.sh --push`).
4. Create a `FlinkSessionJob` CR under
   [`kubernetes/base-services/flink/jobs/`](../kubernetes/base-services/flink/jobs/)
   (PyFlink) or
   [`kubernetes/base-services/flink/jobs-java/`](../kubernetes/base-services/flink/jobs-java/)
   (Java) referencing the uploaded artifact.
5. Document the job in [data-pipeline-recipes.md](./data-pipeline-recipes.md)
   and, for indicators, [ta-indicators.md](./ta-indicators.md).

## Local development

### PyFlink

```bash
cd flink-jobs
pip install -e ".[dev]"

python -m jobs.dedupe \
  --kafka.bootstrap.servers localhost:9092 \
  --parallelism 1
```

### Java

```bash
cd flink-jobs-java
./gradlew :indicators-momentum:test
./gradlew :indicators-momentum:shadowJar

# Submit to an external cluster:
flink run -c io.rpi.flink.indicators.momentum.MomentumJob \
    indicators-momentum/build/libs/indicators-momentum.jar \
    --kafka.bootstrap.servers localhost:9092
```

See [`flink-jobs-java/README.md`](../flink-jobs-java/README.md) for the full
build/test cycle.
