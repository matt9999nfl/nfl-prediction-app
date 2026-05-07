"""
Tests for GET /api/v1/games and GET /api/v1/games/{game_id}.

BigQuery is mocked — tests verify HTTP contract shapes, pagination behaviour,
error handling, and that no raw BigQuery exceptions leak to clients.
"""
from unittest.mock import MagicMock, patch

from tests.conftest import make_game_row


# ── Helpers ───────────────────────────────────────────────────────────────────


def _mock_list(mock_bq, rows, has_more=False):
    """Patch queries.games.list_games to return (rows, has_more)."""
    return patch("app.routers.games.gq.list_games", return_value=(rows, has_more))


def _mock_get(mock_bq, row):
    """Patch queries.games.get_game_by_id to return row."""
    return patch("app.routers.games.gq.get_game_by_id", return_value=row)


# ── List games ────────────────────────────────────────────────────────────────


def test_list_games_happy_path(client, mock_bq):
    rows = [make_game_row(), make_game_row(game_id="2024_01_DAL_NYG")]
    with _mock_list(mock_bq, rows):
        resp = client.get("/api/v1/games?season=2024")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "pagination" in data
    assert len(data["data"]) == 2


def test_list_games_response_shape(client, mock_bq):
    rows = [make_game_row()]
    with _mock_list(mock_bq, rows):
        resp = client.get("/api/v1/games?season=2024")
    game = resp.json()["data"][0]
    required_fields = [
        "game_id", "season", "week", "game_date",
        "home_team", "away_team", "status",
    ]
    for field in required_fields:
        assert field in game, f"Missing field: {field}"


def test_list_games_empty(client, mock_bq):
    with _mock_list(mock_bq, []):
        resp = client.get("/api/v1/games?season=2024&week=99")
    assert resp.status_code == 200
    assert resp.json()["data"] == []
    assert resp.json()["pagination"]["has_more"] is False


def test_list_games_has_more_and_cursor(client, mock_bq):
    rows = [make_game_row(game_id=f"2024_01_T{i}_T{i+1}") for i in range(50)]
    with _mock_list(mock_bq, rows, has_more=True):
        resp = client.get("/api/v1/games?season=2024&limit=50")
    data = resp.json()
    assert data["pagination"]["has_more"] is True
    assert data["pagination"]["next_cursor"] is not None


def test_list_games_cursor_pagination(client, mock_bq):
    """Second page: cursor decoded correctly and passed as offset."""
    rows = [make_game_row()]
    with _mock_list(mock_bq, rows):
        # Get cursor from first page
        with _mock_list(mock_bq, [make_game_row() for _ in range(50)], has_more=True):
            resp1 = client.get("/api/v1/games?season=2024&limit=50")
        cursor = resp1.json()["pagination"]["next_cursor"]
        assert cursor is not None
        # Use cursor on second page
        resp2 = client.get(f"/api/v1/games?season=2024&limit=50&cursor={cursor}")
    assert resp2.status_code == 200


def test_list_games_invalid_limit(client, mock_bq):
    resp = client.get("/api/v1/games?limit=9999")
    assert resp.status_code == 422
    data = resp.json()
    assert "code" in data
    assert data["code"] == "invalid_params"


def test_list_games_invalid_status_filter(client, mock_bq):
    resp = client.get("/api/v1/games?status=unknown")
    assert resp.status_code == 422


def test_list_games_bq_error_returns_502(client, mock_bq):
    with patch("app.routers.games.gq.list_games", side_effect=Exception("BQ down")):
        resp = client.get("/api/v1/games?season=2024")
    assert resp.status_code == 502
    data = resp.json()
    assert data["code"] == "upstream_error"
    assert "request_id" in data
    # Raw exception message must NOT appear in response
    assert "BQ down" not in str(data)


def test_list_games_error_has_request_id(client, mock_bq):
    with patch("app.routers.games.gq.list_games", side_effect=Exception("fail")):
        resp = client.get("/api/v1/games?season=2024")
    assert "request_id" in resp.json()


# ── Single game ───────────────────────────────────────────────────────────────


def test_get_game_happy_path(client, mock_bq):
    game = make_game_row()
    with _mock_get(mock_bq, game), \
         patch("app.routers.games.gq.get_play_count", return_value=72), \
         patch("app.routers.games.gq.get_team_stats", return_value=None):
        resp = client.get("/api/v1/games/2024_01_GB_CHI")
    assert resp.status_code == 200
    data = resp.json()
    assert data["game_id"] == "2024_01_GB_CHI"
    assert data["play_count"] == 72


def test_get_game_not_found(client, mock_bq):
    with _mock_get(mock_bq, None):
        resp = client.get("/api/v1/games/9999_99_XX_YY")
    assert resp.status_code == 404
    data = resp.json()
    assert data["code"] == "not_found"
    assert "request_id" in data


def test_get_game_bq_error_returns_502(client, mock_bq):
    with patch("app.routers.games.gq.get_game_by_id", side_effect=Exception("network")):
        resp = client.get("/api/v1/games/2024_01_GB_CHI")
    assert resp.status_code == 502
    data = resp.json()
    assert data["code"] == "upstream_error"
    assert "network" not in str(data)   # raw error must not leak


def test_get_game_team_stats_failure_does_not_break_response(client, mock_bq):
    """team_stats is best-effort; a failure there should still return 200."""
    game = make_game_row()
    with _mock_get(mock_bq, game), \
         patch("app.routers.games.gq.get_play_count", return_value=0), \
         patch("app.routers.games.gq.get_team_stats", side_effect=Exception("plays missing")):
        resp = client.get("/api/v1/games/2024_01_GB_CHI")
    assert resp.status_code == 200
    assert resp.json()["team_stats"] is None


def test_get_game_x_request_id_header(client, mock_bq):
    game = make_game_row()
    with _mock_get(mock_bq, game), \
         patch("app.routers.games.gq.get_play_count", return_value=0), \
         patch("app.routers.games.gq.get_team_stats", return_value=None):
        resp = client.get("/api/v1/games/2024_01_GB_CHI")
    assert "x-request-id" in resp.headers
