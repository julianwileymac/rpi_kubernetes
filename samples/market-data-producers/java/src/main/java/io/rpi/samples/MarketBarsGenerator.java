package io.rpi.samples;

import org.apache.avro.Schema;
import org.apache.avro.generic.GenericData;
import org.apache.avro.generic.GenericRecord;

import java.time.Instant;
import java.util.Iterator;
import java.util.List;
import java.util.Random;
import java.util.concurrent.ThreadLocalRandom;

/**
 * Iterator that emits synthetic {@link GenericRecord} bars per symbol on a
 * fixed cadence. Modelled after
 * {@code org.apache.flink.training.exercises.common.sources.TaxiRideGenerator}:
 * the generator owns pseudo-random state keyed by the symbol and yields
 * records deterministically when provided a seeded {@link Random}.
 */
public final class MarketBarsGenerator implements Iterator<GenericRecord> {

    private final Schema schema;
    private final List<String> symbols;
    private final Random random;
    private final long periodNanos;
    private final int maxIterations;

    private int cursor;
    private int iteration;
    private long lastEmit;

    public MarketBarsGenerator(Schema schema, List<String> symbols, long periodMillis) {
        this(schema, symbols, periodMillis, Integer.MAX_VALUE, ThreadLocalRandom.current().nextLong());
    }

    public MarketBarsGenerator(Schema schema, List<String> symbols, long periodMillis, int maxIterations, long seed) {
        this.schema = schema;
        this.symbols = symbols;
        this.periodNanos = periodMillis * 1_000_000L;
        this.maxIterations = maxIterations;
        this.random = new Random(seed);
    }

    @Override
    public boolean hasNext() {
        return iteration < maxIterations;
    }

    @Override
    public GenericRecord next() {
        String symbol = symbols.get(cursor);
        cursor = (cursor + 1) % symbols.size();
        if (cursor == 0) {
            iteration++;
        }
        long now = Instant.now().toEpochMilli() * 1_000_000L;
        if (lastEmit != 0L) {
            long sleepNanos = periodNanos - (now - lastEmit);
            if (sleepNanos > 0) {
                try {
                    Thread.sleep(sleepNanos / 1_000_000L, (int) (sleepNanos % 1_000_000L));
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
            now = Instant.now().toEpochMilli() * 1_000_000L;
        }
        lastEmit = now;

        double close = 100.0 + random.nextDouble() * 400.0;
        double open = close + random.nextGaussian() * 0.5;
        double high = Math.max(open, close) + random.nextDouble();
        double low = Math.min(open, close) - random.nextDouble();
        double volume = 1000.0 + random.nextDouble() * 9000.0;

        GenericRecord record = new GenericData.Record(schema);
        record.put("ts_ns", now);
        record.put("vt_symbol", symbol);
        record.put("open", open);
        record.put("high", high);
        record.put("low", low);
        record.put("close", close);
        record.put("volume", volume);
        record.put("trade_count", random.nextInt(200));
        record.put("vwap", close);
        record.put("exchange", "NASDAQ");
        record.put("received_ts_ns", now);
        return record;
    }
}
