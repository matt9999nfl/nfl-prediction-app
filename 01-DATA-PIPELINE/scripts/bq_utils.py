"""
BigQuery helpers shared across all ingest scripts.
"""
import io
import logging
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from google.cloud import bigquery

logger = logging.getLogger(__name__)

PROJECT = "nfl-model-471509"

# Column name suffixes/exact names that identify player/entity ID columns.
# In nflfastR data these start as int64 (simple numeric IDs in 2015) but
# become UUID strings in later seasons.  We always store them as STRING so
# BQ schema never conflicts across partitions.
# jersey_number is nominally numeric but typed as object/string in some seasons
# (non-numeric values or mixed), so we always normalise it to STRING.
_ID_COL_SUFFIXES = ("_player_id", "_player_name", "nfl_detail_id", "jersey_number")

_NULL_STRINGS = {"nan", "None", "NaT", "<NA>", "none", "NaN"}


def _is_id_column(col: str) -> bool:
    lower = col.lower()
    return any(lower.endswith(s) or lower == s for s in _ID_COL_SUFFIXES)


def get_client() -> bigquery.Client:
    return bigquery.Client(project=PROJECT)


def normalize_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Coerce mixed-type columns to STRING so BigQuery schema never conflicts
    across seasons. Raw landing tables are source-faithful; type consistency
    matters more than native numeric types at this layer.

    Rules:
    - object dtype            → string (existing behaviour)
    - int64/float64 columns
      whose names end in
      _player_id / _player_name
      or equal nfl_detail_id  → string  (these flip to UUID strings in 2021+)
    - bool / other numeric    → left as-is
    """
    df = df.copy()
    null_strings = _NULL_STRINGS

    for col in df.columns:
        series = df[col]

        # ── Player / entity ID columns that can change numeric→UUID ──────────
        if _is_id_column(col) and series.dtype.kind in ("i", "u", "f"):
            # Capture nulls first (float64 can have NaN; int64 cannot)
            null_mask = series.isna()
            if series.dtype.kind in ("i", "u"):
                # True int64 — safe to cast directly
                df[col] = series.astype(str)
            else:
                # float64 — convert whole numbers cleanly: "1234.0" → "1234"
                df[col] = series.apply(
                    lambda x: str(int(x)) if pd.notna(x) else None
                )
            df.loc[null_mask, col] = None
            df[col] = df[col].where(~df[col].isin(null_strings), None)
            continue

        # ── Standard object → string normalisation ───────────────────────────
        if series.dtype == object:
            df[col] = series.where(series.notna(), None)
            df[col] = df[col].astype(str)
            df[col] = df[col].where(~df[col].isin(null_strings), None)

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


def load_df_to_bq(
    client: bigquery.Client,
    df: pd.DataFrame,
    full_table: str,
    job_config: bigquery.LoadJobConfig,
):
    """
    Load a DataFrame into BigQuery via pyarrow, converting any all-null columns
    (pa.null() type) to pa.string() first.

    This is the definitive fix for the INTEGER→STRING schema conflict:
    - In early seasons (e.g. 2015) some player-ID columns are entirely NULL.
    - pandas converts these to float64 NaN; after normalize_dtypes they become
      object dtype with all None values.
    - pyarrow converts all-None object columns to pa.null() (the 'null' type).
    - BigQuery's autodetect sees pa.null() and infers INTEGER (or an unknown
      type that later conflicts with STRING in later seasons).
    - By casting pa.null() → pa.string() before loading, BQ always gets STRING.
    """
    arrow_table = pa.Table.from_pandas(df, preserve_index=False)

    new_fields = []
    new_columns = []
    for i, field in enumerate(arrow_table.schema):
        col = arrow_table.column(i)
        if pa.types.is_null(field.type):
            # All-null columns → STRING so BQ doesn't lock them as INTEGER.
            new_fields.append(field.with_type(pa.string()))
            new_columns.append(col.cast(pa.string()))
        elif pa.types.is_integer(field.type) and field.name != "season":
            # Integer columns (other than the partition key) → FLOAT64 so the
            # schema stays consistent across seasons. Some columns appear as
            # int64 in early seasons (all-whole-number values, no NaN) and
            # float64 in later seasons (fractional values or NaN present).
            # BQ rejects INTEGER→FLOAT changes once the table schema is locked.
            # The raw landing layer doesn't need strict integer semantics.
            new_fields.append(field.with_type(pa.float64()))
            new_columns.append(col.cast(pa.float64()))
        else:
            new_fields.append(field)
            new_columns.append(col)

    fixed_schema = pa.schema(new_fields)
    fixed_table = pa.table(
        {f.name: new_columns[i] for i, f in enumerate(new_fields)},
        schema=fixed_schema,
    )

    # Serialize to Parquet in memory — this preserves the Arrow schema so BQ
    # sees pa.string() for null columns instead of guessing INTEGER.
    # (BQ Client 3.x has no load_table_from_arrow; load_table_from_file works.)
    buf = io.BytesIO()
    pq.write_table(fixed_table, buf)
    buf.seek(0)

    # Parquet loads derive schema from the file — autodetect and schema hints
    # are not applicable and can cause errors. Override them here.
    job_config.source_format = bigquery.SourceFormat.PARQUET
    job_config.autodetect = False
    job_config.schema = None
    job = client.load_table_from_file(buf, full_table, job_config=job_config)
    job.result()
    return job


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
