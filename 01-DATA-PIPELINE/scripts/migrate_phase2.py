"""
Phase 2 Schema Migration
========================
Creates the `platform` and `user_datasets` BigQuery datasets, all four
`platform.*` tables, and adds two new columns to `experiments.backtest_runs`.

Work order: docs/PIPELINE_SCHEMA_MIGRATION_PHASE2.md
Project:    nfl-model-471509

Usage:
    python scripts/migrate_phase2.py

Safe to re-run — all dataset/table creation is idempotent (exists_ok / IF NOT EXISTS).
The ALTER TABLE ADD COLUMN statements use IF NOT EXISTS so re-runs are harmless.
"""

import json
import logging
import sys

sys.path.insert(0, ".")

from google.cloud import bigquery

from scripts.bq_utils import PROJECT, ensure_datasets, get_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas — exact types and modes from the work order
# ---------------------------------------------------------------------------

DATASETS_SCHEMA = [
    bigquery.SchemaField("dataset_id",    "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("name",          "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("description",   "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("upload_date",   "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("file_path",     "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("join_key_type", "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("row_count",     "INT64",     mode="NULLABLE"),
    bigquery.SchemaField("column_count",  "INT64",     mode="NULLABLE"),
    bigquery.SchemaField("license_tag",   "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("status",        "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("schema_source", "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("error_message", "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("created_at",    "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("updated_at",    "TIMESTAMP", mode="REQUIRED"),
]

DATASET_COLUMNS_SCHEMA = [
    bigquery.SchemaField("dataset_id",    "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("column_name",   "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("semantic_name", "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("description",   "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("data_type",     "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("is_join_key",   "BOOL",    mode="REQUIRED"),
    bigquery.SchemaField("join_key_role", "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("null_rate",     "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("sample_values", "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("created_at",    "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("updated_at",    "TIMESTAMP", mode="REQUIRED"),
]

EXPERIMENT_CONFIGS_SCHEMA = [
    bigquery.SchemaField("experiment_id",  "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("name",           "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("description",    "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("created_at",     "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("updated_at",     "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("target",         "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("features",       "JSON",      mode="REQUIRED"),
    bigquery.SchemaField("evaluation",     "JSON",      mode="REQUIRED"),
    bigquery.SchemaField("methodology",    "JSON",      mode="REQUIRED"),
    bigquery.SchemaField("model",          "JSON",      mode="REQUIRED"),
    bigquery.SchemaField("status",         "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("gate_passed",    "BOOL",      mode="NULLABLE"),
    bigquery.SchemaField("latest_run_id",  "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("run_count",      "INT64",     mode="REQUIRED"),
]

FRAMEWORKS_SCHEMA = [
    bigquery.SchemaField("framework_id",        "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("name",                "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("description",         "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("created_at",          "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("updated_at",          "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("base_experiment_id",  "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("config_snapshot",     "JSON",      mode="REQUIRED"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_table_ddl(client: bigquery.Client, ddl: str, label: str) -> None:
    """Run a DDL statement and log the result."""
    job = client.query(ddl)
    job.result()
    logger.info(f"DDL OK: {label}")


def ensure_platform_datasets(client: bigquery.Client) -> None:
    ensure_datasets(client, ["platform", "user_datasets"])


def create_platform_datasets_table(client: bigquery.Client) -> None:
    """platform.datasets — partitioned by DATE(upload_date)."""
    full_ref = f"{PROJECT}.platform.datasets"
    table = bigquery.Table(full_ref, schema=DATASETS_SCHEMA)
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="upload_date",
    )
    client.create_table(table, exists_ok=True)
    logger.info(f"Table ready: {full_ref} (partitioned by upload_date)")


def create_platform_dataset_columns_table(client: bigquery.Client) -> None:
    """platform.dataset_columns — clustered by dataset_id."""
    full_ref = f"{PROJECT}.platform.dataset_columns"
    table = bigquery.Table(full_ref, schema=DATASET_COLUMNS_SCHEMA)
    table.clustering_fields = ["dataset_id"]
    client.create_table(table, exists_ok=True)
    logger.info(f"Table ready: {full_ref} (clustered by dataset_id)")


def create_platform_experiment_configs_table(client: bigquery.Client) -> None:
    """platform.experiment_configs — clustered by status."""
    full_ref = f"{PROJECT}.platform.experiment_configs"
    table = bigquery.Table(full_ref, schema=EXPERIMENT_CONFIGS_SCHEMA)
    table.clustering_fields = ["status"]
    client.create_table(table, exists_ok=True)
    logger.info(f"Table ready: {full_ref} (clustered by status)")


def create_platform_frameworks_table(client: bigquery.Client) -> None:
    """platform.frameworks — no partitioning or clustering."""
    full_ref = f"{PROJECT}.platform.frameworks"
    table = bigquery.Table(full_ref, schema=FRAMEWORKS_SCHEMA)
    client.create_table(table, exists_ok=True)
    logger.info(f"Table ready: {full_ref}")


def add_columns_to_backtest_runs(client: bigquery.Client) -> None:
    """
    Add experiment_config_id (STRING NULLABLE) and success_criteria (JSON NULLABLE)
    to experiments.backtest_runs. Uses IF NOT EXISTS so re-runs are safe.
    """
    ddl = f"""
        ALTER TABLE `{PROJECT}.experiments.backtest_runs`
        ADD COLUMN IF NOT EXISTS experiment_config_id STRING,
        ADD COLUMN IF NOT EXISTS success_criteria      JSON
    """
    create_table_ddl(client, ddl, "ALTER experiments.backtest_runs — add 2 columns")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def check(condition: bool, label: str, results: list) -> bool:
    status = "[PASS]" if condition else "[FAIL]"
    results.append((label, status, condition))
    print(f"  {status}  {label}")
    return condition


def get_table_columns(client: bigquery.Client, dataset: str, table: str) -> dict[str, str]:
    """Return {column_name: field_type} for a table, or {} if table doesn't exist."""
    try:
        t = client.get_table(f"{PROJECT}.{dataset}.{table}")
        return {f.name: f.field_type for f in t.schema}
    except Exception:
        return {}


def dataset_exists(client: bigquery.Client, dataset_id: str) -> bool:
    try:
        client.get_dataset(f"{PROJECT}.{dataset_id}")
        return True
    except Exception:
        return False


def table_exists(client: bigquery.Client, dataset: str, table: str) -> bool:
    try:
        client.get_table(f"{PROJECT}.{dataset}.{table}")
        return True
    except Exception:
        return False


def validate(client: bigquery.Client) -> bool:
    results = []
    print("\n" + "=" * 60)
    print("VALIDATION CHECKLIST -- Phase 2 Schema Migration")
    print("=" * 60 + "\n")

    # ------------------------------------------------------------------ #
    # 1. Datasets                                                          #
    # ------------------------------------------------------------------ #
    print("-- Datasets --")
    check(dataset_exists(client, "platform"),      "platform dataset exists in nfl-model-471509",      results)
    check(dataset_exists(client, "user_datasets"), "user_datasets dataset exists in nfl-model-471509", results)

    # ------------------------------------------------------------------ #
    # 2. platform.datasets                                                #
    # ------------------------------------------------------------------ #
    print("\n-- platform.datasets --")
    cols = get_table_columns(client, "platform", "datasets")
    check(bool(cols), "platform.datasets table exists", results)
    expected_datasets = {
        "dataset_id": "STRING", "name": "STRING", "description": "STRING",
        "upload_date": "TIMESTAMP", "file_path": "STRING", "join_key_type": "STRING",
        "row_count": "INTEGER", "column_count": "INTEGER", "license_tag": "STRING",
        "status": "STRING", "schema_source": "STRING", "error_message": "STRING",
        "created_at": "TIMESTAMP", "updated_at": "TIMESTAMP",
    }
    for col, expected_type in expected_datasets.items():
        actual = cols.get(col, "MISSING")
        # BQ returns INTEGER for INT64
        ok = actual in (expected_type, expected_type.replace("INTEGER", "INT64"))
        check(ok, f"  platform.datasets.{col} is {expected_type} (got {actual})", results)

    # ------------------------------------------------------------------ #
    # 3. platform.dataset_columns                                         #
    # ------------------------------------------------------------------ #
    print("\n-- platform.dataset_columns --")
    cols = get_table_columns(client, "platform", "dataset_columns")
    check(bool(cols), "platform.dataset_columns table exists", results)
    expected_dc = {
        "dataset_id": "STRING", "column_name": "STRING", "semantic_name": "STRING",
        "description": "STRING", "data_type": "STRING", "is_join_key": "BOOLEAN",
        "join_key_role": "STRING", "null_rate": "FLOAT", "sample_values": "STRING",
        "created_at": "TIMESTAMP", "updated_at": "TIMESTAMP",
    }
    for col, expected_type in expected_dc.items():
        actual = cols.get(col, "MISSING")
        ok = actual in (expected_type, expected_type.replace("FLOAT", "FLOAT64"),
                        expected_type.replace("BOOLEAN", "BOOL"))
        check(ok, f"  platform.dataset_columns.{col} is {expected_type} (got {actual})", results)

    # ------------------------------------------------------------------ #
    # 4. platform.experiment_configs                                      #
    # ------------------------------------------------------------------ #
    print("\n-- platform.experiment_configs --")
    cols = get_table_columns(client, "platform", "experiment_configs")
    check(bool(cols), "platform.experiment_configs table exists", results)
    expected_ec = {
        "experiment_id": "STRING", "name": "STRING", "description": "STRING",
        "created_at": "TIMESTAMP", "updated_at": "TIMESTAMP",
        "target": "STRING", "features": "JSON", "evaluation": "JSON",
        "methodology": "JSON", "model": "JSON", "status": "STRING",
        "gate_passed": "BOOLEAN", "latest_run_id": "STRING", "run_count": "INTEGER",
    }
    for col, expected_type in expected_ec.items():
        actual = cols.get(col, "MISSING")
        ok = actual in (expected_type,
                        expected_type.replace("INTEGER", "INT64"),
                        expected_type.replace("BOOLEAN", "BOOL"))
        check(ok, f"  platform.experiment_configs.{col} is {expected_type} (got {actual})", results)

    # ------------------------------------------------------------------ #
    # 5. platform.frameworks                                              #
    # ------------------------------------------------------------------ #
    print("\n-- platform.frameworks --")
    cols = get_table_columns(client, "platform", "frameworks")
    check(bool(cols), "platform.frameworks table exists", results)
    expected_fw = {
        "framework_id": "STRING", "name": "STRING", "description": "STRING",
        "created_at": "TIMESTAMP", "updated_at": "TIMESTAMP",
        "base_experiment_id": "STRING", "config_snapshot": "JSON",
    }
    for col, expected_type in expected_fw.items():
        actual = cols.get(col, "MISSING")
        check(actual == expected_type,
              f"  platform.frameworks.{col} is {expected_type} (got {actual})", results)

    # ------------------------------------------------------------------ #
    # 6. experiments.backtest_runs -- new columns                        #
    # ------------------------------------------------------------------ #
    print("\n-- experiments.backtest_runs (new columns) --")
    br_cols = get_table_columns(client, "experiments", "backtest_runs")
    check("experiment_config_id" in br_cols,
          "experiments.backtest_runs has experiment_config_id", results)
    check("success_criteria" in br_cols,
          "experiments.backtest_runs has success_criteria", results)
    if "success_criteria" in br_cols:
        check(br_cols["success_criteria"] == "JSON",
              f"  success_criteria type is JSON (got {br_cols.get('success_criteria')})", results)
    if "experiment_config_id" in br_cols:
        check(br_cols["experiment_config_id"] == "STRING",
              f"  experiment_config_id type is STRING (got {br_cols.get('experiment_config_id')})", results)

    # ------------------------------------------------------------------ #
    # 7. JSON column smoke test -- INSERT + SELECT on experiment_configs  #
    # ------------------------------------------------------------------ #
    print("\n-- JSON column smoke test --")
    test_id = "__migration_smoke_test__"
    json_ok = False
    try:
        insert_sql = f"""
            INSERT INTO `{PROJECT}.platform.experiment_configs`
              (experiment_id, name, created_at, updated_at, target,
               features, evaluation, methodology, model, status, run_count)
            VALUES
              ('{test_id}', 'smoke-test', CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(),
               'ats_cover',
               JSON '[{{"dataset":"d","column":"c","semantic_name":"x"}}]',
               JSON '{{"metric":"accuracy","success_threshold":0.55,"min_sample":100}}',
               JSON '{{"type":"walk_forward","train_seasons":[2015,2016],"test_seasons":[2017],"start_season":2015,"end_season":2017}}',
               JSON '{{"type":"xgboost","hyperparams":{{"n_estimators":100}}}}',
               'draft',
               0)
        """
        client.query(insert_sql).result()

        read_sql = f"""
            SELECT
              JSON_VALUE(evaluation, '$.metric') AS metric,
              JSON_VALUE(evaluation, '$.success_threshold') AS threshold
            FROM `{PROJECT}.platform.experiment_configs`
            WHERE experiment_id = '{test_id}'
        """
        rows = list(client.query(read_sql).result())
        if rows and rows[0]["metric"] == "accuracy":
            json_ok = True

        # Clean up test row
        client.query(
            f"DELETE FROM `{PROJECT}.platform.experiment_configs` WHERE experiment_id = '{test_id}'"
        ).result()
    except Exception as e:
        logger.warning(f"JSON smoke test failed: {e}")

    check(json_ok, "JSON columns accept valid JSON (smoke test INSERT + SELECT)", results)

    # ------------------------------------------------------------------ #
    # 8. user_datasets is empty                                           #
    # ------------------------------------------------------------------ #
    print("\n-- user_datasets emptiness --")
    try:
        tables = list(client.list_tables(f"{PROJECT}.user_datasets"))
        check(len(tables) == 0,
              f"user_datasets dataset is empty (0 tables, got {len(tables)})", results)
    except Exception as e:
        check(False, f"user_datasets.list_tables failed: {e}", results)

    # ------------------------------------------------------------------ #
    # Summary                                                             #
    # ------------------------------------------------------------------ #
    passed = sum(1 for _, _, ok in results if ok)
    failed = [(label, status) for label, status, ok in results if not ok]

    print("\n" + "=" * 60)
    print(f"RESULT: {passed}/{len(results)} checks passed")
    if failed:
        print("\nFailed checks:")
        for label, status in failed:
            print(f"  {status}  {label}")
    else:
        print("ALL CHECKS PASSED -- ready for handoff to BACKEND-API and MODELING")
    print("=" * 60 + "\n")

    return len(failed) == 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("Phase 2 Schema Migration starting")
    client = get_client()

    # Step 1 — Datasets
    logger.info("Step 1/7 — Creating datasets: platform, user_datasets")
    ensure_platform_datasets(client)

    # Step 2–5 — platform.* tables
    logger.info("Step 2/7 — Creating platform.datasets")
    create_platform_datasets_table(client)

    logger.info("Step 3/7 — Creating platform.dataset_columns")
    create_platform_dataset_columns_table(client)

    logger.info("Step 4/7 — Creating platform.experiment_configs")
    create_platform_experiment_configs_table(client)

    logger.info("Step 5/7 — Creating platform.frameworks")
    create_platform_frameworks_table(client)

    # Step 6 — ALTER experiments.backtest_runs
    logger.info("Step 6/7 — Adding columns to experiments.backtest_runs")
    add_columns_to_backtest_runs(client)

    # Step 7 — Validate
    logger.info("Step 7/7 — Running validation checklist")
    all_passed = validate(client)

    if not all_passed:
        sys.exit(1)

    logger.info("Phase 2 migration complete.")


if __name__ == "__main__":
    main()
