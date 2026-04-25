"""OpenTelemetry setup shared by all samples."""

from __future__ import annotations

import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)


def configure_tracing(service_name: str, endpoint: str) -> trace.Tracer:
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "data-services",
            "deployment.environment": "rpi-cluster",
        }
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
    trace.set_tracer_provider(provider)

    # Auto-instrument confluent-kafka if the plugin is available.
    try:
        from opentelemetry.instrumentation.confluent_kafka import ConfluentKafkaInstrumentor

        ConfluentKafkaInstrumentor().instrument()
    except ImportError:
        logger.warning("confluent-kafka auto-instrumentation not available")

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
    except ImportError:
        logger.warning("httpx auto-instrumentation not available")

    return trace.get_tracer(service_name)
