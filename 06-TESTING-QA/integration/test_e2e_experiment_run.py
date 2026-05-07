"""
Seam 6: End-to-end experiment creation, run trigger, and result verification.
Requires DEVOPS Step 3b (real Cloud Run Job trigger) to be deployed.

TIER 3 (nightly, live): slow (~5–10 minutes) — only runs on schedule.
"""
import time
import uuid
import pytest
import requests
from google.cloud import bigquery

API_BASE_URL = __import__("os").getenv("API_BASE_URL", "http://localhost:8080")
TIMEOUT_SECONDS = 600
PROJECT = "nfl-model-471509"


@pytest.mark.live
@pytest.mark.nightly
def test_full_experiment_lifecycle():
    """
    1. Create a minimal experiment config via POST /api/v1/experiments
    2. Trigger it via POST /api/v1/experiments/{id}/run
    3. Poll /status until complete or timeout
    4. Verify predictions were written via GET /api/v1/experiments/{id}/predictions
    5. Verify backtest run has metrics
    """
    eid = None
    try:
        # 1. Create config
        config = {
            "name": f"e2e_test_{uuid.uuid4().hex[:8]}",
            "target": "ats_cover",
            "features": [
                {"dataset": "curated", "column": "ol_pass_epa_per_att",
                 "semantic_name": "ol_pass_epa_per_att"}
            ],
            "evaluation": {"metric": "ats_hit_rate", "success_threshold": 0.40, "min_sample": 10},
            "methodology": {
                "type": "walk_forward",
                "train_seasons": 2,
                "test_seasons": 1,
                "start_season": 2020,
                "end_season": 2022,
            },
            "model": {"type": "xgboost", "hyperparams": {}},
        }
        r = requests.post(f"{API_BASE_URL}/api/v1/experiments", json=config)
        assert r.status_code == 201, f"Create failed: {r.text}"
        eid = r.json()["experiment_id"]

        # 2. Trigger
        r = requests.post(f"{API_BASE_URL}/api/v1/experiments/{eid}/run")
        assert r.status_code == 202, f"Trigger failed: {r.text}"

        # 3. Poll until complete
        deadline = time.time() + TIMEOUT_SECONDS
        while time.time() < deadline:
            r = requests.get(f"{API_BASE_URL}/api/v1/experiments/{eid}/status")
            assert r.status_code == 200
            status = r.json()["status"]
            if status == "complete":
                break
            if status == "failed":
                pytest.fail(f"Experiment failed: {r.json().get('error')}")
            time.sleep(15)
        else:
            pytest.fail(f"Experiment did not complete within {TIMEOUT_SECONDS}s")

        # 4. Verify predictions exist
        r = requests.get(
            f"{API_BASE_URL}/api/v1/experiments/{eid}/predictions",
            params={"season": 2022}
        )
        assert r.status_code == 200
        assert len(r.json()["data"]) > 0, "No predictions written for season 2022"

        # 5. Verify backtest run has metrics
        r = requests.get(f"{API_BASE_URL}/api/v1/experiments/{eid}")
        assert r.status_code == 200
        exp = r.json()
        assert exp is not None, "Experiment not found"
        if "latest_run" in exp and exp["latest_run"] is not None:
            latest = exp["latest_run"]
            assert latest["ats_hit_rate"] is not None
            assert latest["n_games_evaluated"] > 0

    finally:
        # Best-effort cleanup
        if eid:
            bq = bigquery.Client(project=PROJECT)
            for tbl in [
                "nfl-model-471509.platform.experiment_configs",
                "nfl-model-471509.experiments.backtest_runs",
                "nfl-model-471509.experiments.backtest_predictions",
            ]:
                try:
                    bq.query(
                        f"DELETE FROM `{tbl}` WHERE experiment_id = @eid",
                        job_config=bigquery.QueryJobConfig(
                            query_parameters=[bigquery.ScalarQueryParameter("eid", "STRING", eid)]
                        )
                    ).result()
                except Exception:
                    pass
