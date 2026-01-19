"""
Configuration management using Pydantic Settings.

Environment variables can override all settings.
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class KubernetesSettings(BaseSettings):
    """Kubernetes connection settings."""

    model_config = SettingsConfigDict(env_prefix="K8S_")

    kubeconfig_path: Optional[str] = Field(
        default=None,
        description="Path to kubeconfig file. If None, uses in-cluster config.",
    )
    context: Optional[str] = Field(
        default=None,
        description="Kubernetes context to use. If None, uses current context.",
    )
    namespace: str = Field(
        default="default",
        description="Default namespace for operations.",
    )
    auto_discover: bool = Field(
        default=True,
        description="Auto-discover local clusters (in-cluster, env KUBECONFIG, default kubeconfig).",
    )
    extra_kubeconfig_paths: list[str] = Field(
        default=[],
        description="Additional kubeconfig paths to try during auto-discovery.",
    )
    context_preference: list[str] = Field(
        default=[],
        description="Preferred contexts to try (in order) when auto-detecting.",
    )


class TelemetrySettings(BaseSettings):
    """OpenTelemetry settings."""

    model_config = SettingsConfigDict(env_prefix="OTEL_")

    enabled: bool = Field(default=True, description="Enable OpenTelemetry tracing")
    service_name: str = Field(default="rpi-k8s-management", description="Service name for traces")
    exporter_endpoint: str = Field(
        default="http://otel-collector.observability:4317",
        description="OTLP exporter endpoint",
    )


class MLFlowSettings(BaseSettings):
    """MLFlow settings."""

    model_config = SettingsConfigDict(env_prefix="MLFLOW_")

    enabled: bool = Field(default=True, description="Enable MLFlow integration")
    tracking_uri: str = Field(
        default="http://mlflow.ml-platform:5000",
        description="MLFlow tracking server URI",
    )


class HardwareSettings(BaseSettings):
    """Hardware monitoring settings."""

    model_config = SettingsConfigDict(env_prefix="HARDWARE_")

    ssh_user: str = Field(default="pi", description="SSH username for RPi nodes")
    ssh_key_path: Optional[str] = Field(
        default=None,
        description="Path to SSH private key",
    )
    ssh_timeout: int = Field(default=10, description="SSH connection timeout in seconds")
    metrics_interval: int = Field(
        default=30,
        description="Interval for collecting hardware metrics (seconds)",
    )


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Application settings
    debug: bool = Field(default=False, description="Enable debug mode")
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8080, description="Server port")
    log_level: str = Field(default="INFO", description="Logging level")
    cors_origins: list[str] = Field(
        default=["*"],
        description="Allowed CORS origins",
    )

    # Cluster information
    cluster_name: str = Field(default="rpi-k8s-cluster", description="Cluster name")

    # Nested settings
    kubernetes: KubernetesSettings = Field(default_factory=KubernetesSettings)
    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)
    mlflow: MLFlowSettings = Field(default_factory=MLFlowSettings)
    hardware: HardwareSettings = Field(default_factory=HardwareSettings)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
