"""
Tests for GET /api/v1/predictions/{game_id}/explanation.

Covers:
  - Happy path: top drivers, family matchup, full feature list, is_approximate
  - No production experiment: 404 no_production_experiment
  - No stored rows for the game: 404 not_found
  - BigQuery error resolving the experiment: 502
  - BigQuery error fetching explanation rows: 502
  - Approximate reproduction is surfaced (is_approximate / reproduction_max_diff)
"""
from unittest.mock import patch

from tests.conftest import make_explanation_row


PROD_EXP = {
    "experiment_id": "00000000-0000-4000-8000-00000000f0re",
    "run_id": "run-001",
    "completed_at": "2026-09-17T00:00:00Z",
    "experiment_name": "production-forward-v2",
    "gate_passed": False,
}


def _rows():
    return [
        make_explanation_row(feature="home_ol_sack_rate_blend", side="home",
                              family="OL pass protection", contribution_logodds=0.12,
                              pick_direction_contribution=0.12, abs_rank=1),
        make_explanation_row(feature="away_def_sack_rate_blend", side="away",
                              family="defence pass rush", contribution_logodds=0.08,
                              pick_direction_contribution=0.08, abs_rank=2),
        make_explanation_row(feature="temp", side="game", family="weather",
                              raw_value=68.0, league_pctile=None,
                              contribution_logodds=-0.01, pick_direction_contribution=-0.01,
                              abs_rank=3),
    ]


def test_happy_path_shape(client, mock_bq):
    with patch("app.routers.predictions.pq.get_production_experiment", return_value=PROD_EXP), \
         patch("app.routers.predictions.eq.get_game_explanation_rows", return_value=_rows()):
        resp = client.get("/api/v1/predictions/2026_01_SF_LA/explanation")

    assert resp.status_code == 200
    data = resp.json()
    assert data["game_id"] == "2026_01_SF_LA"
    assert data["experiment_id"] == PROD_EXP["experiment_id"]
    assert data["is_approximate"] is False
    assert data["reproduction_max_diff"] is None
    assert data["clean_forward"] is True
    assert len(data["all_features"]) == 3
    assert len(data["top_drivers"]) <= 5
    # top_drivers ordered by abs_rank
    assert [d["feature"] for d in data["top_drivers"]] == [
        "home_ol_sack_rate_blend", "away_def_sack_rate_blend", "temp",
    ]


def test_family_matchup_excludes_game_side_and_nets_home_away(client, mock_bq):
    with patch("app.routers.predictions.pq.get_production_experiment", return_value=PROD_EXP), \
         patch("app.routers.predictions.eq.get_game_explanation_rows", return_value=_rows()):
        resp = client.get("/api/v1/predictions/2026_01_SF_LA/explanation")

    matchup = {m["family"]: m for m in resp.json()["family_matchup"]}
    assert "weather" not in matchup  # side='game' feature, excluded
    assert matchup["OL pass protection"]["home_contribution"] == 0.12
    assert matchup["OL pass protection"]["away_contribution"] == 0.0
    assert matchup["OL pass protection"]["net"] == 0.12
    assert matchup["defence pass rush"]["away_contribution"] == 0.08


def test_approximate_reproduction_is_surfaced(client, mock_bq):
    rows = [make_explanation_row(is_approximate=True, reproduction_max_diff=0.0370355,
                                  clean_forward=False)]
    with patch("app.routers.predictions.pq.get_production_experiment", return_value=PROD_EXP), \
         patch("app.routers.predictions.eq.get_game_explanation_rows", return_value=rows):
        resp = client.get("/api/v1/predictions/2026_01_SF_LA/explanation")

    data = resp.json()
    assert data["is_approximate"] is True
    assert data["reproduction_max_diff"] == 0.0370355
    assert data["clean_forward"] is False


def test_no_production_experiment_returns_404(client, mock_bq):
    with patch("app.routers.predictions.pq.get_production_experiment", return_value=None):
        resp = client.get("/api/v1/predictions/2026_01_SF_LA/explanation")

    assert resp.status_code == 404
    assert resp.json()["code"] == "no_production_experiment"


def test_no_stored_rows_returns_404_not_found(client, mock_bq):
    with patch("app.routers.predictions.pq.get_production_experiment", return_value=PROD_EXP), \
         patch("app.routers.predictions.eq.get_game_explanation_rows", return_value=[]):
        resp = client.get("/api/v1/predictions/2026_99_XX_YY/explanation")

    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


def test_bigquery_error_resolving_experiment_returns_502(client, mock_bq):
    with patch("app.routers.predictions.pq.get_production_experiment", side_effect=RuntimeError("boom")):
        resp = client.get("/api/v1/predictions/2026_01_SF_LA/explanation")

    assert resp.status_code == 502
    assert resp.json()["code"] == "upstream_error"


def test_bigquery_error_fetching_rows_returns_502(client, mock_bq):
    with patch("app.routers.predictions.pq.get_production_experiment", return_value=PROD_EXP), \
         patch("app.routers.predictions.eq.get_game_explanation_rows", side_effect=RuntimeError("boom")):
        resp = client.get("/api/v1/predictions/2026_01_SF_LA/explanation")

    assert resp.status_code == 502
    assert resp.json()["code"] == "upstream_error"
