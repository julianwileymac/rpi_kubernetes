# TA-Lib Indicator Catalog

The [`flink-jobs-java/`](../flink-jobs-java/) module hierarchy is a 1:1
projection of [TA-Lib's published catalog](https://ta-lib.org/function.html)
onto Flink DataStream jobs. Each TA-Lib function category maps to a Gradle
subproject that compiles into a separate shadow JAR and runs as an
independent `FlinkSessionJob`.

## Mapping table

| TA-Lib group | Module | FlinkSessionJob | Indicator list |
|--------------|--------|-----------------|----------------|
| Overlap Studies | [`indicators-overlap`](../flink-jobs-java/indicators-overlap/) | `indicators-overlap` | SMA, EMA, WMA, DEMA, TEMA, TRIMA, KAMA, MAMA+FAMA, T3, BBANDS, MIDPOINT, MIDPRICE, SAR, SAREXT, HT_TRENDLINE |
| Momentum Indicators | [`indicators-momentum`](../flink-jobs-java/indicators-momentum/) | `indicators-momentum` | ADX, ADXR, APO, AROON, AROONOSC, BOP, CCI, CMO, DX, MACD, MACDEXT, MACDFIX, MFI, MINUS_DI, MINUS_DM, PLUS_DI, PLUS_DM, MOM, PPO, ROC, ROCP, ROCR, ROCR100, RSI, STOCH, STOCHF, STOCHRSI, TRIX, ULTOSC, WILLR |
| Volume Indicators | [`indicators-volume`](../flink-jobs-java/indicators-volume/) | `indicators-volume` | AD, ADOSC, OBV |
| Volatility Indicators | [`indicators-volatility`](../flink-jobs-java/indicators-volatility/) | `indicators-volatility` | ATR, NATR, TRANGE |
| Price Transform | [`indicators-price-transform`](../flink-jobs-java/indicators-price-transform/) | `indicators-price-transform` | AVGPRICE, MEDPRICE, TYPPRICE, WCLPRICE |
| Cycle Indicators | [`indicators-cycle`](../flink-jobs-java/indicators-cycle/) | `indicators-cycle` | HT_DCPERIOD, HT_DCPHASE, HT_PHASOR, HT_SINE, HT_TRENDMODE |
| Statistic Functions | [`indicators-statistic`](../flink-jobs-java/indicators-statistic/) | `indicators-statistic` | BETA, CORREL, LINEARREG, LINEARREG_ANGLE, LINEARREG_INTERCEPT, LINEARREG_SLOPE, STDDEV, TSF, VAR |
| Pattern Recognition | [`indicators-patterns`](../flink-jobs-java/indicators-patterns/) | `indicators-patterns` | 61 candlestick patterns (CDL2CROWS ... CDLXSIDEGAP3METHODS) |
| Math Transform | [`indicators-math-transform`](../flink-jobs-java/indicators-math-transform/) | `indicators-math-transform` | ACOS, ASIN, ATAN, CEIL, COS, COSH, EXP, FLOOR, LN, LOG10, SIN, SINH, SQRT, TAN, TANH |
| Math Operators | [`indicators-math-operator`](../flink-jobs-java/indicators-math-operator/) | `indicators-math-operator` | ADD, DIV, MAX, MAXINDEX, MIN, MININDEX, MINMAX, MINMAXINDEX, MULT, SUB, SUM |

## Input contract

All jobs consume `market.bar.v1`, keyed by `vt_symbol`. The Avro schema
lives at [`flink-jobs/jobs/schemas/market_bar_v1.avsc`](../flink-jobs/jobs/schemas/market_bar_v1.avsc)
and matches the POJO
[`MarketBar`](../flink-jobs-java/common/src/main/java/io/rpi/flink/indicators/common/MarketBar.java).

Each `KeyedProcessFunction` maintains a per-symbol
[`SymbolBufferState`](../flink-jobs-java/common/src/main/java/io/rpi/flink/indicators/common/SymbolBufferState.java)
ring buffer, pushes the new bar in, passes the buffer to the TA-Lib `Core`
function, and emits an
[`IndicatorRecord`](../flink-jobs-java/common/src/main/java/io/rpi/flink/indicators/common/IndicatorRecord.java)
to `features.indicators.v1` with:

- `ts_ns`, `vt_symbol`, `close`, `compute_ts_ns`
- `category` = the module's label (e.g. `"momentum"`)
- `extras` = a map of `"<indicator_name>" -> double`

## Buffer sizing

| Category | `buffer.size` | Rationale |
|----------|---------------|-----------|
| overlap | 300 | SMA_50 + BBANDS_20 + HT_TRENDLINE lookback |
| momentum | 300 | STOCHRSI + TRIX_30 + ULTOSC (7, 14, 28) |
| volume | 100 | ADOSC (3, 10) + OBV |
| volatility | 100 | ATR / NATR 14 |
| price-transform | 10 | pure OHLC transforms |
| cycle | 120 | HT_* require >= 63 bars |
| statistic | 100 | CORREL 30 + STDDEV 20 |
| patterns | 30 | most patterns look back 3-5 bars |
| math-transform | 10 | element-wise |
| math-operator | 60 | MAX / MIN / SUM over 30 bars |

Override per-job via `--buffer.size` on the CR. State TTL is 24h
(`SymbolBufferState.initialize`), so inactive symbols free their state
automatically.

## Running the full catalog

```bash
# Build + upload jars to MinIO (s3://flink-jobs/java/)
bash bootstrap/scripts/build-flink-jobs-java.sh --push

# Apply all CRs (they start suspended)
kubectl apply -k kubernetes/base-services/flink/jobs-java/

# Activate category-by-category:
kubectl patch flinksessionjob indicators-overlap -n flink \
  --type merge -p '{"spec":{"job":{"state":"running"}}}'
kubectl patch flinksessionjob indicators-momentum -n flink \
  --type merge -p '{"spec":{"job":{"state":"running"}}}'
# ... repeat per category
```

Or use the management API to avoid kubectl:

```bash
curl -XPOST http://control.local/api/flink/sessionjobs/indicators-overlap/activate
curl -XPOST http://control.local/api/flink/sessionjobs/indicators-momentum/activate
```

## Resource footprint (single-broker RPi cluster)

Each category job runs with `parallelism=1` (or 2 for momentum + patterns)
and a 1536Mi task slot. On the reference 4-node cluster all 10 jobs run
comfortably alongside the PyFlink jobs; if memory is tight, keep `patterns`
and `momentum` as the two prioritized jobs (they emit the highest signal
value per record). The others can be activated on demand.

## Adding a new indicator

1. Decide which category it belongs to (TA-Lib groups on ta-lib.org).
2. Edit the category's `<Category>IndicatorFunction.java` and call
   `Core.<function>(...)` wrapped in the same `tryCall(...)` pattern
   used by the existing indicators.
3. Rerun `./gradlew :indicators-<category>:test` to confirm state
   handling + indicator emission still work.
4. Push a new image via
   [`bootstrap/scripts/build-flink-jobs-java.sh --push`](../bootstrap/scripts/build-flink-jobs-java.sh).
5. If the indicator exposes a scalar not already in
   [`SinkSchemas`](../flink-jobs-java/common/src/main/java/io/rpi/flink/indicators/common/SinkSchemas.java),
   either add it there or let it flow through the `extras` map.
