"""Thin wrappers over confluent-kafka used by all samples."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from confluent_kafka import KafkaError, Producer
from opentelemetry import trace
from prometheus_client import Counter, Histogram

from .avro_codec import AvroCodec
from .config import KafkaSettings

logger = logging.getLogger(__name__)

PRODUCED = Counter(
    "sample_producer_messages_total",
    "Kafka messages emitted by the samples.",
    ["producer", "topic", "status"],
)
PRODUCE_LATENCY = Histogram(
    "sample_producer_publish_seconds",
    "Latency of the produce+poll loop in seconds.",
    ["producer", "topic"],
    buckets=(0.001, 0.005, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)


def build_producer(settings: KafkaSettings, *, client_id: str) -> Producer:
    cfg: Dict[str, Any] = {
        "bootstrap.servers": settings.bootstrap_servers,
        "client.id": client_id,
        "enable.idempotence": True,
        "acks": "all",
        "compression.type": "snappy",
        "linger.ms": 10,
        "security.protocol": settings.security_protocol,
    }
    if settings.sasl_username:
        cfg["sasl.mechanism"] = settings.sasl_mechanism
        cfg["sasl.username"] = settings.sasl_username
    if settings.sasl_password:
        cfg["sasl.password"] = settings.sasl_password
    if settings.ssl_ca_location:
        cfg["ssl.ca.location"] = settings.ssl_ca_location
    return Producer(cfg)


def produce_with_tracing(
    producer: Producer,
    codec: AvroCodec,
    *,
    producer_name: str,
    schema_name: str,
    topic: str,
    record: Dict[str, Any],
    key: Optional[str] = None,
    tracer: Optional[trace.Tracer] = None,
) -> None:
    tracer = tracer or trace.get_tracer(producer_name)
    started = time.perf_counter()
    labels = {"producer": producer_name, "topic": topic}
    with tracer.start_as_current_span(
        "kafka.produce",
        attributes={
            "messaging.system": "kafka",
            "messaging.destination.name": topic,
            "messaging.kafka.schema": schema_name,
        },
    ) as span:
        try:
            payload = codec.encode(schema_name, record)
            producer.produce(
                topic=topic,
                key=key.encode() if key else None,
                value=payload,
                on_delivery=_delivery_callback(producer_name),
            )
            producer.poll(0)
            PRODUCED.labels(status="queued", **labels).inc()
        except Exception as exc:  # noqa: BLE001
            span.record_exception(exc)
            PRODUCED.labels(status="error", **labels).inc()
            logger.exception("produce failed for %s", topic)
        finally:
            PRODUCE_LATENCY.labels(**labels).observe(time.perf_counter() - started)


def _delivery_callback(producer_name: str):
    def _on_delivery(err: Optional[KafkaError], msg: Any) -> None:
        if err is not None:
            PRODUCED.labels(producer=producer_name, topic=msg.topic(), status="delivery_error").inc()
            logger.error("delivery failed: %s", err)
        else:
            PRODUCED.labels(producer=producer_name, topic=msg.topic(), status="delivered").inc()

    return _on_delivery
