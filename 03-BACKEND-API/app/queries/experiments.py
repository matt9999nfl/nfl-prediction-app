"""
BigQuery queries for the /experiments and /experiments/{id}/predictions endpoints.

Partition constraint:
  experiments.backtest_predictions is partitioned/clustered on `season`.
  list_predictions() requires a season parameter and always applies it.

JSON handling:
  platform.experiment_configs stores features, evaluation, methodology, and model
  as either BigQuery JSON columns or STRING columns containing JSON text.
  _parse_json() handles both transparently.

ol_mismatch_flag (ruling #5):
  This column is Phase-1 specific and may not exist on future runs.
  check_prediction_column_exists() is called by the router before applying
  the filter; if absent, the router returns 400 / unsupported_filter.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any

from google.cloud import bigquery

from app.config import settings

logger = logging.getLogger(__name__)

PROJECT = settings.bigquery_project


# ── Helpers ───────────────────────────────────────────────────────────────────


def _run_query(
    client: bigquery.Client,
    query: str,
    params: list[bigquery.ScalarQueryParameter],
) -> list[dict[str, Any]]:
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    rows = list(client.query(query, job_config=job_config).result())
    return [dict(row) for row in rows]


def _parse_json(value: Any) -> Any:
    """Parse a BigQuery JSON or STRING field into a Python object."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    # BigQuery native JSON / STRUCT / list already decoded by the client.
    return value


def _normalize_experiment(row: dict[str, Any]) -> dict[str, Any]:
    """Parse JSON sub-fields and normalise timestamps in an experiment row."""
    row = dict(row)
    for field in ("features", "evaluation", "methodology", "model"):
        row[field] = _parse_json(row.get(field))
    # Ensure created_at is a string
    if row.get("created_at") and not isinstance(row["created_at"], str):
        row["created_at"] = row["created_at"].isoformat()
    return row


def _normalize_run(row: dict[str, Any]) -> dict[str, Any]:
    """Normalise a backtest_run row."""
    row = dict(row)
    # features may be stored as a JSON array or a BQ ARRAY<STRING>
    if isinstance(row.get("features"), str):
        row["features"] = _parse_json(row["features"]) or []
    if row.get("run_at") and not isinstance(row["run_at"], str):
        row["run_at"] = row["run_at"].isoformat()
    return row


def _experiment_select() -> str:
    """Column list mapping platform.experiment_configs → ExperimentConfig schema."""
    return """
        experiment_id,
        name,
        FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', created_at) AS created_at,
        target,
        features,
        evaluation,
        methodology,
        model,
        status,
        gate_passed
    """


def _experiment_select_aliased(alias: str = "ec") -> str:
    """Column list with table alias for queries that join other tables."""
    return f"""
        {alias}.experiment_id,
        {alias}.name,
        FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', {alias}.created_at) AS created_at,
        {alias}.target,
        {alias}.features,
        {alias}.evaluation,
        {alias}.methodology,
        {alias}.model,
        {alias}.status,
        {alias}.gate_passed
    """


# ── List experiments ──────────────────────────────────────────────────────────


