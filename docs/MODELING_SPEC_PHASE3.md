# MODELING Spec — Phase 3

**Owner:** PROJECT-LEAD
**Assigned to:** MODELING
**Date:** 2026-05-06
**Status:** Active

---

## Read These First

1. `../02-MODELING/instructions.md` — your scope and operating principles
2. `../02-MODELING/backtests/run_experiment.py` — the runner you are fixing and extending
3. `../02-MODELING/backtests/bq_writer.py` — the BigQuery output layer you are extending
4. `../00-PROJECT-LEAD/ROADMAP.md` — the known pre-Phase-3 fix that has been waiting

---

## What Phase 2 Delivered

`backtests/run_experiment.py` is a complete, config-driven experiment runner. It reads `EXPERIMENT_CONFIG_ID` from the environment, fetches the config from `platform.experiment_configs`, builds a feature matrix dynamically, runs walk-forward backtests, writes results to `experiments.backtest_runs` and `experiments.backtest_predictions`, and updates the config status in a `finally` block.

Two known gaps were carried into Phase 3:

1. **Join-key column names are hardcoded** — the runner reads `join_key_type` correctly from `platform.datasets` but then assumes the actual column names in the user's uploaded table are literally `team`, `season`, `week`, and `game_id`. This breaks silently if the user's columns have different names.
2. **Feature importance scores are not written to BigQuery** — the XGBoost model computes them internally but they're never persisted. FRONTEND and BACKEND-API need them to surface importance displays.

Phase 3 also adds a third deliverable: implement `run_production_refresh.py` (DEVOPS left a stub that exits 1).

---

## Deliverable 1 — Fix the Join-Key Column Name Bug

### What's broken

In `backtests/run_experiment.py`, the function `_join_user_dataset()` currently hardcodes the join column names:

```python
# For team_season_week datasets (line ~363):
join_cols = ["team", "season", "week"]

# For game_id datasets (line ~347):
col_select = ", ".join(f"`{c}`" for c in ["game_id"] + raw_col_names)
```

The real column names in the user's BigQuery table are stored in `platform.datasets.join_key_columns` (a JSON field set when the user submits `PUT /api/v1/datasets/{id}/schema`). For example:

```json
{
  "join_key_type": "team_season_week",
  "join_key_columns": {
    "team": "team_name",
    "season": "year",
    "week": "week_number"
  }
}
```

If the user's file has a column called `year` instead of `season`, the join currently produces all-null columns silently.

### Where `join_key_columns` lives in BigQuery

`platform.datasets` table, column `join_key_columns` — stored as JSON. The `_resolve_join_key_type()` function already queries this table. Extend it.

### The fix

**Step 1:** Extend `_resolve_join_key_type()` (or rename it `_resolve_dataset_join_info()`) to also return `join_key_columns`:

```python
def _resolve_dataset_join_info(
    client: bigquery.Client,
    dataset_id: str,
) -> tuple[str, dict[str, str]]:
    """
    Returns (join_key_type, join_key_columns) from platform.datasets.

    join_key_columns maps semantic names → actual column names in the BQ table.
    E.g. {"team": "team_name", "season": "year", "week": "week_number"}

    Falls back to type='team_season_week' and identity mapping if row not found.
    """
    query = f"""
        SELECT join_key_type, join_key_columns
        FROM `{DATASETS_TABLE}`
        WHERE dataset_id = @dataset_id
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("dataset_id", "STRING", dataset_id)]
    )
    rows = list(client.query(query, job_config=job_config).result())

    if not rows:
        logger.warning(
            f"join_key info not found for dataset_id={dataset_id!r}; "
            "defaulting to team_season_week with identity column mapping"
        )
        return "team_season_week", {}

    row = dict(rows[0])
    jkt = row.get("join_key_type") or "team_season_week"

    raw_jkc = row.get("join_key_columns")
    if isinstance(raw_jkc, str):
        try:
            import json
            jkc = json.loads(raw_jkc)
        except Exception:
            jkc = {}
    elif isinstance(raw_jkc, dict):
        jkc = raw_jkc
    else:
        jkc = {}

    return jkt, jkc
```

