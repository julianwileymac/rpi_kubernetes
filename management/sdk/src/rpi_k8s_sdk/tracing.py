"""OpenTelemetry helper - shared by every SDK client that touches Kafka or
HTTP.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def configure_tracing(
    service_name: str,
    *,
    endpoint: Optional[str] = None,
    namespace: str = "data-services",
    instrument_kafka: bool = True,
    instrument_httpx: bool = True,
) -> None:
    """Install an OTLP/gRPC tracer provider and auto-instrument Kafka + httpx.

    Safe to call multiple times - only the first invocation installs the
    provider; subsequent calls are no-ops (dependent on the OpenTelemetry
    SDK's idempotency guarantees).
    """

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning("opentelemetry packages missing; tracing disabled.")
        return

    endpoint = endpoint or os.environ.get(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://otel-collector.observability.svc.cluster.local:4317",
    )
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": namespace,
            "deployment.environment": os.environ.get("OTEL_ENV", "rpi-cluster"),
        }
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
    trace.set_tracer_provider(provider)

    if instrument_kafka:
        try:
            from opentelemetry.instrumentation.confluent_kafka import ConfluentKafkaInstrumentor

            ConfluentKafkaInstrumentor().instrument()
        except ImportError:
            logger.debug("opentelemetry-instrumentation-confluent-kafka not installed")
        try:
            from opentelemetry.instrumentation.aiokafka import AIOKafkaInstrumentor

            AIOKafkaInstrumentor().instrument()
        except ImportError:
            logger.debug("opentelemetry-instrumentation-aiokafka not installed")

    if instrument_httpx:
        try:
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

            HTTPXClientInstrumentor().instrument()
        except ImportError:
            logger.debug("opentelemetry-instrumentation-httpx not installed")

    logger.info("tracing configured service=%s endpoint=%s", service_name, endpoint)