def list_experiments(
    client: bigquery.Client,
    status: str | None,
    target: str | None,
    gate_passed: bool | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], bool]:
    conditions: list[str] = []
    params: list[bigquery.ScalarQueryParameter] = []

    # P5-05 fix: when status='complete' is requested, return experiments that have
    # at least one run in experiments.backtest_runs regardless of the status column
    # value.  The runner may not always set status='complete' correctly, so we
    # treat "has a run" as the ground truth for completion.
    use_run_join = False
    if status is not None:
        if status == "complete":
            use_run_join = True
        else:
            conditions.append("ec.status = @status")
            params.append(bigquery.ScalarQueryParameter("status", "STRING", status))

    if target is not None:
        conditions.append("ec.target = @target")
        params.append(bigquery.ScalarQueryParameter("target", "STRING", target))

    if gate_passed is not None:
        conditions.append("ec.gate_passed = @gate_passed")
        params.append(bigquery.ScalarQueryParameter("gate_passed", "BOOL", gate_passed))

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    params.extend([
        bigquery.ScalarQueryParameter("lim", "INT64", limit + 1),
        bigquery.ScalarQueryParameter("off", "INT64", offset),
    ])

    if use_run_join:
        # Return experiments that have at least one run in backtest_runs,
        # regardless of what the status column says on experiment_configs.
        # Note: no DISTINCT needed — experiment_id is PK in experiment_configs.
        extra_conditions = (' AND ' + ' AND '.join(conditions)) if conditions else ''
        query = f"""
            SELECT {_experiment_select_aliased("ec")}
            FROM `{PROJECT}.platform.experiment_configs` ec
            WHERE EXISTS (
                SELECT 1
                FROM `{PROJECT}.experiments.backtest_runs` br
                WHERE br.experiment_id = ec.experiment_id
            )
            {extra_conditions}
            ORDER BY ec.created_at DESC
            LIMIT @lim OFFSET @off
        """
    else:
        query = f"""
            SELECT {_experiment_select_aliased("ec")}
            FROM `{PROJECT}.platform.experiment_configs` ec
            {where}
            ORDER BY ec.created_at DESC
            LIMIT @lim OFFSET @off
        """

    rows = _run_query(client, query, params)
    has_more = len(rows) > limit
    return [_normalize_experiment(r) for r in rows[:limit]], has_more


# ── Single experiment ─────────────────────────────────────────────────────────


def get_experiment_by_id(
    client: bigquery.Client,
    experiment_id: str,
) -> dict[str, Any] | None:
    query = f"""
        SELECT {_experiment_select()}
        FROM `{PROJECT}.platform.experiment_configs`
        WHERE experiment_id = @experiment_id
        LIMIT 1
    """
    params = [bigquery.ScalarQueryParameter("experiment_id", "STRING", experiment_id)]
    rows = _run_query(client, query, params)
    return _normalize_experiment(rows[0]) if rows else None


# ── Backtest runs for an experiment ──────────────────────────────────────────


def get_runs_for_experiment(
    client: bigquery.Client,
    experiment_id: str,
) -> list[dict[str, Any]]:
    """Return all backtest runs for an experiment, newest first."""
    query = f"""
        SELECT
            run_id,
            experiment_id,
            name,
            FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', run_at) AS run_at,
            model_type,
            features,
            ats_hit_rate,
            n_games_evaluated,
            gate_passed,
            notes
        FROM `{PROJECT}.experiments.backtest_runs`
        WHERE experiment_id = @experiment_id
        ORDER BY run_at DESC
    """
    params = [bigquery.ScalarQueryParameter("experiment_id", "STRING", experiment_id)]
    rows = _run_query(client, query, params)
    return [_normalize_run(r) for r in rows]


# ── Predictions ───────────────────────────────────────────────────────────────


def check_prediction_column_exists(
    client: bigquery.Client,
    column_name: str,
) -> bool:
    """
    Check whether `column_name` exists in experiments.backtest_predictions.
    Uses INFORMATION_SCHEMA — fast metadata-only query, no table scan.
    """
    query = f"""
        SELECT COUNT(*) AS cnt
        FROM `{PROJECT}.experiments.INFORMATION_SCHEMA.COLUMNS`
        WHERE table_name  = 'backtest_predictions'
          AND column_name = @column_name
    """
    params = [bigquery.ScalarQueryParameter("column_name", "STRING", column_name)]
    rows = _run_query(client, query, params)
    return int(rows[0]["cnt"]) > 0 if rows else False


