"""Convenience wrappers for using the rpi_kubernetes platform from AQP code.

The Agentic Quant Platform (`agentic_quant_platform`) runs locally on a
developer laptop most of the time, but its production data plane lives in
this Kubernetes cluster.  The helpers in this module let an AQP user start
a session, hand off a backtest to the in-cluster Argo runners, and register
a trained model with MLflow + KServe in one or two lines:

    from rpi_k8s_sdk.aqp import aqp_session, register_model

    with aqp_session():
        register_model("mlflow-run-id-here", strategy_name="momentum-50d")

The session context configures tracing, brings up the necessary tunnels,
and exports the right env vars so AQP's own clients (MLflow, MinIO,
Iceberg) can reach the cluster.
"""

from __future__ import annotations

import contextlib
import logging
import os
from typing import Any, Iterator

from .access import LocalAccessSettings, load_settings
from .mlflow import MLflowClient
from .pipelines import ArgoPipelineClient, PipelineRun
from .serving import ModelStore, kserve_inferenceservice_manifest
from .tracing import configure_tracing
from .tunnels import LocalTunnelManager

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def aqp_session(
    *,
    service_name: str = "aqp-local",
    settings: LocalAccessSettings | None = None,
    tunnels: bool | None = None,
) -> Iterator[LocalAccessSettings]:
    """Configure tracing + tunnels + env for an AQP local session.

    Parameters
    ----------
    service_name:
        Reported in OpenTelemetry spans (``service.name``).
    settings:
        Pre-built :class:`LocalAccessSettings`.  When ``None``, loads from
        environment via :func:`load_settings`.
    tunnels:
        Whether to start ``kubectl port-forward`` tunnels to the cluster
        (MLflow, OTel, Argo, DataHub).  When ``None``, follows
        ``settings.auto_tunnel``.
    """

    active = settings or load_settings()
    if tunnels is None:
        tunnels = active.auto_tunnel

    # Export the canonical env vars so AQP's own ``aqp.config.settings``
    # reads pick them up.
    for key, value in active.to_env().items():
        os.environ.setdefault(key, value)
    # Also export the AQP-namespaced aliases so any AQP_OTEL_* config
    # consumers keep working without explicit overrides.
    os.environ.setdefault("AQP_OTEL_ENDPOINT", active.otlp_endpoint)
    os.environ.setdefault("AQP_OTEL_SERVICE_NAME", service_name)

    configure_tracing(
        service_name=service_name,
        endpoint=active.otlp_endpoint,
        namespace="aqp",
        instrument_kafka=False,
        instrument_httpx=True,
    )

    if not tunnels:
        yield active
        return

    manager = LocalTunnelManager(active)
    services = [active.datahub_gms, active.otel_collector, active.argo_server]
    with manager.started(*services):
        logger.info("AQP session tunnels online: %s", [s.name for s in services])
        yield active


def submit_backtest(
    *,
    template_name: str = "aqp-backtest",
    name: str = "aqp-run",
    parameters: dict[str, str] | None = None,
    namespace: str | None = None,
    settings: LocalAccessSettings | None = None,
) -> PipelineRun:
    """Submit an AQP backtest as an Argo Workflow.

    Thin wrapper around :class:`ArgoPipelineClient.submit_template` so AQP
    code does not have to import the lower-level pipeline API.
    """

    client = ArgoPipelineClient(settings=settings)
    return client.submit_template(
        template_name=template_name,
        name=name,
        parameters=parameters or {},
        namespace=namespace,
    )


def register_model(
    run_id: str,
    *,
    strategy_name: str,
    artifact_path: str = "model",
    runtime: str = "sklearn",
    deploy: bool = True,
    settings: LocalAccessSettings | None = None,
) -> dict[str, Any]:
    """Promote an MLflow run into a KServe-served model.

    Steps
    -----
    1. Pull the artifact directory from MLflow into the cluster's model bucket.
    2. Optionally apply a KServe ``InferenceService`` manifest pointing at the
       new ``s3://`` URI.

    Returns the artifact + manifest summary so callers can log it.
    """

    active = settings or load_settings()
    store = ModelStore(active)
    artifact = store.from_mlflow_run(run_id=run_id, artifact_path=artifact_path)
    manifest = kserve_inferenceservice_manifest(
        name=strategy_name,
        model_uri=artifact.s3_uri,
        runtime=runtime,
    )
    summary: dict[str, Any] = {
        "artifact": {
            "model_id": artifact.model_id,
            "bucket": artifact.bucket,
            "prefix": artifact.prefix,
            "s3_uri": artifact.s3_uri,
        },
        "manifest": manifest,
    }
    if deploy:
        applied = store.deploy_to_kserve(manifest)
        summary["status"] = applied.get("status")
        summary["deployed"] = True
    else:
        summary["deployed"] = False
    return summary


def latest_mlflow_run(experiment_name: str, *, settings: LocalAccessSettings | None = None) -> str | None:
    """Return the most recent MLflow run ID under ``experiment_name``."""

    client = MLflowClient(settings or load_settings())
    runs = client.list_runs(experiment_name=experiment_name, max_results=1)
    if not runs:
        return None
    return runs[0].run_id
