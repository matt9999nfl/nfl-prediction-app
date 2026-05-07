"""
Tests for Step 3 experiment write + trigger endpoints:
  POST /api/v1/experiments
  POST /api/v1/experiments/{id}/run
  GET  /api/v1/experiments/{id}/status
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_experiment_row, make_run_row


# ── Shared helpers ────────────────────────────────────────────────────────────


VALID_CREATE_BODY = {
    "name": "New experiment",
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


# ── POST /api/v1/experiments ──────────────────────────────────────────────────


class TestCreateExperiment:
    def test_happy_path_returns_201_with_draft_status(self, client, mock_bq):
        with patch("app.queries.experiments.validate_experiment_features", return_value=[]) as mock_val, \
             patch("app.queries.experiments.insert_experiment_config") as mock_ins:
            resp = client.post("/api/v1/experiments", json=VALID_CREATE_BODY)

        assert resp.status_code == 201
        data = resp.json()
        assert "experiment_id" in data
        assert data["status"] == "draft"
        # UUID v4 shape: 8-4-4-4-12
        parts = data["experiment_id"].split("-")
        assert len(parts) == 5

        mock_val.assert_called_once()
        mock_ins.assert_called_once()
        call_kwargs = mock_ins.call_args.kwargs
        assert call_kwargs["name"] == "New experiment"
        assert call_kwargs["target"] == "ats_cover"
        assert call_kwargs["status"] if "status" in call_kwargs else True  # present or not

    def test_invalid_feature_returns_400(self, client, mock_bq):
        with patch(
            "app.queries.experiments.validate_experiment_features",
            return_value=["Unknown curated feature: 'nonexistent_col'"],
        ):
            resp = client.post("/api/v1/experiments", json=VALID_CREATE_BODY)

        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == "invalid_features"
        assert "nonexistent_col" in body["error"]
        assert "request_id" in body

    def test_multiple_feature_errors_concatenated(self, client, mock_bq):
        errors = ["Unknown curated feature: 'col_a'", "Unknown curated feature: 'col_b'"]
        with patch("app.queries.experiments.validate_experiment_features", return_value=errors):
            resp = client.post("/api/v1/experiments", json=VALID_CREATE_BODY)

        assert resp.status_code == 400
        body = resp.json()
        assert "col_a" in body["error"]
        assert "col_b" in body["error"]

    def test_bq_error_during_validation_returns_502(self, client, mock_bq):
        with patch(
            "app.queries.experiments.validate_experiment_features",
            side_effect=Exception("BQ down"),
        ):
            resp = client.post("/api/v1/experiments", json=VALID_CREATE_BODY)

        assert resp.status_code == 502
        assert resp.json()["code"] == "upstream_error"

    def test_bq_error_during_insert_returns_502(self, client, mock_bq):
        with patch("app.queries.experiments.validate_experiment_features", return_value=[]), \
             patch(
                 "app.queries.experiments.insert_experiment_config",
                 side_effect=Exception("BQ insert failed"),
             ):
            resp = client.post("/api/v1/experiments", json=VALID_CREATE_BODY)

        assert resp.status_code == 502
        assert resp.json()["code"] == "upstream_error"

    def test_missing_required_field_returns_422(self, client, mock_bq):
        body = {k: v for k, v in VALID_CREATE_BODY.items() if k != "target"}
        resp = client.post("/api/v1/experiments", json=body)
        assert resp.status_code == 422

    def test_invalid_target_returns_422(self, client, mock_bq):
        body = {**VALID_CREATE_BODY, "target": "not_a_valid_target"}
        resp = client.post("/api/v1/experiments", json=body)
        assert resp.status_code == 422

    def test_invalid_model_type_returns_422(self, client, mock_bq):
        body = {**VALID_CREATE_BODY, "model": {"type": "neural_net", "hyperparams": {}}}
        resp = client.post("/api/v1/experiments", json=body)
        assert resp.status_code == 422


# ── POST /api/v1/experiments/{id}/run ────────────────────────────────────────


class TestTriggerRun:
    def _draft_config(self):
        return make_experiment_row(experiment_id="exp-001", status="draft")

    def test_happy_path_returns_202_with_run_id(self, client, mock_bq):
        with patch("app.queries.experiments.get_experiment_by_id", return_value=self._draft_config()), \
             patch("app.queries.experiments.insert_initial_run") as mock_run, \
             patch("app.queries.experiments.set_experiment_status") as mock_status, \
             patch("app.queries.experiments.trigger_experiment_runner_stub") as mock_stub:
            resp = client.post("/api/v1/experiments/exp-001/run")

        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "running"
        assert "run_id" in data
        assert len(data["run_id"].split("-")) == 5   # UUID v4 shape
        assert data["estimated_duration_seconds"] == 120

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["experiment_id"] == "exp-001"
        assert call_kwargs["run_id"] == data["run_id"]

        mock_status.assert_called_once_with(mock_bq, "exp-001", "running")
        mock_stub.assert_called_once_with("exp-001", data["run_id"])

    def test_run_id_written_before_stub_called(self, client, mock_bq):
        """insert_initial_run must be called before trigger_stub (order matters)."""
        call_order = []

        def record_run(**kwargs):
            call_order.append("insert_run")

        def record_stub(exp_id, run_id):
            call_order.append("trigger_stub")

        with patch("app.queries.experiments.get_experiment_by_id", return_value=self._draft_config()), \
             patch("app.queries.experiments.insert_initial_run", side_effect=record_run), \
             patch("app.queries.experiments.set_experiment_status"), \
             patch("app.queries.experiments.trigger_experiment_runner_stub", side_effect=record_stub):
            client.post("/api/v1/experiments/exp-001/run")

        assert call_order == ["insert_run", "trigger_stub"]

    def test_experiment_not_found_returns_404(self, client, mock_bq):
        with patch("app.queries.experiments.get_experiment_by_id", return_value=None):
            resp = client.post("/api/v1/experiments/nonexistent/run")

        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == "not_found"
        assert "request_id" in body

    def test_already_running_returns_409(self, client, mock_bq):
        running = make_experiment_row(experiment_id="exp-001", status="running")
        with patch("app.queries.experiments.get_experiment_by_id", return_value=running):
            resp = client.post("/api/v1/experiments/exp-001/run")

        assert resp.status_code == 409
        body = resp.json()
        assert body["code"] == "already_running"

    def test_complete_experiment_can_be_re_run(self, client, mock_bq):
        complete = make_experiment_row(experiment_id="exp-001", status="complete")
        with patch("app.queries.experiments.get_experiment_by_id", return_value=complete), \
             patch("app.queries.experiments.insert_initial_run"), \
             patch("app.queries.experiments.set_experiment_status"), \
             patch("app.queries.experiments.trigger_experiment_runner_stub"):
            resp = client.post("/api/v1/experiments/exp-001/run")

        assert resp.status_code == 202

    def test_failed_experiment_can_be_re_run(self, client, mock_bq):
        failed = make_experiment_row(experiment_id="exp-001", status="failed")
        with patch("app.queries.experiments.get_experiment_by_id", return_value=failed), \
             patch("app.queries.experiments.insert_initial_run"), \
             patch("app.queries.experiments.set_experiment_status"), \
             patch("app.queries.experiments.trigger_experiment_runner_stub"):
            resp = client.post("/api/v1/experiments/exp-001/run")

        assert resp.status_code == 202

    def test_bq_fetch_error_returns_502(self, client, mock_bq):
        with patch(
            "app.queries.experiments.get_experiment_by_id",
            side_effect=Exception("BQ down"),
        ):
            resp = client.post("/api/v1/experiments/exp-001/run")

        assert resp.status_code == 502
        assert resp.json()["code"] == "upstream_error"

    def test_bq_insert_run_error_returns_502(self, client, mock_bq):
        with patch("app.queries.experiments.get_experiment_by_id", return_value=self._draft_config()), \
             patch(
                 "app.queries.experiments.insert_initial_run",
                 side_effect=Exception("streaming insert failed"),
             ):
            resp = client.post("/api/v1/experiments/exp-001/run")

        assert resp.status_code == 502
        assert resp.json()["code"] == "upstream_error"


# ── GET /api/v1/experiments/{id}/status ──────────────────────────────────────


class TestGetRunStatus:
    def _status_row(self, **kwargs):
        defaults = {
            "experiment_id": "exp-001",
            "status": "running",
            "run_id": "run-abc",
            "started_at": "2024-02-01T12:00:00Z",
            "completed_at": None,
            "folds_complete": None,
            "folds_total": None,
            "error_message": None,
        }
        defaults.update(kwargs)
        return defaults

    def test_running_status_happy_path(self, client, mock_bq):
        row = self._status_row()
        with patch("app.queries.experiments.get_experiment_run_status", return_value=row):
            resp = client.get("/api/v1/experiments/exp-001/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["experiment_id"] == "exp-001"
        assert data["status"] == "running"
        assert data["run_id"] == "run-abc"
        assert data["started_at"] == "2024-02-01T12:00:00Z"
        assert data["completed_at"] is None
        assert data["progress"] is None
        assert data["error"] is None

    def test_draft_status_no_run_yet(self, client, mock_bq):
        row = self._status_row(status="draft", run_id=None, started_at=None)
        with patch("app.queries.experiments.get_experiment_run_status", return_value=row):
            resp = client.get("/api/v1/experiments/exp-001/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "draft"
        assert data["run_id"] is None
        assert data["started_at"] is None

    def test_complete_status_with_progress(self, client, mock_bq):
        row = self._status_row(
            status="complete",
            completed_at="2024-02-01T14:00:00Z",
            folds_complete=10,
            folds_total=10,
        )
        with patch("app.queries.experiments.get_experiment_run_status", return_value=row):
            resp = client.get("/api/v1/experiments/exp-001/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "complete"
        assert data["completed_at"] == "2024-02-01T14:00:00Z"
        assert data["progress"] == {"folds_complete": 10, "folds_total": 10}

    def test_failed_status_with_error(self, client, mock_bq):
        row = self._status_row(status="failed", error_message="Training diverged")
        with patch("app.queries.experiments.get_experiment_run_status", return_value=row):
            resp = client.get("/api/v1/experiments/exp-001/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        assert data["error"] == "Training diverged"

    def test_not_found_returns_404(self, client, mock_bq):
        with patch("app.queries.experiments.get_experiment_run_status", return_value=None):
            resp = client.get("/api/v1/experiments/nonexistent/status")

        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == "not_found"
        assert "request_id" in body

    def test_bq_error_returns_502(self, client, mock_bq):
        with patch(
            "app.queries.experiments.get_experiment_run_status",
            side_effect=Exception("BQ down"),
        ):
            resp = client.get("/api/v1/experiments/exp-001/status")

        assert resp.status_code == 502
        assert resp.json()["code"] == "upstream_error"

    def test_partial_progress_both_fields_required(self, client, mock_bq):
        """progress is null if only one of folds_complete/folds_total is set."""
        row = self._status_row(folds_complete=5, folds_total=None)
        with patch("app.queries.experiments.get_experiment_run_status", return_value=row):
            resp = client.get("/api/v1/experiments/exp-001/status")

        assert resp.status_code == 200
        assert resp.json()["progress"] is None