def list_predictions(
    client: bigquery.Client,
    experiment_id: str,
    season: int,           # REQUIRED — partition key, prevents full scan
    fold: int | None,
    ol_mismatch_flag: bool | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], bool]:
    """
    Return paginated predictions from the latest completed run for an experiment.

    Season is required to apply the partition filter on experiments.backtest_predictions.

    NOTE — Ambiguity flagged for PROJECT-LEAD:
      The `fold` and `ol_mismatch_flag` columns are assumed to exist in
      experiments.backtest_predictions.  If they don't yet exist in the table,
      those filter params are silently ignored (BigQuery will raise an error
      that surfaces as a 502 upstream_error).  Confirm column names with
      DATA-PIPELINE / MODELING.
    """
    # Join through backtest_runs to get the latest completed run_id
    conditions: list[str] = [
        "p.experiment_id = @experiment_id",
        "p.season = @season",
    ]
    params: list[bigquery.ScalarQueryParameter] = [
        bigquery.ScalarQueryParameter("experiment_id", "STRING", experiment_id),
        bigquery.ScalarQueryParameter("season", "INT64", season),
    ]

    if fold is not None:
        conditions.append("p.fold = @fold")
        params.append(bigquery.ScalarQueryParameter("fold", "INT64", fold))

    if ol_mismatch_flag is not None:
        conditions.append("p.ol_mismatch_flag = @ol_mismatch_flag")
        params.append(bigquery.ScalarQueryParameter("ol_mismatch_flag", "BOOL", ol_mismatch_flag))

    where = "WHERE " + " AND ".join(conditions)

    params.extend([
        bigquery.ScalarQueryParameter("lim", "INT64", limit + 1),
        bigquery.ScalarQueryParameter("off", "INT64", offset),
    ])

    # Scope to the single latest run to avoid duplicate rows across re-runs.
    query = f"""
        WITH latest_run AS (
            SELECT run_id
            FROM `{PROJECT}.experiments.backtest_runs`
            WHERE experiment_id = @experiment_id
            ORDER BY run_at DESC
            LIMIT 1
        )
        SELECT
            p.game_id,
            p.season,
            p.week,
            p.fold,
            p.home_team,
            p.away_team,
            p.predicted_home_cover_prob,
            p.predicted_side,
            p.actual_home_covered,
            p.correct
        FROM `{PROJECT}.experiments.backtest_predictions` p
        JOIN latest_run lr ON p.run_id = lr.run_id
        {where}
        ORDER BY p.season ASC, p.week ASC, p.game_id ASC
        LIMIT @lim OFFSET @off
    """

    rows = _run_query(client, query, params)
    has_more = len(rows) > limit
    return rows[:limit], has_more


# ── Phase 4 / Deliverable 3.1: Per-fold data ─────────────────────────────────


def get_latest_run_id(
    client: bigquery.Client,
    experiment_id: str,
) -> str | None:
    """Return the latest_run_id from platform.experiment_configs, or None."""
    query = f"""
        SELECT latest_run_id
        FROM `{PROJECT}.platform.experiment_configs`
        WHERE experiment_id = @experiment_id
        LIMIT 1
    """
    params = [bigquery.ScalarQueryParameter("experiment_id", "STRING", experiment_id)]
    rows = _run_query(client, query, params)
    if not rows:
        return None
    return rows[0].get("latest_run_id")


def get_per_fold_results(
    client: bigquery.Client,
    run_id: str,
) -> list[dict[str, Any]]:
    """
    Return per-season fold summary for a given run_id from
    experiments.backtest_predictions, grouped by season.

    The backtest_predictions table is partitioned on season; we supply the
    run_id filter (not a direct season filter) so BigQuery can prune as needed.
    Returns an empty list if run_id is None or no rows match.
    """
    query = f"""
        SELECT
          season,
          COUNTIF(correct = 1)                                                  AS wins,
          COUNTIF(correct = 0)                                                  AS losses,
          COUNTIF(correct IS NULL)                                              AS pushes,
          SAFE_DIVIDE(COUNTIF(correct = 1), COUNTIF(correct IS NOT NULL))       AS hit_rate,
          COUNTIF(correct IS NOT NULL)                                          AS n_games
        FROM `{PROJECT}.experiments.backtest_predictions`
        WHERE run_id = @run_id
        GROUP BY season
        ORDER BY season
    """
    params = [bigquery.ScalarQueryParameter("run_id", "STRING", run_id)]
    return _run_query(client, query, params)


