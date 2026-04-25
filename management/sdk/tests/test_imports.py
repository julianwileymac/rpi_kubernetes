"""Smoke test confirming the package layout is importable."""

from __future__ import annotations


def test_configure_tracing_callable():
    from rpi_k8s_sdk import configure_tracing
    assert callable(configure_tracing)


def test_flink_client_init():
    from rpi_k8s_sdk.flink import ManagementFlinkClient
    client = ManagementFlinkClient(base_url="http://localhost:8080/api")
    try:
        assert client.base_url == "http://localhost:8080/api"
    finally:
        client.close()


def test_kafka_package_structure():
    import importlib

    mod = importlib.import_module("rpi_k8s_sdk.kafka")
    assert hasattr(mod, "AvroProducer")
    assert hasattr(mod, "AvroConsumer")
    assert hasattr(mod, "KafkaAdmin")
    assert hasattr(mod, "ApicurioClient")