**Step 2:** Update `_join_user_dataset()` to use the returned `join_key_columns`. When `join_key_columns` has a mapping, use the mapped column name; when it's absent or empty, fall back to the semantic name (preserves backward compat with existing manually-loaded data that does use the expected column names):

```python
def _join_user_dataset(
    client: bigquery.Client,
    game_features: pd.DataFrame,
    dataset_id: str,
    columns: list[dict],
) -> pd.DataFrame:
    raw_col_names  = [c["column"]        for c in columns]
    semantic_names = [c["semantic_name"] for c in columns]
    col_rename     = dict(zip(raw_col_names, semantic_names))

    join_key_type, join_key_columns = _resolve_dataset_join_info(client, dataset_id)
    bq_table = f"`{PROJECT}.user_datasets.{dataset_id}`"

    if join_key_type == "game_id":
        actual_game_id_col = join_key_columns.get("game_id", "game_id")
        col_select = ", ".join(
            f"`{c}`" for c in [actual_game_id_col] + raw_col_names
        )
        query = f"SELECT {col_select} FROM {bq_table}"
        ud_df = client.query(query).to_dataframe()
        if actual_game_id_col != "game_id":
            ud_df = ud_df.rename(columns={actual_game_id_col: "game_id"})
        ud_df = ud_df.rename(columns=col_rename)
        game_features = game_features.merge(ud_df, on="game_id", how="left")
        for sname in semantic_names:
            if game_features[sname].dtype.kind in ("f", "i"):
                game_features[sname] = game_features[sname].fillna(0)

    elif join_key_type in ("team_season_week", "player_season_week"):
        actual_team_col   = join_key_columns.get("team",   "team")
        actual_season_col = join_key_columns.get("season", "season")
        actual_week_col   = join_key_columns.get("week",   "week")
        actual_join_cols  = [actual_team_col, actual_season_col, actual_week_col]
        col_select = ", ".join(f"`{c}`" for c in actual_join_cols + raw_col_names)
        query = f"SELECT {col_select} FROM {bq_table}"
        ud_df = client.query(query).to_dataframe()
        # Normalise to semantic join column names so the merge always works
        ud_df = ud_df.rename(columns={
            actual_team_col:   "team",
            actual_season_col: "season",
            actual_week_col:   "week",
        })
        ud_df = ud_df.rename(columns=col_rename)

        for prefix, team_col in [("home", "home_team"), ("away", "away_team")]:
            ud_prefixed = (
                ud_df[["team", "season", "week"] + semantic_names]
                .rename(columns={"team": team_col} | {s: f"{prefix}_{s}" for s in semantic_names})
            )
            game_features = game_features.merge(
                ud_prefixed, on=[team_col, "season", "week"], how="left"
            )
            for s in semantic_names:
                col = f"{prefix}_{s}"
                if col in game_features and game_features[col].dtype.kind in ("f", "i", "u"):
                    game_features[col] = game_features[col].fillna(0)
    else:
        logger.warning(
            f"Unrecognised join_key_type={join_key_type!r} for dataset "
            f"{dataset_id!r}; skipping join."
        )

    logger.info(
        f"Joined user dataset {dataset_id!r} "
        f"(join_key={join_key_type}, actual_cols={join_key_columns}, feature_cols={semantic_names})"
    )
    return game_features
```

**Step 3:** Update all callers of `_resolve_join_key_type()` to use `_resolve_dataset_join_info()` instead. There are two call sites in `run_experiment.py` — the one inside `_join_user_dataset` (just fixed above) and one at line ~467 that calls `_resolve_join_key_type` again to determine model feature column prefixing. Unify these.

### Backward compatibility note

If `join_key_columns` is missing or empty (e.g. for datasets loaded before this field was populated), fall through to the identity mapping (semantic name = actual column name). This preserves behavior for the two Phase 1 experiments already in BigQuery.

---