# ── Phase 4 / Deliverable 3.2: Feature importance ────────────────────────────


def get_feature_importances(
    client: bigquery.Client,
    run_id: str,
) -> list[dict[str, Any]]:
    """
    Return feature importances from experiments.backtest_runs for a given run_id.

    The feature_importances column stores JSON: {"feature_name": importance, ...}.
    Returns a list of {"feature": str, "importance": float} dicts sorted
    descending by importance.  Returns an empty list if the column is null or
    the run doesn't exist.
    """
    query = f"""
        SELECT feature_importances
        FROM `{PROJECT}.experiments.backtest_runs`
        WHERE run_id = @run_id
        LIMIT 1
    """
    params = [bigquery.ScalarQueryParameter("run_id", "STRING", run_id)]
    rows = _run_query(client, query, params)
    if not rows or rows[0].get("feature_importances") is None:
        return []

    raw = _parse_json(rows[0]["feature_importances"])
    if not isinstance(raw, dict):
        return []

    items = [{"feature": k, "importance": float(v)} for k, v in raw.items()]
    items.sort(key=lambda x: x["importance"], reverse=True)
    return items


# ── Step 3: write operations ──────────────────────────────────────────────────


def _run_dml(
    client: bigquery.Client,
    query: str,
    params: list[bigquery.ScalarQueryParameter],
) -> None:
    """Execute a DML statement and block until complete."""
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    client.query(query, job_config=job_config).result()


def _streaming_insert(
    client: bigquery.Client,
    table_ref: str,
    rows: list[dict[str, Any]],
) -> None:
    errors = client.insert_rows_json(table_ref, rows)
    if errors:
        raise ValueError(f"BigQuery streaming insert errors: {errors}")


# ── Feature validation ────────────────────────────────────────────────────────


def _curated_feature_ids() -> frozenset[str]:
    """
    Return the set of valid curated feature_ids from the hardcoded catalog.
    Imported lazily to avoid a circular dependency with queries.features.
    """
    from app.queries.features import _CATALOG
    return frozenset(f["feature_id"] for f in _CATALOG)


def validate_experiment_features(
    client: bigquery.Client,
    features: list[dict[str, Any]],
) -> list[str]:
    """
    Validate each feature reference in an experiment config.

    Returns a list of human-readable error strings (empty = all valid).

    Rules:
      - dataset == "curated"          → column must be in the hardcoded catalog.
      - dataset == "user_datasets.X"  → dataset must exist with status='ready',
                                        column must exist in platform.dataset_columns.
    """
    errors: list[str] = []
    catalog_ids = _curated_feature_ids()

    # Collect all user_datasets to validate in one BQ round-trip per dataset.
    user_dataset_ids: dict[str, list[str]] = {}  # dataset_id → [column_name, ...]

    for feat in features:
        dataset: str = feat.get("dataset", "")
        column: str  = feat.get("column", "")

        if dataset == "curated":
            feature_id = f"curated.{column}"
            if feature_id not in catalog_ids:
                errors.append(f"Unknown curated feature: '{column}'")
        elif dataset.startswith("user_datasets."):
            dataset_id = dataset.removeprefix("user_datasets.")
            user_dataset_ids.setdefault(dataset_id, []).append(column)
        else:
            errors.append(f"Unknown dataset namespace: '{dataset}'")

    # Validate user dataset references.
    for dataset_id, columns in user_dataset_ids.items():
        # Check dataset exists and is ready.
        ds_rows = _run_query(
            client,
            f"""
            SELECT status FROM `{PROJECT}.platform.datasets`
            WHERE dataset_id = @dataset_id LIMIT 1
            """,
            [bigquery.ScalarQueryParameter("dataset_id", "STRING", dataset_id)],
        )
        if not ds_rows:
            errors.append(f"Dataset 'user_datasets.{dataset_id}' not found")
            continue
        if ds_rows[0]["status"] != "ready":
            errors.append(
                f"Dataset 'user_datasets.{dataset_id}' is not ready "
                f"(status='{ds_rows[0]['status']}')"
            )
            continue

        # Check each column exists.
        existing_cols = {
            r["column_name"]
            for r in _run_query(
                client,
                f"""
                SELECT column_name FROM `{PROJECT}.platform.dataset_columns`
                WHERE dataset_id = @dataset_id
                """,
                [bigquery.ScalarQueryParameter("dataset_id", "STRING", dataset_id)],
            )
        }
        for col in columns:
            if col not in existing_cols:
                errors.append(
                    f"Column '{col}' not found in dataset 'user_datasets.{dataset_id}'"
                )

    return errors


