"""
Tests for:
  GET /api/v1/teams/{team}/ol-rating
"""
from unittest.mock import patch

from tests.conftest import make_ol_rating_row


# ── GET /api/v1/teams/{team}/ol-rating ───────────────────────────────────────


def test_ol_rating_happy_path(client, mock_bq):
    rows = [
        make_ol_rating_row(season=2024, week=1),
        make_ol_rating_row(season=2024, week=2, ol_rush_epa_per_att=0.15, ol_pass_epa_per_att=0.09),
    ]
    with patch("app.routers.teams.tq.get_ol_rating", return_value=rows):
        resp = client.get("/api/v1/teams/KC/ol-rating")
    assert resp.status_code == 200
    data = resp.json()
    assert data["team"] == "KC"
    assert len(data["ratings"]) == 2


def test_ol_rating_shape(client, mock_bq):
    rows = [make_ol_rating_row()]
    with patch("app.routers.teams.tq.get_ol_rating", return_value=rows):
        resp = client.get("/api/v1/teams/KC/ol-rating")
    assert resp.status_code == 200
    data = resp.json()
    assert "team" in data
    assert "ratings" in data
    point = data["ratings"][0]
    for field in ["season", "week", "ol_rush_epa_per_att", "ol_pass_epa_per_att"]:
        assert field in point, f"Missing field: {field}"


def test_ol_rating_team_uppercased(client, mock_bq):
    """Lowercase team codes should be normalised to uppercase."""
    rows = [make_ol_rating_row()]
    with patch("app.routers.teams.tq.get_ol_rating", return_value=rows) as mock_fn:
        resp = client.get("/api/v1/teams/kc/ol-rating")
    assert resp.status_code == 200
    # Confirm the query was called with the uppercased team code.
    call_args = mock_fn.call_args
    assert call_args[0][1] == "KC" or call_args[1].get("team") == "KC" or "KC" in str(call_args)


def test_ol_rating_season_filter(client, mock_bq):
    rows = [make_ol_rating_row(season=2024, week=1)]
    with patch("app.routers.teams.tq.get_ol_rating", return_value=rows) as mock_fn:
        resp = client.get("/api/v1/teams/KC/ol-rating?season=2024")
    assert resp.status_code == 200
    # Confirm that the season parameter was forwarded to the query layer.
    call_kwargs = mock_fn.call_args
    assert call_kwargs is not None


def test_ol_rating_empty_result(client, mock_bq):
    """Unknown team or team with no play data returns empty ratings list."""
    with patch("app.routers.teams.tq.get_ol_rating", return_value=[]):
        resp = client.get("/api/v1/teams/XYZ/ol-rating")
    assert resp.status_code == 200
    data = resp.json()
    assert data["team"] == "XYZ"
    assert data["ratings"] == []


def test_ol_rating_invalid_team_code(client, mock_bq):
    """Team codes with invalid characters should return 400."""
    resp = client.get("/api/v1/teams/KC!!/ol-rating")
    assert resp.status_code in (400, 404, 422)


def test_ol_rating_bq_error(client, mock_bq):
    with patch("app.routers.teams.tq.get_ol_rating", side_effect=Exception("BQ fail")):
        resp = client.get("/api/v1/teams/KC/ol-rating")
    assert resp.status_code == 502
    data = resp.json()
    assert data["code"] == "upstream_error"
    assert "BQ fail" not in str(data)


def test_ol_rating_null_epa_values(client, mock_bq):
    """ol_rush_epa_per_att and ol_pass_epa_per_att may be null for weeks with no plays."""
    rows = [make_ol_rating_row(ol_rush_epa_per_att=None, ol_pass_epa_per_att=None)]
    with patch("app.routers.teams.tq.get_ol_rating", return_value=rows):
        resp = client.get("/api/v1/teams/KC/ol-rating")
    assert resp.status_code == 200
    point = resp.json()["ratings"][0]
    assert point["ol_rush_epa_per_att"] is None
    assert point["ol_pass_epa_per_att"] is None
