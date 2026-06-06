"""
Tests for:
  GET /api/v1/experiments
  GET /api/v1/experiments/{id}
  GET /api/v1/experiments/{id}/predictions
  GET /api/v1/experiments/{id}/feature-importance
"""
from unittest.mock import patch

from tests.conftest import (
    make_experiment_row,
    make_feature_importance_row,
    make_fold_result_row,
    make_prediction_row,
    make_run_row,
)


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


# ── Deliverable 3.1: per_fold in experiment detail ───────────────────────────


def test_get_experiment_includes_per_fold(client, mock_bq):
    """per_fold array should be present and populated when fold data is available."""
    config = make_experiment_row()
    run = make_run_row()
    fold_rows = [
        make_fold_result_row(season=2023),
        make_fold_result_row(season=2024),
    ]
    with patch("app.routers.experiments.eq.get_experiment_by_id", return_value=config), \
         patch("app.routers.experiments.eq.get_runs_for_experiment", return_value=[run]), \
         patch("app.routers.experiments.eq.get_latest_run_id", return_value="run-001"), \
         patch("app.routers.experiments.eq.get_per_fold_results", return_value=fold_rows):
        resp = client.get("/api/v1/experiments/exp-001")
    assert resp.status_code == 200
    data = resp.json()
    assert "per_fold" in data
    assert len(data["per_fold"]) == 2
    fold = data["per_fold"][0]
    for field in ["season", "wins", "losses", "pushes", "hit_rate", "n_games"]:
        assert field in fold, f"Missing field: {field}"


def test_get_experiment_per_fold_empty_when_no_run_id(client, mock_bq):
    """per_fold should be [] when latest_run_id is None (no completed run yet)."""
    config = make_experiment_row()
    with patch("app.routers.experiments.eq.get_experiment_by_id", return_value=config), \
         patch("app.routers.experiments.eq.get_runs_for_experiment", return_value=[]), \
         patch("app.routers.experiments.eq.get_latest_run_id", return_value=None):
        resp = client.get("/api/v1/experiments/exp-001")
    assert resp.status_code == 200
    assert resp.json()["per_fold"] == []


def test_get_experiment_per_fold_empty_when_no_predictions(client, mock_bq):
    """per_fold should be [] when the run exists but backtest_predictions has no rows."""
    config = make_experiment_row()
    with patch("app.routers.experiments.eq.get_experiment_by_id", return_value=config), \
         patch("app.routers.experiments.eq.get_runs_for_experiment", return_value=[]), \
         patch("app.routers.experiments.eq.get_latest_run_id", return_value="run-001"), \
         patch("app.routers.experiments.eq.get_per_fold_results", return_value=[]):
        resp = client.get("/api/v1/experiments/exp-001")
    assert resp.status_code == 200
    assert resp.json()["per_fold"] == []


def test_get_experiment_per_fold_failure_does_not_break_response(client, mock_bq):
    """If per-fold query fails, the config should still be returned with per_fold=[]."""
    config = make_experiment_row()
    run = make_run_row()
    with patch("app.routers.experiments.eq.get_experiment_by_id", return_value=config), \
         patch("app.routers.experiments.eq.get_runs_for_experiment", return_value=[run]), \
         patch("app.routers.experiments.eq.get_latest_run_id", side_effect=Exception("BQ error")):
        resp = client.get("/api/v1/experiments/exp-001")
    assert resp.status_code == 200
    assert resp.json()["per_fold"] == []


# ── Deliverable 3.2: feature-importance endpoint ─────────────────────────────


def test_feature_importance_happy_path(client, mock_bq):
    config = make_experiment_row()
    items = [
        make_feature_importance_row(feature="home_ol_rush_epa_per_att", importance=0.0842),
        make_feature_importance_row(feature="away_ol_pass_epa_per_att", importance=0.0601),
    ]
    with patch("app.routers.experiments.eq.get_experiment_by_id", return_value=config), \
         patch("app.routers.experiments.eq.get_latest_run_id", return_value="run-001"), \
         patch("app.routers.experiments.eq.get_feature_importances", return_value=items):
        resp = client.get("/api/v1/experiments/exp-001/feature-importance")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == "run-001"
    assert len(data["features"]) == 2
    feat = data["features"][0]
    assert "feature" in feat
    assert "importance" in feat