## Deliverable 2 — Write Feature Importance Scores to BigQuery

### What to write

After each walk-forward fold completes, the XGBoost model has a `.feature_importances_` array aligned to its feature list. Aggregate these across folds (mean importance per feature), then write to BigQuery alongside the run record.

### Schema change

Add a new column to `experiments.backtest_runs`:

```python
# In backtests/bq_writer.py, add to RUNS_SCHEMA:
bigquery.SchemaField("feature_importances", "JSON", mode="NULLABLE"),
```

The JSON value is a dict mapping feature name → mean importance across folds:
```json
{
  "home_ol_pass_epa_per_att": 0.142,
  "away_ol_pass_epa_per_att": 0.118,
  "rest_differential": 0.089,
  ...
}
```

### Where to compute

In `backtests/walk_forward.py`, the `run_walk_forward()` function trains the model on each fold. After each fold's model is trained, capture `model.get_feature_importances()` (or `model.model.feature_importances_` for the XGBoost wrapper). Accumulate across folds and return the mean as part of the run result dict.

If the model class doesn't expose feature importances (e.g. future logistic regression), return `None` for that field — the column is NULLABLE.

### Add to bq_writer

In `write_backtest_run()`, include `feature_importances` in the row dict:

```python
row["feature_importances"] = json.dumps(feature_importances) if feature_importances else None
```

Also add `_alter_runs_table_phase3()` (idempotent DDL, called from `setup_experiments_tables()`):

```python
def _alter_runs_table_phase3(client: bigquery.Client) -> None:
    """Add feature_importances column if missing."""
    ddl = f"""
        ALTER TABLE `{RUNS_TABLE}`
        ADD COLUMN IF NOT EXISTS feature_importances JSON
    """
    client.query(ddl).result()
    logger.info("backtest_runs: feature_importances column ensured")
```

### BACKEND-API endpoint (future)

BACKEND-API will add a `GET /api/v1/experiments/{id}/feature-importance` endpoint once this column is populated. BACKEND-API needs to know the exact JSON field name (`feature_importances`) and that it lives on `experiments.backtest_runs`. Flag this to PROJECT-LEAD when you deliver this item.

---

## Deliverable 3 — Implement `run_production_refresh.py`

DEVOPS left a stub at `02-MODELING/backtests/run_production_refresh.py` that currently exits with code 1. You must implement it. This is the Cloud Run Job that Cloud Scheduler fires every Tuesday at 9am ET to refresh predictions for gate-passed experiments.

### What it does

1. Queries `platform.experiment_configs` for all experiments where `gate_passed = true` AND `status != 'running'`
2. For each result, creates a Cloud Run Job execution for `nfl-experiment-runner` with `EXPERIMENT_CONFIG_ID` set to that experiment's UUID
3. Logs which experiments were triggered and which were skipped (already running)
4. Exits 0 if all triggers succeeded; exits 1 if any failed

### Reference implementation

Use the exact same Cloud Run Jobs API pattern that BACKEND-API uses in `trigger_experiment_runner()` in `03-BACKEND-API/app/queries/experiments.py`. Copy and adapt that function — the API call is identical, just called from a standalone script instead of a FastAPI endpoint.

### Full implementation

