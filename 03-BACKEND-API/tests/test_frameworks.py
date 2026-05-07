"""
Tests for Step 4 framework CRUD endpoints:
  POST   /api/v1/frameworks
  GET    /api/v1/frameworks
  GET    /api/v1/frameworks/{id}
  PUT    /api/v1/frameworks/{id}
  DELETE /api/v1/frameworks/{id}
"""
import json
from unittest.mock import patch

import pytest

from tests.conftest import make_experiment_row


# ── Shared helpers ────────────────────────────────────────────────────────────


VALID_CONFIG = {
    "target": "ats_cover",
    "features": [
        {"dataset": "curated", "column": "home_ol_pass_epa_per_att"}
    ],
    "evaluation": {
        "metric": "ats_hit_rate",
        "success_threshold": 0.54,
        "min_sample": 250,
    },
    "methodology": {
        "type": "walk_forward",
        "train_seasons": 4,
        "test_seasons": 1,
        "start_season": 2015,
        "end_season": 2024,
    },
    "model": {
        "type": "xgboost",
        "hyperparams": {},
    },
}

BASE_CREATE_BODY = {
    "name": "OL mismatch baseline",
    "description": "Starting point for OL-focused ATS experiments",
}


def make_framework_row(**kwargs):
    """Return a dict matching the Framework schema with sensible defaults."""
    defaults = {
        "framework_id": "fw-001",
        "name": "OL mismatch baseline",
        "description": "Starting point for OL-focused ATS experiments",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
        "base_experiment_id": None,
        "config": {
            "experiment_id": "fw-001",
            "name": "Framework config fw-001",
            "created_at": "2024-01-01T00:00:00Z",
            "target": "ats_cover",
            "features": [{"dataset": "curated", "column": "home_ol_pass_epa_per_att", "semantic_name": None}],
            "evaluation": {"metric": "ats_hit_rate", "success_threshold": 0.54, "min_sample": 250},
            "methodology": {
                "type": "walk_forward", "train_seasons": 4, "test_seasons": 1,
                "start_season": 2015, "end_season": 2024,
            },
            "model": {"type": "xgboost", "hyperparams": {}},
            "status": "draft",
            "gate_passed": None,
        },
    }
    defaults.update(kwargs)
    return defaults


# ── POST /api/v1/frameworks ───────────────────────────────────────────────────


class TestCreateFramework:
    def test_from_base_experiment_id_returns_201(self, client, mock_bq):
        exp_row = make_experiment_row(experiment_id="exp-001", status="complete")
        body = {**BASE_CREATE_BODY, "base_experiment_id": "exp-001"}

        with patch("app.queries.experiments.get_experiment_by_id", return_value=exp_row), \
             patch("app.queries.frameworks.insert_framework") as mock_ins:
            resp = client.post("/api/v1/frameworks", json=body)

        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "OL mismatch baseline"
        assert data["base_experiment_id"] == "exp-001"
        assert "framework_id" in data
        assert len(data["framework_id"].split("-")) == 5   # UUID v4
        assert "config" in data
        assert data["config"]["experiment_id"] == "exp-001"

        mock_ins.assert_called_once()
        call_kwargs = mock_ins.call_args.kwargs
        assert call_kwargs["base_experiment_id"] == "exp-001"
        assert call_kwargs["name"] == "OL mismatch baseline"

    def test_from_direct_config_returns_201(self, client, mock_bq):
        body = {**BASE_CREATE_BODY, "config": VALID_CONFIG}

        with patch("app.queries.frameworks.insert_framework") as mock_ins:
            resp = client.post("/api/v1/frameworks", json=body)

        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "OL mismatch baseline"
        assert data["base_experiment_id"] is None
        assert data["config"]["target"] == "ats_cover"
        assert data["config"]["status"] == "draft"
        # Synthetic experiment_id should equal the generated framework_id
        assert data["config"]["experiment_id"] == data["framework_id"]

        mock_ins.assert_called_once()
        call_kwargs = mock_ins.call_args.kwargs
        assert call_kwargs["base_experiment_id"] is None

    def test_neither_source_returns_422(self, client, mock_bq):
        """Missing both base_experiment_id and config → Pydantic validation error."""
        resp = client.post("/api/v1/frameworks", json=BASE_CREATE_BODY)
        assert resp.status_code == 422

    def test_both_sources_returns_422(self, client, mock_bq):
        """Providing both base_experiment_id and config → Pydantic validation error."""
        body = {**BASE_CREATE_BODY, "base_experiment_id": "exp-001", "config": VALID_CONFIG}
        resp = client.post("/api/v1/frameworks", json=body)
        assert resp.status_code == 422

    def test_base_experiment_not_found_returns_404(self, client, mock_bq):
        body = {**BASE_CREATE_BODY, "base_experiment_id": "nonexistent"}

        with patch("app.queries.experiments.get_experiment_by_id", return_value=None):
            resp = client.post("/api/v1/frameworks", json=body)

        assert resp.status_code == 404
        body_out = resp.json()
        assert body_out["code"] == "not_found"
        assert "request_id" in body_out

    def test_bq_fetch_experiment_error_returns_502(self, client, mock_bq):
        body = {**BASE_CREATE_BODY, "base_experiment_id": "exp-001"}

        with patch(
            "app.queries.experiments.get_experiment_by_id",
            side_effect=Exception("BQ down"),
        ):
            resp = client.post("/api/v1/frameworks", json=body)

        assert resp.status_code == 502
        assert resp.json()["code"] == "upstream_error"

    def test_bq_insert_error_returns_502(self, client, mock_bq):
        body = {**BASE_CREATE_BODY, "config": VALID_CONFIG}

        with patch(
            "app.queries.frameworks.insert_framework",
            side_effect=Exception("streaming insert failed"),
        ):
            resp = client.post("/api/v1/frameworks", json=body)

        assert resp.status_code == 502
        assert resp.json()["code"] == "upstream_error"

    def test_missing_name_returns_422(self, client, mock_bq):
        body = {"description": "desc", "config": VALID_CONFIG}
        resp = client.post("/api/v1/frameworks", json=body)
        assert resp.status_code == 422


