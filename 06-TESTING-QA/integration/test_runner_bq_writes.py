"""
Seam 3: run_experiment.py → experiments.*
Verifies that a runner invocation produces correct BQ writes.
Uses a minimal curated-only experiment config (no user datasets).

TIER 3 (nightly): this is slow (~2–10 minutes) — only run scheduled.
"""
import json
import os
import subprocess
import uuid
import pytest
from google.cloud import bigquery

PROJECT     = "nfl-model-471509"
CONFIGS_TBL = f"{PROJECT}.platform.experiment_configs"
RUNS_TBL    = f"{PROJECT}.experiments.backtest_runs"
PREDS_TBL   = f"{PROJECT}.experiments.backtest_predictions"

MINIMAL_CONFIG = {
    "name": "test_runner_seam3_minimal",
    "target": "ats_cover",
    "features": [
        {"dataset": "curated", "column": "ol_pass_epa_per_att", "semantic_name": "ol_pass_epa_per_att"},
    ],
    "evaluation": {"metric": "ats_hit_rate", "success_threshold": 0.54, "min_sample": 50},
    "methodology": {
        "type": "walk_forward",
        "train_seasons": 2,
        "test_seasons": 1,
        "start_season": 2020,
        "end_season": 2022,
    },
    "model": {"type": "xgboost", "hyperparams": {}},
    "status": "draft",
    "gate_passed": None,
}


@pytest.fixture
def test_experiment_id(bq_client):
    """Insert a minimal experiment config and return its ID. Clean up after."""
    eid = f"test_{uuid.uuid4().hex[:12]}"
    row = {"experiment_id": eid, **MINIMAL_CONFIG,
           "features": json.dumps(MINIMAL_CONFIG["features"]),
           "evaluation": json.dumps(MINIMAL_CONFIG["evaluation"]),
           "methodology": json.dumps(MINIMAL_CONFIG["methodology"]),
           "model": json.dumps(MINIMAL_CONFIG["model"]),
           "created_at": "2026-01-01T00:00:00Z"}
    errors = bq_client.insert_rows_json(CONFIGS_TBL, [row])
    assert not errors, f"Failed to insert test config: {errors}"
    yield eid
    # Teardown
    for tbl in [CONFIGS_TBL, RUNS_TBL, PREDS_TBL]:
        try:
            bq_client.query(
                f"DELETE FROM `{tbl}` WHERE experiment_id = @eid",
                job_config=bigquery.QueryJobConfig(
                    query_parameters=[bigquery.ScalarQueryParameter("eid", "STRING", eid)]
                )
            ).result()
        except Exception:
            pass


@pytest.mark.nightly
@pytest.mark.integration
def test_runner_writes_backtest_run(bq_client, test_experiment_id):
    """After the runner exits, experiments.backtest_runs has a row for this experiment."""
    env = {**os.environ, "EXPERIMENT_CONFIG_ID": test_experiment_id, "BIGQUERY_PROJECT": PROJECT}
    result = subprocess.run(
        ["python", "backtests/run_experiment.py"],
        cwd=os.path.join(os.path.dirname(__file__), "../../02-MODELING"),
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, (
        f"run_experiment.py exited {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    rows = list(bq_client.query(
        f"SELECT * FROM `{RUNS_TBL}` WHERE experiment_id = @eid",
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("eid", "STRING", test_experiment_id)]
        )
    ).result())
    assert len(rows) >= 1, "No backtest_runs row written for experiment"
    run = dict(rows[0])
    assert run["ats_hit_rate"] is not None, "ats_hit_rate not populated"
    assert run["n_games_evaluated"] is not None and run["n_games_evaluated"] > 0
    assert run["gate_passed"] is not None, "gate_passed not set"


@pytest.mark.nightly
@pytest.mark.integration
def test_runner_writes_predictions(bq_client, test_experiment_id):
    """After the runner exits, backtest_predictions has rows with correct structure."""
    # Assumes test_runner_writes_backtest_run already ran and the runner wrote preds
    rows = list(bq_client.query(f"""
        SELECT game_id, season, week, predicted_home_cover_prob
        FROM `{PREDS_TBL}`
        WHERE experiment_id = @eid AND season = 2022
        LIMIT 10
    """, job_config=bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("eid", "STRING", test_experiment_id)]
    )).result())
    assert len(rows) > 0, "No predictions written for season 2022"
    for row in rows:
        assert row["game_id"], "game_id is null"
        assert 0.0 <= row["predicted_home_cover_prob"] <= 1.0, (
            f"predicted_home_cover_prob out of range: {row['predicted_home_cover_prob']}"
        )


@pytest.mark.nightly
@pytest.mark.integration
def test_experiment_config_status_updated(bq_client, test_experiment_id):
    """After the runner exits, platform.experiment_configs.status is 'complete' or 'failed'."""
    rows = list(bq_client.query(
        f"SELECT status, gate_passed FROM `{CONFIGS_TBL}` WHERE experiment_id = @eid",
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("eid", "STRING", test_experiment_id)]
        )
    ).result())
    assert len(rows) == 1
    assert dict(rows[0])["status"] in ("complete", "failed"), (
        f"Expected status 'complete' or 'failed', got {dict(rows[0])['status']}"
    )
