"""
BigQuery helpers shared across all ingest scripts.
"""
import logging
import pandas as pd
from google.cloud import bigquery

logger = logging.getLogger(__name__)

PROJECT = "nfl-model-471509"


def get_client() -> bigquery.Client:
    return bigquery.Client(project=PROJECT)


def normalize_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Coerce mixed-type columns to STRING so BigQuery schema never conflicts
    across seasons. Raw landing tables are source-faithful; type consistency
    matters more than native numeric types at this layer.

    Rules:
    - object dtype  → string (catches mixed int/str columns like nfl_detail_id)
    - float columns with only whole numbers stay float (BQ handles them fine)
    - bool columns stay bool
    - explicit int/float dtypes stay as-is
    """
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].where(df[col].notna(), None)
            df[col] = df[col].astype(str)
            df[col] = df[col].where(~df[col].isin(["nan", "None", "NaT", "<NA>"]), None)
    return df


def ensure_datasets(client: bigquery.Client, datasets: list[str]) -> None:
    for ds_id in datasets:
        ref = bigquery.Dataset(f"{PROJECT}.{ds_id}")
        ref.location = "US"
        client.create_dataset(ref, exists_ok=True)
        logger.info(f"Dataset ready: {ds_id}")


def load_partition(
    client: bigquery.Client,
    df,
    table_id: str,
    partition_field: str,
    partition_value: int,
    clustering_fields: list[str] | None = None,
) -> None:
    """
    Replace a single partition in a BigQuery table.
    table_id format: 'dataset.table'
    """
    full_table = f"{PROJECT}.{table_id}${partition_value}"

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        time_partitioning=bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field=None,  # integer-range partitioning set via DDL; use range below
        ),
    )

    # BigQuery Python client doesn't support integer range partitioning natively
    # via load job for new tables, so we use WRITE_TRUNCATE on the decorated
    # partition reference (dataset.table$YEAR) which works for integer partitions
    # created via the schema below.
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION],
    )

    job = client.load_table_from_dataframe(df, full_table, job_config=job_config)
    job.result()
    logger.info(f"Loaded {len(df)} rows → {full_table}")


def ensure_table_with_schema(
    client: bigquery.Client,
    table_ref: str,
    schema: list[bigquery.SchemaField],
    partition_field: str,
    clustering_fields: list[str] | None = None,
) -> None:
    """
    Create a BigQuery table with integer range partitioning if it doesn't exist.
    table_ref: 'dataset.table'
    """
    full_ref = f"{PROJECT}.{table_ref}"
    table = bigquery.Table(full_ref, schema=schema)
    table.range_partitioning = bigquery.RangePartitioning(
        field=partition_field,
        range_=bigquery.PartitionRange(start=2010, end=2040, interval=1),
    )
    if clustering_fields:
        table.clustering_fields = clustering_fields
    client.create_table(table, exists_ok=True)
    logger.info(f"Table ready: {full_ref}")
