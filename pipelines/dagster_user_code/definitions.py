"""Dagster definitions for pipeline orchestrator MVP."""

from __future__ import annotations

from dagster import Definitions, ScheduleDefinition, define_asset_job

from .assets import (
    cdc_incremental_sync,
    hybrid_argo_heavy_transform,
    minio_to_postgres_curated,
    vectorize_to_milvus_chroma,
)
from .rag_assets import (
    graphrag_knowledge_base,
    ingest_csv_data,
    ingest_pdf_documents,
)

minio_to_postgres_job = define_asset_job(
    name="minio_to_postgres_job",
    selection=[minio_to_postgres_curated],
)

vectorization_job = define_asset_job(
    name="vectorization_job",
    selection=[vectorize_to_milvus_chroma],
)

cdc_job = define_asset_job(
    name="cdc_job",
    selection=[cdc_incremental_sync],
)

hybrid_transform_job = define_asset_job(
    name="hybrid_transform_job",
    selection=[hybrid_argo_heavy_transform],
)

cdc_hourly_schedule = ScheduleDefinition(
    name="cdc_hourly_schedule",
    cron_schedule="15 * * * *",
    job=cdc_job,
    run_config={
        "ops": {
            "cdc_incremental_sync": {
                "config": {
                    "pipeline_name": "cdc-source-events",
                    "source_table": "source_events",
                    "primary_key": "id",
                    "updated_at_column": "updated_at",
                    "batch_size": 500,
                    "output_prefix": "cdc/hourly",
                    "output_bucket": "dagster-artifacts",
                }
            }
        }
    },
)

vector_daily_schedule = ScheduleDefinition(
    name="vector_daily_schedule",
    cron_schedule="0 2 * * *",
    job=vectorization_job,
    run_config={
        "ops": {
            "vectorize_to_milvus_chroma": {
                "config": {
                    "source_key": "processed/heavy/sample.json",
                    "source_bucket": "dagster-artifacts",
                    "collection_name": "pipeline_documents",
                    "pipeline_name": "vector-sync",
                    "text_field": "text",
                }
            }
        }
    },
)

pdf_ingest_job = define_asset_job(
    name="pdf_ingest_job",
    selection=[ingest_pdf_documents],
)

csv_ingest_job = define_asset_job(
    name="csv_ingest_job",
    selection=[ingest_csv_data],
)

graphrag_job = define_asset_job(
    name="graphrag_job",
    selection=[graphrag_knowledge_base],
)

defs = Definitions(
    assets=[
        minio_to_postgres_curated,
        vectorize_to_milvus_chroma,
        cdc_incremental_sync,
        hybrid_argo_heavy_transform,
        ingest_pdf_documents,
        ingest_csv_data,
        graphrag_knowledge_base,
    ],
    jobs=[
        minio_to_postgres_job,
        vectorization_job,
        cdc_job,
        hybrid_transform_job,
        pdf_ingest_job,
        csv_ingest_job,
        graphrag_job,
    ],
    schedules=[cdc_hourly_schedule, vector_daily_schedule],
)

