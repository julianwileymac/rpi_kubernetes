"""Shared configuration helpers for pipeline runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def normalize_endpoint(endpoint: str) -> str:
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        return endpoint
    return f"http://{endpoint}"


@dataclass(slots=True)
class PipelineConfig:
    """Environment-backed configuration used by Argo and Dagster tasks."""

    minio_endpoint: str = field(
        default_factory=lambda: normalize_endpoint(
            _env("PIPELINE_MINIO_ENDPOINT", "minio.data-services.svc.cluster.local:9000")
        )
    )
    minio_access_key: str = field(
        default_factory=lambda: _env("PIPELINE_MINIO_ACCESS_KEY", "minioadmin")
    )
    minio_secret_key: str = field(
        default_factory=lambda: _env("PIPELINE_MINIO_SECRET_KEY", "minioadmin123")
    )
    minio_region: str = field(default_factory=lambda: _env("PIPELINE_MINIO_REGION", "us-east-1"))
    minio_bucket_raw: str = field(
        default_factory=lambda: _env("PIPELINE_MINIO_BUCKET_RAW", "dagster-artifacts")
    )
    minio_bucket_processed: str = field(
        default_factory=lambda: _env("PIPELINE_MINIO_BUCKET_PROCESSED", "dagster-artifacts")
    )
    postgres_dsn: str = field(
        default_factory=lambda: _env(
            "PIPELINE_POSTGRES_DSN",
            "postgresql://dagster:dagster123@postgresql.data-services.svc.cluster.local:5432/dagster",
        )
    )
    source_postgres_dsn: str = field(default_factory=lambda: _env("PIPELINE_SOURCE_POSTGRES_DSN", ""))
    milvus_host: str = field(default_factory=lambda: _env("PIPELINE_MILVUS_HOST", "milvus.data-services"))
    milvus_port: int = field(default_factory=lambda: int(_env("PIPELINE_MILVUS_PORT", "19530")))
    chroma_host: str = field(default_factory=lambda: _env("PIPELINE_CHROMA_HOST", "chromadb.data-services"))
    chroma_port: int = field(default_factory=lambda: int(_env("PIPELINE_CHROMA_PORT", "8000")))
    rest_api_token: str = field(default_factory=lambda: _env("PIPELINE_REST_API_TOKEN", ""))
    http_auth_header: str = field(default_factory=lambda: _env("PIPELINE_HTTP_AUTH_HEADER", ""))
    source_s3_endpoint: str = field(
        default_factory=lambda: normalize_endpoint(
            _env("PIPELINE_S3_ENDPOINT", "minio.data-services.svc.cluster.local:9000")
        )
    )
    source_s3_access_key: str = field(
        default_factory=lambda: _env("PIPELINE_S3_ACCESS_KEY", "minioadmin")
    )
    source_s3_secret_key: str = field(
        default_factory=lambda: _env("PIPELINE_S3_SECRET_KEY", "minioadmin123")
    )
    source_s3_region: str = field(default_factory=lambda: _env("PIPELINE_S3_REGION", "us-east-1"))

    @property
    def effective_source_postgres_dsn(self) -> str:
        return self.source_postgres_dsn or self.postgres_dsn

