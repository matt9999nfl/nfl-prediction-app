"""
Shared pytest fixtures.

Tests run against the FastAPI app with the BigQuery client replaced by a
MagicMock.  No real GCP credentials are required.
"""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.bigquery_client import get_client
from app.main import app


@pytest.fixture
def mock_bq():
    """A MagicMock that stands in for bigquery.Client."""
    return MagicMock()


@pytest.fixture
def client(mock_bq):
    """
    A Starlette TestClient with the real BigQuery client replaced by mock_bq.
    Dependency-override is cleared after each test.
    """
    app.dependency_overrides[get_client] = lambda: mock_bq
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


# ── Row factory helpers ───────────────────────────────────────────────────────


def make_game_row(**kwargs):
    """Return a dict matching the Game schema with sensible defaults."""
    defaults = {
        "game_id": "2024_01_GB_CHI",
        "season": 2024,
        "week": 1,
        "game_date": "2024-09-08",
        "home_team": "CHI",
        "away_team": "GB",
        "home_score": 10,
        "away_score": 24,
        "status": "final",
        "home_spread_close": 3.5,
        "total_close": 42.5,
        "home_covered": False,
        "div_game": True,
        "roof": "outdoors",
        "temp": 68.0,
        "wind": 8.0,
    }
    defaults.update(kwargs)
    return defaults


def make_experiment_row(**kwargs):
    """Return a dict matching ExperimentConfig with sensible defaults."""
    import json
    defaults = {
        "experiment_id": "exp-001",
        "name": "Test experiment",
        "created_at": "2024-01-01T00:00:00Z",
        "target": "ats_cover",
        "features": json.dumps([
            {"dataset": "curated", "column": "home_ol_pass_epa_per_att", "semantic_name": "home_ol_pass_epa_per_att"}
        ]),
        "evaluation": json.dumps({
            "metric": "ats_hit_rate",
            "success_threshold": 0.54,
            "min_sample": 250,
        }),
        "methodology": json.dumps({
            "type": "walk_forward",
            "train_seasons": 4,
            "test_seasons": 1,
            "start_season": 2015,
            "end_season": 2024,
        }),
        "model": json.dumps({
            "type": "xgboost",
            "hyperparams": {},
        }),
        "status": "complete",
        "gate_passed": True,
    }
    defaults.update(kwargs)
    return defaults


def make_run_row(**kwargs):
    """Return a dict matching BacktestRun with sensible defaults."""
    import json
    defaults = {
        "run_id": "run-001",
        "experiment_id": "exp-001",
        "name": "Test run",
        "run_at": "2024-02-01T12:00:00Z",
        "model_type": "xgboost",
        "features": json.dumps(["home_ol_pass_epa_per_att", "away_ol_pass_epa_per_att"]),
        "ats_hit_rate": 0.56,
        "n_games_evaluated": 300,
        "gate_passed": True,
        "notes": None,
    }
    defaults.update(kwargs)
    return defaults


def make_prediction_row(**kwargs):
    defaults = {
        "game_id": "2024_01_GB_CHI",
        "season": 2024,
        "week": 1,
        "home_team": "CHI",
        "away_team": "GB",
        "predicted_home_cover_prob": 0.43,
        "predicted_side": "away",
        "actual_home_covered": False,
        "correct": 1,
        "confidence_tier": "high",
    }
    defaults.update(kwargs)
    return defaults
