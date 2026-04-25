"""rpi_k8s_sdk - streaming + Flink control plane SDK for rpi_kubernetes."""

from .tracing import configure_tracing

__all__ = ["configure_tracing"]
__version__ = "0.1.0"
