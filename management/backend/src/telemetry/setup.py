"""OpenTelemetry setup and configuration."""

import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from ..config import Settings

logger = logging.getLogger(__name__)


def setup_telemetry(settings: Settings) -> None:
    """
    Configure OpenTelemetry tracing.

    Sets up:
    - OTLP exporter to send traces to the collector
    - FastAPI auto-instrumentation
    - Redis auto-instrumentation (covers redis-py sync + asyncio)
    - Custom resource attributes
    """
    if not settings.telemetry.enabled:
        logger.info("OpenTelemetry disabled")
        return

    # Create resource with service information
    resource = Resource.create({
        "service.name": settings.telemetry.service_name,
        "service.version": "0.1.0",
        "deployment.environment": "development",
        "cluster.name": settings.cluster_name,
    })

    # Create tracer provider
    provider = TracerProvider(resource=resource)

    # Configure OTLP exporter
    try:
        otlp_exporter = OTLPSpanExporter(
            endpoint=settings.telemetry.exporter_endpoint,
            insecure=True,  # For local development
        )

        # Add batch processor for efficient export
        processor = BatchSpanProcessor(otlp_exporter)
        provider.add_span_processor(processor)

        # Set as global tracer provider
        trace.set_tracer_provider(provider)

        # Instrument FastAPI
        FastAPIInstrumentor.instrument()

        # Instrument Redis (safe to call before any Redis client is created).
        # Captures both sync (redis.Redis) and async (redis.asyncio) traffic.
        try:
            from opentelemetry.instrumentation.redis import RedisInstrumentor

            RedisInstrumentor().instrument()
            logger.info("Redis OTel instrumentation enabled")
        except Exception as redis_err:  # pragma: no cover - optional dep
            logger.warning(
                "Redis OTel instrumentor unavailable: %s",
                redis_err,
            )

        logger.info(
            f"OpenTelemetry configured: exporting to {settings.telemetry.exporter_endpoint}"
        )

    except Exception as e:
        logger.warning(f"Failed to configure OTLP exporter: {e}")
        # Still set provider for local tracing
        trace.set_tracer_provider(provider)