def test_feature_importance_shape(client, mock_bq):
    config = make_experiment_row()
    items = [make_feature_importance_row()]
    with patch("app.routers.experiments.eq.get_experiment_by_id", return_value=config), \
         patch("app.routers.experiments.eq.get_latest_run_id", return_value="run-001"), \
         patch("app.routers.experiments.eq.get_feature_importances", return_value=items):
        resp = client.get("/api/v1/experiments/exp-001/feature-importance")
    assert resp.status_code == 200
    data = resp.json()
    assert "run_id" in data
    assert "features" in data


def test_feature_importance_no_run(client, mock_bq):
    """Returns {run_id: null, features: []} when no run exists."""
    config = make_experiment_row()
    with patch("app.routers.experiments.eq.get_experiment_by_id", return_value=config), \
         patch("app.routers.experiments.eq.get_latest_run_id", return_value=None):
        resp = client.get("/api/v1/experiments/exp-001/feature-importance")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] is None
    assert data["features"] == []


def test_feature_importance_not_found(client, mock_bq):
    with patch("app.routers.experiments.eq.get_experiment_by_id", return_value=None):
        resp = client.get("/api/v1/experiments/does-not-exist/feature-importance")
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


def test_feature_importance_bq_error_on_config(client, mock_bq):
    with patch("app.routers.experiments.eq.get_experiment_by_id", side_effect=Exception("timeout")):
        resp = client.get("/api/v1/experiments/exp-001/feature-importance")
    assert resp.status_code == 502
    assert resp.json()["code"] == "upstream_error"
    assert "timeout" not in str(resp.json())


def test_feature_importance_bq_error_on_importances(client, mock_bq):
    config = make_experiment_row()
    with patch("app.routers.experiments.eq.get_experiment_by_id", return_value=config), \
         patch("app.routers.experiments.eq.get_latest_run_id", return_value="run-001"), \
         patch("app.routers.experiments.eq.get_feature_importances", side_effect=Exception("BQ fail")):
        resp = client.get("/api/v1/experiments/exp-001/feature-importance")
    assert resp.status_code == 502
    assert resp.json()["code"] == "upstream_error"


# ── GameUniverseFilter schema validation ──────────────────────────────────────


from app.schemas.experiments import GameUniverseFilter, MethodologyConfig


def test_game_universe_filter_div_game_valid():
    """A boolean value for div_game is accepted."""
    f = GameUniverseFilter(field="div_game", operator="eq", value=True)
    assert f.field == "div_game"
    assert f.value is True


def test_game_universe_filter_week_valid():
    """An integer value for week is accepted."""
    f = GameUniverseFilter(field="week", operator="gte", value=10)
    assert f.field == "week"
    assert f.value == 10


def test_game_universe_null_accepted_in_methodology():
    """game_universe=None is valid (means all games)."""
    m = MethodologyConfig(
        type="walk_forward",
        train_seasons=3,
        test_seasons=1,
        start_season=2018,
        end_season=2023,
        game_universe=None,
    )
    assert m.game_universe is None


def test_game_universe_omitted_defaults_to_none():
    """game_universe defaults to None when not provided."""
    m = MethodologyConfig(
        type="walk_forward",
        train_seasons=3,
        test_seasons=1,
        start_season=2018,
        end_season=2023,
    )
    assert m.game_universe is None


def test_game_universe_filter_invalid_field():
    """An unrecognized field name is rejected with a validation error."""
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        GameUniverseFilter(field="stadium_type", operator="eq", value=True)


def test_game_universe_filter_div_game_wrong_value_type():
    """A non-boolean value for div_game is rejected."""
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="div_game filter value must be a boolean"):
        GameUniverseFilter(field="div_game", operator="eq", value=1)


def test_game_universe_filter_week_string_value_rejected():
    """A string value for week is rejected."""
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        GameUniverseFilter(field="week", operator="gte", value="early")
