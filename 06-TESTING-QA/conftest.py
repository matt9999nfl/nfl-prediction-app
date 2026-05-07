"""
Shared pytest fixtures for integration tests.

Provides:
  - bq_client: BigQuery client authenticated with ADC
  - test_run_id: unique ID for test scoping
  - cleanup_test_rows: autouse fixture that deletes test data after each test
  - api: HTTP session for API tests
"""
import os
import uuid
import pytest
import requests
from google.cloud import bigquery

PROJECT = "nfl-model-471509"
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8080")


@pytest.fixture(scope="session")
def bq_client():
    """Create and return a BigQuery client authenticated via ADC."""
    return bigquery.Client(project=PROJECT)


@pytest.fixture
def test_run_id():
    """Generate a unique test ID for scoping test data writes."""
    return f"test_{uuid.uuid4().hex[:12]}"


@pytest.fixture(autouse=True)
def cleanup_test_rows(bq_client, test_run_id):
    """
    Auto-cleanup fixture: delete any rows written during a test.
    Runs as teardown after each test (yield).
    """
    yield
    # Teardown: delete test rows from experiments tables
    for table in [
        f"{PROJECT}.platform.experiment_configs",
        f"{PROJECT}.experiments.backtest_runs",
        f"{PROJECT}.experiments.backtest_predictions",
    ]:
        try:
            bq_client.query(
                f"DELETE FROM `{table}` WHERE experiment_id LIKE 'test_%'"
            ).result()
        except Exception:
            # Ignore cleanup errors — don't fail tests because of teardown
            pass


@pytest.fixture(scope="module")
def api():
    """HTTP session for API tests pointed at API_BASE_URL."""
    s = requests.Session()
    s.headers.update({"Accept": "application/json"})
    s.base_url = API_BASE_URL
    return s
