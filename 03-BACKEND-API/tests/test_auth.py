"""
Tests for X-API-Key authentication on write endpoints.

Phase 3 deliverable: Enforce X-API-Key on POST/PUT/DELETE endpoints.

Covers:
  - API key missing → 401 (when configured)
  - API key invalid → 401 (when configured)
  - API key valid → passes through to handler
  - API key not configured (dev mode) → open/no-op
"""
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.bigquery_client import get_client
from app.config import settings
from app.main import app


@pytest.fixture
def mock_bq_for_auth():
    """A MagicMock that stands in for bigquery.Client for auth tests."""
    mock = MagicMock()
    # Mock the list_experiments query to succeed
    mock.query.return_value.result.return_value = []
    return mock


@pytest.fixture
def client_with_auth(mock_bq_for_auth):
    """TestClient with BQ mock override."""
    app.dependency_overrides[get_client] = lambda: mock_bq_for_auth
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


# ── Write endpoint tests with auth enabled ───────────────────────────────────


class TestAuthEnabled:
    """Tests with OWNER_API_KEY configured (production mode)."""

    @patch.dict(os.environ, {"OWNER_API_KEY": "test-secret-key"})
    def test_api_key_missing_returns_401(self, client_with_auth):
        """POST without X-API-Key header → 401."""
        # Reload settings to pick up the new env var
        from importlib import reload
        import app.config
        reload(app.config)

        # Try to POST an experiment (requires auth) without the key
        resp = client_with_auth.post(
            "/api/v1/experiments",
            json={
                "name": "Test",
                "target": "ats_cover",
                "features": [],
                "evaluation": {"metric": "ats_hit_rate", "success_threshold": 0.54, "min_sample": 250},
                "methodology": {"type": "walk_forward", "train_seasons": 4, "test_seasons": 1,
                               "start_season": 2015, "end_season": 2024},
                "model": {"type": "xgboost", "hyperparams": {}},
            },
        )
        assert resp.status_code == 401
        data = resp.json()
        assert data["code"] == "unauthorized"
        assert "Missing or invalid API key" in data["error"]

    @patch.dict(os.environ, {"OWNER_API_KEY": "test-secret-key"})
    def test_api_key_invalid_returns_401(self, client_with_auth):
        """POST with wrong X-API-Key → 401."""
        from importlib import reload
        import app.config
        reload(app.config)

        resp = client_with_auth.post(
            "/api/v1/experiments",
            headers={"X-API-Key": "wrong-key"},
            json={
                "name": "Test",
                "target": "ats_cover",
                "features": [],
                "evaluation": {"metric": "ats_hit_rate", "success_threshold": 0.54, "min_sample": 250},
                "methodology": {"type": "walk_forward", "train_seasons": 4, "test_seasons": 1,
                               "start_season": 2015, "end_season": 2024},
                "model": {"type": "xgboost", "hyperparams": {}},
            },
        )
        assert resp.status_code == 401
        data = resp.json()
        assert data["code"] == "unauthorized"

    @patch.dict(os.environ, {"OWNER_API_KEY": "test-secret-key"})
    def test_api_key_valid_allows_request(self, client_with_auth, mock_bq_for_auth):
        """POST with correct X-API-Key → request proceeds (validation/BQ errors may still occur)."""
        from importlib import reload
        import app.config
        reload(app.config)

        # Mock the feature validation and insert to succeed
        with patch("app.routers.experiments.eq.validate_experiment_features", return_value=[]), \
             patch("app.routers.experiments.eq.insert_experiment_config", return_value=None):
            resp = client_with_auth.post(
                "/api/v1/experiments",
                headers={"X-API-Key": "test-secret-key"},
                json={
                    "name": "Test",
                    "target": "ats_cover",
                    "features": [],
                    "evaluation": {"metric": "ats_hit_rate", "success_threshold": 0.54, "min_sample": 250},
                    "methodology": {"type": "walk_forward", "train_seasons": 4, "test_seasons": 1,
                                   "start_season": 2015, "end_season": 2024},
                    "model": {"type": "xgboost", "hyperparams": {}},
                },
            )

        # Should not be 401; will be 201 if successful or 400/502 on validation/BQ errors
        assert resp.status_code != 401
        assert resp.status_code in (201, 400, 502)


# ── Dev mode (no API key configured) ─────────────────────────────────────────


class TestAuthDisabled:
    """Tests with OWNER_API_KEY not configured (dev mode)."""

    @patch.dict(os.environ, {}, clear=True)
    def test_no_api_key_configured_allows_all(self, client_with_auth):
        """POST without key when OWNER_API_KEY is not set → allowed (dev mode)."""
        from importlib import reload
        import app.config
        reload(app.config)

        # Even without the key, request should be allowed to proceed in dev mode
        with patch("app.routers.experiments.eq.validate_experiment_features", return_value=[]), \
             patch("app.routers.experiments.eq.insert_experiment_config", return_value=None):
            resp = client_with_auth.post(
                "/api/v1/experiments",
                json={
                    "name": "Test",
                    "target": "ats_cover",
                    "features": [],
                    "evaluation": {"metric": "ats_hit_rate", "success_threshold": 0.54, "min_sample": 250},
                    "methodology": {"type": "walk_forward", "train_seasons": 4, "test_seasons": 1,
                                   "start_season": 2015, "end_season": 2024},
                    "model": {"type": "xgboost", "hyperparams": {}},
                },
            )

        # Should not be 401 in dev mode
        assert resp.status_code != 401
        assert resp.status_code in (201, 400, 502)


# ── Read endpoints (no auth required) ─────────────────────────────────────────


class TestReadEndpoints:
    """Read endpoints should work without auth regardless of configuration."""

    @patch.dict(os.environ, {"OWNER_API_KEY": "test-secret-key"})
    def test_read_endpoint_no_auth_required(self, client_with_auth, mock_bq_for_auth):
        """GET endpoints should work without X-API-Key header."""
        from importlib import reload
        import app.config
        reload(app.config)

        with patch("app.routers.experiments.eq.list_experiments", return_value=([], False)):
            resp = client_with_auth.get("/api/v1/experiments")

        # Should succeed without auth
        assert resp.status_code == 200