```python
"""
Production refresh wrapper for Cloud Run Job.

Queries for all gate-passed experiments and fires one Cloud Run Job execution
per experiment to generate current-week predictions.

Cloud Scheduler fires this every Tuesday at 9am ET (14:00 UTC).
"""
import json
import logging
import os
import sys
from pathlib import Path

import google.auth
import google.auth.transport.requests
import requests as http_requests
from google.cloud import bigquery

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT        = os.environ.get("BIGQUERY_PROJECT", "nfl-model-471509")
REGION         = os.environ.get("CLOUD_RUN_REGION", "us-central1")
JOB_NAME       = os.environ.get("EXPERIMENT_JOB_NAME", "nfl-experiment-runner")
CONFIGS_TABLE  = f"{PROJECT}.platform.experiment_configs"


def get_gate_passed_experiments(client: bigquery.Client) -> list[dict]:
    """Return all experiments where gate_passed=true and not currently running."""
    query = f"""
        SELECT experiment_id, name, status
        FROM `{CONFIGS_TABLE}`
        WHERE gate_passed = true
          AND status != 'running'
        ORDER BY created_at DESC
    """
    rows = list(client.query(query).result())
    return [dict(r) for r in rows]


def trigger_experiment_job(
    credentials,
    experiment_id: str,
    run_id_hint: str,
) -> str:
    """
    Create a Cloud Run Job execution for the experiment runner.
    Returns the execution name on success.
    Raises on failure.
    """
    url = (
        f"https://{REGION}-run.googleapis.com/apis/run.googleapis.com/v1/"
        f"namespaces/{PROJECT}/jobs/{JOB_NAME}:run"
    )
    payload = {
        "overrides": {
            "containerOverrides": [{
                "env": [
                    {"name": "EXPERIMENT_CONFIG_ID", "value": experiment_id},
                    {"name": "NFL_RUN_ID", "value": run_id_hint},
                ]
            }]
        }
    }
    resp = http_requests.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {credentials.token}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("metadata", {}).get("name", "unknown")


def main() -> int:
    logger.info("Production refresh starting — project=%s", PROJECT)

    # BQ client
    client = bigquery.Client(project=PROJECT)

    # GCP credentials for Cloud Run Jobs API
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    credentials.refresh(google.auth.transport.requests.Request())

    experiments = get_gate_passed_experiments(client)
    if not experiments:
        logger.info("No gate-passed experiments found — nothing to refresh")
        return 0

    logger.info(
        "Found %d gate-passed experiment(s): %s",
        len(experiments),
        [e["experiment_id"] for e in experiments],
    )

    import uuid
    failed: list[str] = []

    for exp in experiments:
        eid  = exp["experiment_id"]
        name = exp["name"]
        run_hint = str(uuid.uuid4())
        try:
            exec_name = trigger_experiment_job(credentials, eid, run_hint)
            logger.info("Triggered experiment '%s' (%s) → execution %s", name, eid, exec_name)
        except Exception as exc:
            logger.error("Failed to trigger '%s' (%s): %s", name, eid, exc, exc_info=True)
            failed.append(eid)

    if failed:
        logger.error(
            "Production refresh completed with %d failure(s): %s",
            len(failed), failed,
        )
        return 1

    logger.info("Production refresh complete — %d experiment(s) triggered", len(experiments))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### Test locally

```bash
cd 02-MODELING
# With no gate-passed experiments in BQ, should log "nothing to refresh" and exit 0
BIGQUERY_PROJECT=nfl-model-471509 python backtests/run_production_refresh.py
```

---

## Deliverable Summary

| # | File | Change |
|---|------|--------|
| 1 | `02-MODELING/backtests/run_experiment.py` | Replace `_resolve_join_key_type()` with `_resolve_dataset_join_info()`, update `_join_user_dataset()` to use actual column names from `join_key_columns` |
| 2 | `02-MODELING/backtests/bq_writer.py` | Add `feature_importances JSON NULLABLE` to `RUNS_SCHEMA`, add `_alter_runs_table_phase3()`, update `write_backtest_run()` |
| 2 | `02-MODELING/backtests/walk_forward.py` | Capture per-fold feature importances, return mean dict from `run_walk_forward()` |
| 3 | `02-MODELING/backtests/run_production_refresh.py` | Implement (replace the stub) |

---

## Handoff Signals

When each deliverable is complete:

1. **Join-key fix** — update `00-PROJECT-LEAD/PHASE3_STATUS.md`. This unblocks any experiment using a real user-uploaded dataset.
2. **Feature importances** — flag to PROJECT-LEAD that `feature_importances JSON` is now on `backtest_runs`. BACKEND-API will add the serving endpoint.
3. **run_production_refresh.py** — update `00-PROJECT-LEAD/PHASE3_STATUS.md`. DEVOPS Step 5 becomes fully operational.
