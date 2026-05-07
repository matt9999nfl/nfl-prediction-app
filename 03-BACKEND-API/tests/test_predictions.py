"""
Tests for GET /api/v1/predictions?season=N&week=N

Covers:
  - Happy path: gate-passed run + predictions returned
  - No gate-passed experiment: 404 with no_production_experiment code
  - season omitted: 422
  - week omitted: 422
  - experiment_id override: uses specified experiment
  - experiment_id override where not gate-passed: 404
  - BigQuery error: 502
"""
from unittest.mock import patch

from tests.conftest import make_experiment_row, make_prediction_row, make_run_row


# ── Happy path: gate-passed experiment with predictions ──────────────────────


def test_get_predictions_happy_path(client, mock_bq):
    """Happy path: fetch predictions from production experiment."""
    # Mock the production experiment lookup
    prod_exp = {
        "experiment_id": "exp-001",
        "run_id": "run-001",
        "completed_at": "2024-02-01T12:00:00Z",
        "experiment_name": "OL Mismatch Baseline",
    }

    # Mock the predictions
    predictions = [
        make_prediction_row(game_id="2024_05_GB_CHI", week=5),
        make_prediction_row(game_id="2024_05_KC_LAC", week=5, predicted_side="home"),
    ]

    with patch("app.routers.predictions.pq.get_production_experiment", return_value=prod_exp), \
         patch("app.routers.predictions.pq.get_production_predictions", return_value=predictions):
        resp = client.get("/api/v1/predictions?season=2024&week=5")

    assert resp.status_code == 200
    data = resp.json()
    assert data["experiment_id"] == "exp-001"
    assert data["experiment_name"] == "OL Mismatch Baseline"
    assert data["season"] == 2024
    assert data["week"] == 5
    assert data["generated_at"] == "2024-02-01T12:00:00Z"
    assert len(data["data"]) == 2
    assert data["data"][0]["game_id"] == "2024_05_GB_CHI"


def test_get_predictions_shape(client, mock_bq):
    """Verify response shape matches schema."""
    prod_exp = {
        "experiment_id": "exp-001",
        "run_id": "run-001",
        "completed_at": "2024-02-01T12:00:00Z",
        "experiment_name": "Test",
    }

    predictions = [make_prediction_row(game_id="2024_05_GB_CHI", week=5)]

    with patch("app.routers.predictions.pq.get_production_experiment", return_value=prod_exp), \
         patch("app.routers.predictions.pq.get_production_predictions", return_value=predictions):
        resp = client.get("/api/v1/predictions?season=2024&week=5")

    data = resp.json()
    # Check top-level fields
    for field in ["experiment_id", "experiment_name", "season", "week", "generated_at", "data"]:
        assert field in data, f"Missing field: {field}"

    # Check prediction item shape
    pred = data["data"][0]
    for field in ["game_id", "week", "home_team", "away_team",
                  "predicted_home_cover_prob", "predicted_side",
                  "actual_home_covered", "correct", "confidence_tier"]:
        assert field in pred, f"Missing prediction field: {field}"


