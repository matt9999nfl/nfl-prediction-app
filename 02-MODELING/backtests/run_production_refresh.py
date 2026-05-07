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
