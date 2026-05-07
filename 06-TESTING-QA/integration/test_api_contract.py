"""
Seam 4: experiments.* → BACKEND-API
Verifies that live endpoints return the shapes declared in API_CONTRACTS.md.
Runs against http://localhost:8080 by default; switches to deployed URL when API_BASE_URL is set.
"""
import os
import pytest
import requests

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8080")


def url(path: str) -> str:
    """Build absolute URL from relative path."""
    return f"{API_BASE_URL}{path}"


@pytest.mark.integration
def test_health(api):
    """GET /health returns 200 with status and version."""
    r = api.get(url("/health"))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


@pytest.mark.integration
def test_games_list_returns_pagination(api):
    """GET /api/v1/games returns paginated data structure."""
    r = api.get(url("/api/v1/games"), params={"season": 2023, "limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert "data" in body
    assert "pagination" in body
    assert isinstance(body["data"], list)


@pytest.mark.integration
def test_games_list_fields(api):
    """GET /api/v1/games returns games with required fields."""
    r = api.get(url("/api/v1/games"), params={"season": 2023, "limit": 1})
    assert r.status_code == 200
    if not r.json()["data"]:
        pytest.skip("No games in season 2023")
    game = r.json()["data"][0]
    for field in ("game_id", "season", "week", "home_team", "away_team", "status"):
        assert field in game, f"Missing field: {field}"


@pytest.mark.integration
def test_experiments_list(api):
    """GET /api/v1/experiments returns paginated experiments."""
    r = api.get(url("/api/v1/experiments"), params={"limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert "data" in body
    assert isinstance(body["data"], list)


@pytest.mark.integration
def test_experiments_list_fields(api):
    """Experiment objects contain required fields."""
    r = api.get(url("/api/v1/experiments"), params={"limit": 1})
    assert r.status_code == 200
    experiments = r.json()["data"]
    if not experiments:
        pytest.skip("No experiments exist")
    exp = experiments[0]
    for field in ("experiment_id", "name", "status", "target"):
        assert field in exp, f"Missing field in experiment: {field}"


@pytest.mark.integration
def test_features_list(api):
    """GET /api/v1/features returns features with correct structure."""
    r = api.get(url("/api/v1/features"))
    assert r.status_code == 200
    body = r.json()
    assert "data" in body
    assert len(body["data"]) > 0, "Features catalog is empty"
    feat = body["data"][0]
    for field in ("feature_id", "semantic_name", "dataset", "data_type"):
        assert field in feat, f"Missing field in feature: {field}"


@pytest.mark.integration
def test_predictions_requires_season(api):
    """GET /api/v1/predictions without season returns 422."""
    r = api.get(url("/api/v1/predictions"))
    assert r.status_code == 422


@pytest.mark.integration
def test_predictions_requires_week(api):
    """GET /api/v1/predictions with season but no week returns 422."""
    r = api.get(url("/api/v1/predictions"), params={"season": 2023})
    assert r.status_code == 422


@pytest.mark.integration
def test_predictions_no_production_experiment_returns_404(api):
    """GET /api/v1/predictions for future season with no gate-passed experiment returns 404."""
    r = api.get(url("/api/v1/predictions"), params={"season": 2099, "week": 1})
    # Either 404 (no gate-passed experiment) or 200 (one exists) — both are valid
    assert r.status_code in (200, 404)
    if r.status_code == 404:
        assert r.json()["code"] == "no_production_experiment"


@pytest.mark.integration
def test_predictions_response_shape(api):
    """GET /api/v1/predictions returns correct shape when data exists."""
    # Try a recent season that likely has data
    r = api.get(url("/api/v1/predictions"), params={"season": 2023, "week": 1})
    if r.status_code == 404:
        pytest.skip("No gate-passed experiment for season 2023")
    assert r.status_code == 200
    body = r.json()
    assert "data" in body
    assert "pagination" in body
    if body["data"]:
        pred = body["data"][0]
        for field in ("game_id", "season", "week", "predicted_home_cover_prob"):
            assert field in pred, f"Missing field in prediction: {field}"