# ── GET /api/v1/frameworks ────────────────────────────────────────────────────


class TestListFrameworks:
    def test_happy_path_returns_200(self, client, mock_bq):
        rows = [make_framework_row(framework_id=f"fw-00{i}") for i in range(3)]

        with patch("app.queries.frameworks.list_frameworks", return_value=(rows, False)):
            resp = client.get("/api/v1/frameworks")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) == 3
        assert data["pagination"]["has_more"] is False
        assert data["pagination"]["next_cursor"] is None

    def test_pagination_cursor(self, client, mock_bq):
        rows = [make_framework_row()]

        with patch("app.queries.frameworks.list_frameworks", return_value=(rows, True)) as mock_list:
            resp = client.get("/api/v1/frameworks?limit=1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["pagination"]["has_more"] is True
        assert data["pagination"]["next_cursor"] is not None

    def test_bq_error_returns_502(self, client, mock_bq):
        with patch(
            "app.queries.frameworks.list_frameworks",
            side_effect=Exception("BQ down"),
        ):
            resp = client.get("/api/v1/frameworks")

        assert resp.status_code == 502
        assert resp.json()["code"] == "upstream_error"


# ── GET /api/v1/frameworks/{id} ───────────────────────────────────────────────


class TestGetFramework:
    def test_happy_path_returns_200(self, client, mock_bq):
        row = make_framework_row()

        with patch("app.queries.frameworks.get_framework_by_id", return_value=row):
            resp = client.get("/api/v1/frameworks/fw-001")

        assert resp.status_code == 200
        data = resp.json()
        assert data["framework_id"] == "fw-001"
        assert data["name"] == "OL mismatch baseline"
        assert "config" in data
        assert data["config"]["target"] == "ats_cover"

    def test_not_found_returns_404(self, client, mock_bq):
        with patch("app.queries.frameworks.get_framework_by_id", return_value=None):
            resp = client.get("/api/v1/frameworks/nonexistent")

        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == "not_found"
        assert "request_id" in body

    def test_bq_error_returns_502(self, client, mock_bq):
        with patch(
            "app.queries.frameworks.get_framework_by_id",
            side_effect=Exception("BQ down"),
        ):
            resp = client.get("/api/v1/frameworks/fw-001")

        assert resp.status_code == 502
        assert resp.json()["code"] == "upstream_error"


# ── PUT /api/v1/frameworks/{id} ───────────────────────────────────────────────


class TestUpdateFramework:
    def _existing(self):
        return make_framework_row()

    def test_update_name_returns_200(self, client, mock_bq):
        updated = make_framework_row(name="New name")

        with patch("app.queries.frameworks.get_framework_by_id", side_effect=[self._existing(), updated]), \
             patch("app.queries.frameworks.update_framework") as mock_upd:
            resp = client.put("/api/v1/frameworks/fw-001", json={"name": "New name"})

        assert resp.status_code == 200
        assert resp.json()["name"] == "New name"
        mock_upd.assert_called_once()
        call_kwargs = mock_upd.call_args.kwargs
        assert call_kwargs["name"] == "New name"
        assert call_kwargs["description"] is None
        assert call_kwargs["config_snapshot"] is None

    def test_update_config_returns_200(self, client, mock_bq):
        updated_config = {**make_framework_row()["config"], "target": "outright_winner"}
        updated = make_framework_row(config={**make_framework_row()["config"], "target": "outright_winner"})
        new_config = {**VALID_CONFIG, "target": "outright_winner"}

        with patch("app.queries.frameworks.get_framework_by_id", side_effect=[self._existing(), updated]), \
             patch("app.queries.frameworks.update_framework") as mock_upd:
            resp = client.put("/api/v1/frameworks/fw-001", json={"config": new_config})

        assert resp.status_code == 200
        mock_upd.assert_called_once()
        call_kwargs = mock_upd.call_args.kwargs
        assert call_kwargs["config_snapshot"] is not None
        assert call_kwargs["config_snapshot"]["target"] == "outright_winner"

    def test_empty_body_returns_422(self, client, mock_bq):
        """Empty update body → Pydantic model_validator rejects it."""
        resp = client.put("/api/v1/frameworks/fw-001", json={})
        assert resp.status_code == 422

    def test_not_found_returns_404(self, client, mock_bq):
        with patch("app.queries.frameworks.get_framework_by_id", return_value=None):
            resp = client.put("/api/v1/frameworks/nonexistent", json={"name": "x"})

        assert resp.status_code == 404
        assert resp.json()["code"] == "not_found"

    def test_bq_fetch_error_returns_502(self, client, mock_bq):
        with patch(
            "app.queries.frameworks.get_framework_by_id",
            side_effect=Exception("BQ down"),
        ):
            resp = client.put("/api/v1/frameworks/fw-001", json={"name": "x"})

        assert resp.status_code == 502
        assert resp.json()["code"] == "upstream_error"

    def test_bq_update_error_returns_502(self, client, mock_bq):
        with patch("app.queries.frameworks.get_framework_by_id", return_value=self._existing()), \
             patch(
                 "app.queries.frameworks.update_framework",
                 side_effect=Exception("DML failed"),
             ):
            resp = client.put("/api/v1/frameworks/fw-001", json={"name": "x"})

        assert resp.status_code == 502
        assert resp.json()["code"] == "upstream_error"

    def test_refetch_fails_returns_merged_response(self, client, mock_bq):
        """
        If the re-fetch after update fails (streaming buffer not flushed),
        the router should return a synthesised response from known state
        rather than raising 500.
        """
        with patch(
            "app.queries.frameworks.get_framework_by_id",
            side_effect=[self._existing(), None],
        ), patch("app.queries.frameworks.update_framework"):
            resp = client.put("/api/v1/frameworks/fw-001", json={"name": "Updated name"})

        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated name"


# ── DELETE /api/v1/frameworks/{id} ───────────────────────────────────────────


class TestDeleteFramework:
    def test_happy_path_returns_204(self, client, mock_bq):
        with patch("app.queries.frameworks.get_framework_by_id", return_value=make_framework_row()), \
             patch("app.queries.frameworks.delete_framework") as mock_del:
            resp = client.delete("/api/v1/frameworks/fw-001")

        assert resp.status_code == 204
        assert resp.content == b""
        mock_del.assert_called_once_with(mock_bq, "fw-001")

    def test_not_found_returns_404(self, client, mock_bq):
        with patch("app.queries.frameworks.get_framework_by_id", return_value=None):
            resp = client.delete("/api/v1/frameworks/nonexistent")

        assert resp.status_code == 404
        assert resp.json()["code"] == "not_found"

    def test_bq_fetch_error_returns_502(self, client, mock_bq):
        with patch(
            "app.queries.frameworks.get_framework_by_id",
            side_effect=Exception("BQ down"),
        ):
            resp = client.delete("/api/v1/frameworks/fw-001")

        assert resp.status_code == 502
        assert resp.json()["code"] == "upstream_error"

    def test_bq_delete_error_returns_502(self, client, mock_bq):
        with patch("app.queries.frameworks.get_framework_by_id", return_value=make_framework_row()), \
             patch(
                 "app.queries.frameworks.delete_framework",
                 side_effect=Exception("DML failed"),
             ):
            resp = client.delete("/api/v1/frameworks/fw-001")

        assert resp.status_code == 502
        assert resp.json()["code"] == "upstream_error"
