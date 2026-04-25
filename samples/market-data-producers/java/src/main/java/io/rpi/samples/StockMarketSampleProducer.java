package io.rpi.samples;

import io.apicurio.registry.serde.SerdeConfig;
import io.apicurio.registry.serde.avro.AvroKafkaSerializer;
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;
import org.apache.avro.Schema;
import org.apache.avro.generic.GenericRecord;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.config.SaslConfigs;
import org.apache.kafka.common.config.SslConfigs;
import org.apache.kafka.common.serialization.StringSerializer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Arrays;
import java.util.List;
import java.util.Properties;

/**
 * Java sample producer that emits synthetic {@code market.bar.v1} records.
 *
 * <p>Modelled after
 * {@link org.apache.flink.training.exercises.common.sources.TaxiRideGenerator}:
 * we own a single generator iterator and drive it in a main loop so Flink-
 * centric developers have a familiar starting point for wiring a Kafka
 * producer into the cluster.</p>
 */
public final class StockMarketSampleProducer {

    private static final Logger LOG = LoggerFactory.getLogger(StockMarketSampleProducer.class);

    private StockMarketSampleProducer() {
    }

    public static void main(String[] args) throws Exception {
        String bootstrap = env("KAFKA_BOOTSTRAP_SERVERS",
                "trading-kafka-kafka-bootstrap.data-services.svc.cluster.local:9094");
        String topic = env("KAFKA_TOPIC", "market.bar.v1");
        String schemaName = env("KAFKA_SCHEMA_NAME", "market_bar_v1");
        String registryUrl = env("SCHEMA_REGISTRY_URL",
                "http://apicurio-registry.data-services.svc.cluster.local:8080/apis/registry/v2");
        long periodMillis = Long.parseLong(env("BAR_PERIOD_MS", "1000"));
        List<String> symbols = Arrays.asList(env("KAFKA_SYMBOLS", "AAPL.NASDAQ,MSFT.NASDAQ,SPY.NYSE").split(","));

        Properties props = new Properties();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrap);
        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, AvroKafkaSerializer.class.getName());
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        props.put(ProducerConfig.COMPRESSION_TYPE_CONFIG, "snappy");
        props.put(ProducerConfig.CLIENT_ID_CONFIG, "stock-market-sample-producer");

        props.put("security.protocol", env("KAFKA_SECURITY_PROTOCOL", "SASL_SSL"));
        props.put(SaslConfigs.SASL_MECHANISM, env("KAFKA_SASL_MECHANISM", "SCRAM-SHA-512"));
        props.put(SaslConfigs.SASL_JAAS_CONFIG, String.format(
                "org.apache.kafka.common.security.scram.ScramLoginModule required username=\"%s\" password=\"%s\";",
                env("KAFKA_SASL_USERNAME", "producer-market"),
                env("KAFKA_SASL_PASSWORD", "")));
        props.put(SslConfigs.SSL_TRUSTSTORE_LOCATION_CONFIG,
                env("KAFKA_SSL_TRUSTSTORE_LOCATION", "/etc/kafka/ca/truststore.jks"));
        props.put(SslConfigs.SSL_TRUSTSTORE_PASSWORD_CONFIG,
                env("KAFKA_SSL_TRUSTSTORE_PASSWORD", "changeit"));
        props.put(SslConfigs.SSL_ENDPOINT_IDENTIFICATION_ALGORITHM_CONFIG, "");

        props.put(SerdeConfig.REGISTRY_URL, registryUrl);
        props.put(SerdeConfig.AUTO_REGISTER_ARTIFACT, "true");
        props.put(SerdeConfig.EXPLICIT_ARTIFACT_GROUP_ID, env("SCHEMA_GROUP", "default"));
        props.put(SerdeConfig.FIND_LATEST_ARTIFACT, "true");
        props.put(SerdeConfig.USE_ID, "contentId");
        props.put(SerdeConfig.ENABLE_HEADERS, "true");
        props.put(SerdeConfig.SCHEMA_ARTIFACT_ID, schemaName);

        Schema schema = loadBarSchema();
        MarketBarsGenerator generator = new MarketBarsGenerator(schema, symbols, periodMillis);
        Tracer tracer = GlobalOpenTelemetry.getTracer("stock-market-sample-producer");

        try (KafkaProducer<String, GenericRecord> producer = new KafkaProducer<>(props)) {
            Runtime.getRuntime().addShutdownHook(new Thread(() -> {
                producer.flush();
                LOG.info("producer flushed + closed");
            }));
            while (generator.hasNext()) {
                GenericRecord bar = generator.next();
                String key = bar.get("vt_symbol").toString();
                Span span = tracer.spanBuilder("kafka.produce").startSpan();
                try (Scope ignored = span.makeCurrent()) {
                    producer.send(new ProducerRecord<>(topic, key, bar));
                } catch (Exception e) {
                    span.recordException(e);
                    LOG.error("produce failed", e);
                } finally {
                    span.end();
                }
            }
        }
    }

    private static String env(String key, String fallback) {
        String v = System.getenv(key);
        return (v == null || v.isEmpty()) ? fallback : v;
    }

    /** Embedded mirror of market_bar_v1.avsc so the sample is self-contained. */
    private static Schema loadBarSchema() {
        String json = "{\"type\":\"record\",\"name\":\"MarketBarV1\",\"namespace\":\"aqp.streaming.market\","
                + "\"fields\":["
                + "{\"name\":\"ts_ns\",\"type\":\"long\"},"
                + "{\"name\":\"vt_symbol\",\"type\":\"string\"},"
                + "{\"name\":\"open\",\"type\":\"double\"},"
                + "{\"name\":\"high\",\"type\":\"double\"},"
                + "{\"name\":\"low\",\"type\":\"double\"},"
                + "{\"name\":\"close\",\"type\":\"double\"},"
                + "{\"name\":\"volume\",\"type\":\"double\"},"
                + "{\"name\":\"trade_count\",\"type\":\"int\"},"
                + "{\"name\":\"vwap\",\"type\":\"double\"},"
                + "{\"name\":\"exchange\",\"type\":\"string\"},"
                + "{\"name\":\"received_ts_ns\",\"type\":\"long\"}"
                + "]}";
        return new Schema.Parser().parse(json);
    }
}