# ── Experiment config write ───────────────────────────────────────────────────


def insert_experiment_config(
    client: bigquery.Client,
    experiment_id: str,
    name: str,
    target: str,
    features: list[dict[str, Any]],
    evaluation: dict[str, Any],
    methodology: dict[str, Any],
    model: dict[str, Any],
) -> None:
    """Insert a new experiment config row with status='draft'.

    Uses DML INSERT (not streaming insert) so that subsequent DML UPDATE
    statements (e.g. set_experiment_status) can immediately see the row.
    BigQuery streaming-buffer rows are invisible to DML for up to 90 minutes.
    """
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _run_dml(
        client,
        f"""
        INSERT INTO `{PROJECT}.platform.experiment_configs`
        (experiment_id, name, created_at, updated_at, target,
         features, evaluation, methodology, model,
         status, gate_passed, run_count)
        VALUES (
            @experiment_id,
            @name,
            TIMESTAMP(@created_at),
            TIMESTAMP(@updated_at),
            @target,
            PARSE_JSON(@features),
            PARSE_JSON(@evaluation),
            PARSE_JSON(@methodology),
            PARSE_JSON(@model),
            @status,
            NULL,
            @run_count
        )
        """,
        [
            bigquery.ScalarQueryParameter("experiment_id", "STRING", experiment_id),
            bigquery.ScalarQueryParameter("name",          "STRING", name),
            bigquery.ScalarQueryParameter("created_at",    "STRING", now_str),
            bigquery.ScalarQueryParameter("updated_at",    "STRING", now_str),
            bigquery.ScalarQueryParameter("target",        "STRING", target),
            bigquery.ScalarQueryParameter("features",      "STRING", json.dumps(features)),
            bigquery.ScalarQueryParameter("evaluation",    "STRING", json.dumps(evaluation)),
            bigquery.ScalarQueryParameter("methodology",   "STRING", json.dumps(methodology)),
            bigquery.ScalarQueryParameter("model",         "STRING", json.dumps(model)),
            bigquery.ScalarQueryParameter("status",        "STRING", "draft"),
            bigquery.ScalarQueryParameter("run_count",     "INT64",  0),
        ],
    )


def set_experiment_status(
    client: bigquery.Client,
    experiment_id: str,
    status: str,
) -> None:
    """DML UPDATE — immediately visible to subsequent reads."""
    _run_dml(
        client,
        f"""
        UPDATE `{PROJECT}.platform.experiment_configs`
        SET    status        = @status
        WHERE  experiment_id = @experiment_id
        """,
        [
            bigquery.ScalarQueryParameter("status",        "STRING", status),
            bigquery.ScalarQueryParameter("experiment_id", "STRING", experiment_id),
        ],
    )


# ── Run trigger ───────────────────────────────────────────────────────────────