def test_get_predictions_empty_week(client, mock_bq):
    """Return empty predictions list for a week with no games."""
    prod_exp = {
        "experiment_id": "exp-001",
        "run_id": "run-001",
        "completed_at": "2024-02-01T12:00:00Z",
        "experiment_name": "Test",
    }

    predictions = []

    with patch("app.routers.predictions.pq.get_production_experiment", return_value=prod_exp), \
         patch("app.routers.predictions.pq.get_production_predictions", return_value=predictions):
        resp = client.get("/api/v1/predictions?season=2024&week=1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["data"] == []


# ── No gate-passed experiment ─────────────────────────────────────────────────


def test_get_predictions_no_gate_passed(client, mock_bq):
    """Return 404 if no gate-passed experiment exists."""
    with patch("app.routers.predictions.pq.get_production_experiment", return_value=None):
        resp = client.get("/api/v1/predictions?season=2024&week=5")

    assert resp.status_code == 404
    data = resp.json()
    assert data["code"] == "no_production_experiment"
    assert "No gate-passed experiment" in data["error"]


# ── Missing required parameters ──────────────────────────────────────────────


def test_get_predictions_missing_season(client, mock_bq):
    """422 if season is omitted."""
    resp = client.get("/api/v1/predictions?week=5")
    assert resp.status_code == 422
    data = resp.json()
    assert data["code"] == "invalid_params"


def test_get_predictions_missing_week(client, mock_bq):
    """422 if week is omitted."""
    resp = client.get("/api/v1/predictions?season=2024")
    assert resp.status_code == 422
    data = resp.json()
    assert data["code"] == "invalid_params"


def test_get_predictions_missing_both(client, mock_bq):
    """422 if both season and week are omitted."""
    resp = client.get("/api/v1/predictions")
    assert resp.status_code == 422


# ── experiment_id override ──────────────────────────────────────────────────


def test_get_predictions_with_experiment_override(client, mock_bq):
    """Use specified experiment when experiment_id is provided."""
    prod_exp = {
        "experiment_id": "exp-override",
        "run_id": "run-002",
        "completed_at": "2024-02-05T14:00:00Z",
        "experiment_name": "Custom Experiment",
    }

    predictions = [make_prediction_row(game_id="2024_05_GB_CHI", week=5)]

    with patch("app.routers.predictions.pq.get_production_experiment", return_value=prod_exp) as mock_get, \
         patch("app.routers.predictions.pq.get_production_predictions", return_value=predictions):
        resp = client.get("/api/v1/predictions?season=2024&week=5&experiment_id=exp-override")

    assert resp.status_code == 200
    data = resp.json()
    assert data["experiment_id"] == "exp-override"

    # Verify the override was passed to the query layer
    mock_get.assert_called_once_with(mock_bq, experiment_id_override="exp-override")


def test_get_predictions_experiment_override_not_gate_passed(client, mock_bq):
    """Return 404 if override experiment is not gate-passed."""
    with patch("app.routers.predictions.pq.get_production_experiment", return_value=None):
        resp = client.get("/api/v1/predictions?season=2024&week=5&experiment_id=exp-invalid")

    assert resp.status_code == 404
    data = resp.json()
    assert data["code"] == "no_production_experiment"


# ── BigQuery errors ──────────────────────────────────────────────────────────


def test_get_predictions_bq_error_fetching_experiment(client, mock_bq):
    """502 if BQ error while fetching production experiment."""
    with patch("app.routers.predictions.pq.get_production_experiment", side_effect=Exception("BQ fail")):
        resp = client.get("/api/v1/predictions?season=2024&week=5")

    assert resp.status_code == 502
    data = resp.json()
    assert data["code"] == "upstream_error"
    assert "BQ fail" not in str(data)


def test_get_predictions_bq_error_fetching_predictions(client, mock_bq):
    """502 if BQ error while fetching predictions."""
    prod_exp = {
        "experiment_id": "exp-001",
        "run_id": "run-001",
        "completed_at": "2024-02-01T12:00:00Z",
        "experiment_name": "Test",
    }

    with patch("app.routers.predictions.pq.get_production_experiment", return_value=prod_exp), \
         patch("app.routers.predictions.pq.get_production_predictions", side_effect=Exception("BQ query failed")):
        resp = client.get("/api/v1/predictions?season=2024&week=5")

    assert resp.status_code == 502
    data = resp.json()
    assert data["code"] == "upstream_error"
    assert "BQ query failed" not in str(data)


# ── Multiple predictions per week ────────────────────────────────────────────


def test_get_predictions_multiple_games(client, mock_bq):
    """Return all predictions for a given week."""
    prod_exp = {
        "experiment_id": "exp-001",
        "run_id": "run-001",
        "completed_at": "2024-02-01T12:00:00Z",
        "experiment_name": "Test",
    }

    # Create predictions for a week with 3 games
    predictions = [
        make_prediction_row(game_id="2024_05_GB_CHI", week=5),
        make_prediction_row(game_id="2024_05_KC_LAC", week=5),
        make_prediction_row(game_id="2024_05_SF_LV", week=5),
    ]

    with patch("app.routers.predictions.pq.get_production_experiment", return_value=prod_exp), \
         patch("app.routers.predictions.pq.get_production_predictions", return_value=predictions):
        resp = client.get("/api/v1/predictions?season=2024&week=5")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]) == 3


# ── Null/completed game distinction ──────────────────────────────────────────


def test_get_predictions_with_completed_games(client, mock_bq):
    """Predictions for completed games have actual_home_covered and correct set."""
    prod_exp = {
        "experiment_id": "exp-001",
        "run_id": "run-001",
        "completed_at": "2024-02-01T12:00:00Z",
        "experiment_name": "Test",
    }

    # One scheduled game (nulls), one completed game (values set)
    predictions = [
        make_prediction_row(
            game_id="2024_05_GB_CHI",
            week=5,
            actual_home_covered=None,
            correct=None,
        ),
        make_prediction_row(
            game_id="2024_04_KC_LAC",
            week=4,
            actual_home_covered=True,
            correct=True,
        ),
    ]

    with patch("app.routers.predictions.pq.get_production_experiment", return_value=prod_exp), \
         patch("app.routers.predictions.pq.get_production_predictions", return_value=predictions):
        resp = client.get("/api/v1/predictions?season=2024&week=5")

    assert resp.status_code == 200
    data = resp.json()
    # Scheduled game
    assert data["data"][0]["actual_home_covered"] is None
    assert data["data"][0]["correct"] is None
    # Completed game
    assert data["data"][1]["actual_home_covered"] is True
    assert data["data"][1]["correct"] is True
