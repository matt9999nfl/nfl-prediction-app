"""
Tests for:
  GET /api/v1/experiments
  GET /api/v1/experiments/{id}
  GET /api/v1/experiments/{id}/predictions
"""
from unittest.mock import patch

from tests.conftest import make_experiment_row, make_prediction_row, make_run_row


# ── List experiments ──────────────────────────────────────────────────────────


def test_list_experiments_happy_path(client, mock_bq):
    rows = [make_experiment_row(), make_experiment_row(experiment_id="exp-002")]
    with patch("app.routers.experiments.eq.list_experiments", return_value=(rows, False)):
        resp = client.get("/api/v1/experiments")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]) == 2
    assert "pagination" in data


def test_list_experiments_shape(client, mock_bq):
    rows = [make_experiment_row()]
    with patch("app.routers.experiments.eq.list_experiments", return_value=(rows, False)):
        resp = client.get("/api/v1/experiments")
    exp = resp.json()["data"][0]
    for field in ["experiment_id", "name", "created_at", "target", "status"]:
        assert field in exp, f"Missing field: {field}"


def test_list_experiments_invalid_status(client, mock_bq):
    resp = client.get("/api/v1/experiments?status=bogus")
    assert resp.status_code == 422


def test_list_experiments_invalid_target(client, mock_bq):
    resp = client.get("/api/v1/experiments?target=made_up")
    assert resp.status_code == 422


def test_list_experiments_bq_error(client, mock_bq):
    with patch("app.routers.experiments.eq.list_experiments", side_effect=Exception("BQ fail")):
        resp = client.get("/api/v1/experiments")
    assert resp.status_code == 502
    data = resp.json()
    assert data["code"] == "upstream_error"
    assert "BQ fail" not in str(data)


# ── Single experiment ─────────────────────────────────────────────────────────


def test_get_experiment_happy_path(client, mock_bq):
    config = make_experiment_row()
    run = make_run_row()
    with patch("app.routers.experiments.eq.get_experiment_by_id", return_value=config), \
         patch("app.routers.experiments.eq.get_runs_for_experiment", return_value=[run]):
        resp = client.get("/api/v1/experiments/exp-001")
    assert resp.status_code == 200
    data = resp.json()
    assert "config" in data
    assert "latest_run" in data
    assert "run_history" in data
    assert data["config"]["experiment_id"] == "exp-001"
    assert data["latest_run"] is not None
    assert len(data["run_history"]) == 1


def test_get_experiment_no_runs(client, mock_bq):
    config = make_experiment_row()
    with patch("app.routers.experiments.eq.get_experiment_by_id", return_value=config), \
         patch("app.routers.experiments.eq.get_runs_for_experiment", return_value=[]):
        resp = client.get("/api/v1/experiments/exp-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["latest_run"] is None
    assert data["run_history"] == []


def test_get_experiment_not_found(client, mock_bq):
    with patch("app.routers.experiments.eq.get_experiment_by_id", return_value=None):
        resp = client.get("/api/v1/experiments/does-not-exist")
    assert resp.status_code == 404
    data = resp.json()
    assert data["code"] == "not_found"
    assert "request_id" in data


def test_get_experiment_bq_error(client, mock_bq):
    with patch("app.routers.experiments.eq.get_experiment_by_id", side_effect=Exception("timeout")):
        resp = client.get("/api/v1/experiments/exp-001")
    assert resp.status_code == 502
    assert resp.json()["code"] == "upstream_error"
    assert "timeout" not in str(resp.json())


def test_get_experiment_runs_failure_does_not_break_response(client, mock_bq):
    """If backtest_runs query fails, the config should still be returned."""
    config = make_experiment_row()
    with patch("app.routers.experiments.eq.get_experiment_by_id", return_value=config), \
         patch("app.routers.experiments.eq.get_runs_for_experiment", side_effect=Exception("runs table missing")):
        resp = client.get("/api/v1/experiments/exp-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["latest_run"] is None
    assert data["run_history"] == []


# ── Predictions ───────────────────────────────────────────────────────────────


def test_get_predictions_happy_path(client, mock_bq):
    rows = [make_prediction_row(), make_prediction_row(game_id="2024_02_GB_CHI", week=2)]
    with patch("app.routers.experiments.eq.list_predictions", return_value=(rows, False)):
        resp = client.get("/api/v1/experiments/exp-001/predictions?season=2024")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]) == 2
    assert "pagination" in data


def test_get_predictions_requires_season(client, mock_bq):
    """Season is required on the predictions endpoint — omitting it should 422."""
    resp = client.get("/api/v1/experiments/exp-001/predictions")
    assert resp.status_code == 422


def test_get_predictions_shape(client, mock_bq):
    rows = [make_prediction_row()]
    with patch("app.routers.experiments.eq.list_predictions", return_value=(rows, False)):
        resp = client.get("/api/v1/experiments/exp-001/predictions?season=2024")
    pred = resp.json()["data"][0]
    for field in [
        "game_id", "season", "week", "home_team", "away_team",
        "predicted_home_cover_prob", "predicted_side", "confidence_tier",
    ]:
        assert field in pred, f"Missing field: {field}"


def test_get_predictions_bq_error(client, mock_bq):
    with patch("app.routers.experiments.eq.list_predictions", side_effect=Exception("BQ error")):
        resp = client.get("/api/v1/experiments/exp-001/predictions?season=2024")
    assert resp.status_code == 502
    data = resp.json()
    assert data["code"] == "upstream_error"
    assert "BQ error" not in str(data)


def test_get_predictions_pagination(client, mock_bq):
    rows = [make_prediction_row(game_id=f"2024_0{i}_GB_CHI") for i in range(100)]
    with patch("app.routers.experiments.eq.list_predictions", return_value=(rows, True)):
        resp = client.get("/api/v1/experiments/exp-001/predictions?season=2024&limit=100")
    data = resp.json()
    assert data["pagination"]["has_more"] is True
    assert data["pagination"]["next_cursor"] is not None


def test_get_predictions_invalid_limit(client, mock_bq):
    resp = client.get("/api/v1/experiments/exp-001/predictions?season=2024&limit=9999")
    assert resp.status_code == 422