def insert_initial_run(
    client: bigquery.Client,
    experiment_id: str,
    run_id: str,
    model_type: str,
    feature_columns: list[str],
) -> None:
    """
    Insert the initial backtest_runs row at trigger time.

    Metrics (ats_hit_rate, gate_passed, etc.) are null — the MODELING runner
    populates them when the job completes.  The runner also writes completed_at
    and error_message via DML UPDATE once the job finishes.
    """
    now = datetime.now(timezone.utc)
    now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    _streaming_insert(
        client,
        f"{PROJECT}.experiments.backtest_runs",
        [{
            "run_id":             run_id,
            "experiment_id":      experiment_id,
            "name":               f"Run {now.strftime('%Y-%m-%d %H:%M UTC')}",
            "run_at":             now_str,
            "model_type":         model_type,
            "features":           json.dumps(feature_columns),
            "status":             "running",
            "ats_hit_rate":       None,
            "ats_record_wins":    None,
            "ats_record_losses":  None,
            "ats_record_pushes":  None,
            "n_games_evaluated":  None,
            "gate_passed":        None,
            "training_window_years": None,
            "seasons_evaluated":  None,
            "folds_complete":     None,
            "folds_total":        None,
            "error_message":      None,
            "notes":              None,
            "success_criteria":   None,
        }],
    )


def trigger_experiment_runner(
    experiment_id: str,
    run_id: str,
) -> None:
    """
    Trigger the Cloud Run Job for the experiment runner.

    Makes a direct HTTP call to the Cloud Run Jobs API to execute the
    nfl-experiment-runner job with environment variable overrides for
    EXPERIMENT_CONFIG_ID and NFL_RUN_ID.

    Args:
        experiment_id: UUID of the experiment config to run
        run_id: UUID of this run (for tracking in BigQuery)
    """
    import google.auth
    import google.auth.transport.requests
    import requests as http_requests

    try:
        # Get default credentials (uses service account credentials in Cloud Run)
        credentials, project = google.auth.default()
        credentials.refresh(google.auth.transport.requests.Request())

        region = "us-central1"
        job_name = "nfl-experiment-runner"
        url = (
            f"https://{region}-run.googleapis.com/apis/run.googleapis.com/v1/"
            f"namespaces/{project}/jobs/{job_name}:run"
        )

        payload = {
            "overrides": {
                "containerOverrides": [{
                    "env": [
                        {"name": "EXPERIMENT_CONFIG_ID", "value": experiment_id},
                        {"name": "NFL_RUN_ID", "value": run_id},
                    ]
                }]
            }
        }

        resp = http_requests.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {credentials.token}"},
            timeout=10,
        )
        resp.raise_for_status()

        execution_name = resp.json().get("metadata", {}).get("name", "unknown")
        logger.info(
            "Cloud Run Job execution created for experiment %s (run %s): %s",
            experiment_id, run_id, execution_name,
        )
    except Exception as exc:
        logger.error(
            "Failed to trigger experiment runner for %s (run %s): %s",
            experiment_id, run_id, exc, exc_info=True,
        )
        raise


# ── Status polling ────────────────────────────────────────────────────────────


def get_experiment_run_status(
    client: bigquery.Client,
    experiment_id: str,
) -> dict[str, Any] | None:
    """
    Read current run status from platform.experiment_configs + latest backtest_runs row.

    Returns None if the experiment doesn't exist.

    Phase 2 note:
      completed_at, folds_complete, folds_total, and error_message are returned as
      null until MODELING's runner populates them.  The query tries to select these
      columns; if they don't yet exist in the BQ schema, the whole query will fail
      and the router returns 502 — MODELING should add them before the runner ships.
    """
    query = f"""
        SELECT
            ec.experiment_id,
            ec.status,
            br.run_id,
            FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', br.run_at)        AS started_at,
            FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', br.completed_at)  AS completed_at,
            br.folds_complete,
            br.folds_total,
            br.error_message
        FROM `{PROJECT}.platform.experiment_configs` ec
        LEFT JOIN (
            SELECT
                run_id,
                experiment_id,
                run_at,
                completed_at,
                folds_complete,
                folds_total,
                error_message
            FROM `{PROJECT}.experiments.backtest_runs`
            WHERE experiment_id = @experiment_id
            ORDER BY run_at DESC
            LIMIT 1
        ) br ON ec.experiment_id = br.experiment_id
        WHERE ec.experiment_id = @experiment_id
        LIMIT 1
    """
    params = [bigquery.ScalarQueryParameter("experiment_id", "STRING", experiment_id)]
    rows = _run_query(client, query, params)
    return rows[0] if rows else None
