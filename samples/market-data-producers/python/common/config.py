"""Shared Kafka + schema settings for market-data producers."""

from __future__ import annotations

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class KafkaSettings(BaseSettings):
    """Environment-driven configuration (prefix ``KAFKA_``)."""

    model_config = SettingsConfigDict(env_prefix="KAFKA_", extra="ignore")

    bootstrap_servers: str = Field(
        default="trading-kafka-kafka-bootstrap.data-services.svc.cluster.local:9094"
    )
    security_protocol: str = Field(default="SASL_SSL")
    sasl_mechanism: str = Field(default="SCRAM-SHA-512")
    sasl_username: str = Field(default="producer-market")
    sasl_password: Optional[str] = Field(default=None)
    ssl_ca_location: Optional[str] = Field(default="/etc/kafka/ca/ca.crt")

    schema_registry_url: str = Field(
        default="http://apicurio-registry.data-services.svc.cluster.local:8080/apis/registry/v2"
    )
    schema_group: str = Field(default="default")

    otel_endpoint: str = Field(
        default="http://otel-collector.observability.svc.cluster.local:4317"
    )
    metrics_port: int = Field(default=9310)

    deadletter_topic: str = Field(default="market.deadletter.v1")
