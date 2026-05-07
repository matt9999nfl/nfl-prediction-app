"""
Tests for:
  POST  /api/v1/datasets/upload
  GET   /api/v1/datasets
  GET   /api/v1/datasets/{dataset_id}
  PUT   /api/v1/datasets/{dataset_id}/schema
  DELETE /api/v1/datasets/{dataset_id}

Strategy:
  - BigQuery client is mocked via conftest.py dependency override.
  - GCS client and upload_file are patched per-test.
  - Background task (process_upload_background) is patched out in upload tests
    so we verify the HTTP contract without running the full BQ+pandas pipeline.
  - Background task internals are tested separately in test_process_upload_background.
"""
import io
import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tests.conftest import make_game_row


# ── Dataset row fixtures ──────────────────────────────────────────────────────


def make_dataset_row(**kwargs):
    defaults = {
        "dataset_id":   "ds-001",
        "name":         "Test dataset",
        "description":  "A test dataset",
        "upload_date":  "2024-03-01T12:00:00Z",
        "join_key_type": None,
        "row_count":    None,
        "column_count": None,
        "license_tag":  "open",
        "status":       "mapping",
        "schema_source": "form",
    }
    defaults.update(kwargs)
    return defaults


def make_column_row(**kwargs):
    defaults = {
        "dataset_id":   "ds-001",
        "column_name":  "separation_yards",
        "semantic_name": None,
        "description":  None,
        "data_type":    "numeric",
        "is_join_key":  False,
        "null_rate":    0.05,
    }
    defaults.update(kwargs)
    return defaults


def _csv_bytes(content: str = "game_id,separation_yards\n2024_01_GB_CHI,3.2\n") -> bytes:
    return content.encode()


# ── POST /api/v1/datasets/upload ─────────────────────────────────────────────


class TestUpload:
    def test_upload_csv_happy_path(self, client, mock_bq):
        with patch("app.routers.datasets.get_storage_client") as mock_gcs_fn, \
             patch("app.routers.datasets.upload_file"), \
             patch("app.routers.datasets.dq.insert_dataset_row"), \
             patch("app.routers.datasets.dq.process_upload_background"):
            resp = client.post(
                "/api/v1/datasets/upload",
                data={"name": "My dataset", "description": "desc", "license_tag": "open"},
                files={"file": ("data.csv", _csv_bytes(), "text/csv")},
            )
        assert resp.status_code == 202
        data = resp.json()
        assert "dataset_id" in data
        assert "schema_job_id" in data
        assert data["status"] == "uploading"

    def test_upload_returns_unique_ids(self, client, mock_bq):
        with patch("app.routers.datasets.get_storage_client"), \
             patch("app.routers.datasets.upload_file"), \
             patch("app.routers.datasets.dq.insert_dataset_row"), \
             patch("app.routers.datasets.dq.process_upload_background"):
            r1 = client.post(
                "/api/v1/datasets/upload",
                data={"name": "d1", "description": "d", "license_tag": "open"},
                files={"file": ("a.csv", _csv_bytes(), "text/csv")},
            )
            r2 = client.post(
                "/api/v1/datasets/upload",
                data={"name": "d2", "description": "d", "license_tag": "open"},
                files={"file": ("b.csv", _csv_bytes(), "text/csv")},
            )
        assert r1.json()["dataset_id"] != r2.json()["dataset_id"]
        assert r1.json()["schema_job_id"] != r2.json()["schema_job_id"]

    def test_upload_xlsx(self, client, mock_bq):
        with patch("app.routers.datasets.get_storage_client"), \
             patch("app.routers.datasets.upload_file"), \
             patch("app.routers.datasets.dq.insert_dataset_row"), \
             patch("app.routers.datasets.dq.process_upload_background"):
            resp = client.post(
                "/api/v1/datasets/upload",
                data={"name": "Excel upload", "description": "x", "license_tag": "licensed_commercial"},
                files={"file": ("data.xlsx", b"fakexlsxbytes", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        # Extension is allowed; parsing will fail inside background task (which is mocked)
        assert resp.status_code == 202

    def test_upload_unsupported_extension_returns_400(self, client, mock_bq):
        resp = client.post(
            "/api/v1/datasets/upload",
            data={"name": "d", "description": "d", "license_tag": "open"},
            files={"file": ("data.parquet", b"bytes", "application/octet-stream")},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["code"] == "invalid_params"
        assert "request_id" in data

    def test_upload_invalid_license_tag_returns_400(self, client, mock_bq):
        resp = client.post(
            "/api/v1/datasets/upload",
            data={"name": "d", "description": "d", "license_tag": "totally_made_up"},
            files={"file": ("data.csv", _csv_bytes(), "text/csv")},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "invalid_params"

    def test_upload_file_too_large_returns_400(self, client, mock_bq):
        big = b"x" * (51 * 1024 * 1024)   # 51 MB
        resp = client.post(
            "/api/v1/datasets/upload",
            data={"name": "big", "description": "d", "license_tag": "open"},
            files={"file": ("big.csv", big, "text/csv")},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "invalid_params"

    def test_upload_gcs_failure_returns_502(self, client, mock_bq):
        with patch("app.routers.datasets.get_storage_client"), \
             patch("app.routers.datasets.upload_file", side_effect=Exception("GCS down")):
            resp = client.post(
                "/api/v1/datasets/upload",
                data={"name": "d", "description": "d", "license_tag": "open"},
                files={"file": ("data.csv", _csv_bytes(), "text/csv")},
            )
        assert resp.status_code == 502
        data = resp.json()
        assert data["code"] == "upstream_error"
        assert "GCS down" not in str(data)   # raw error must not leak

    def test_upload_bq_insert_failure_returns_502(self, client, mock_bq):
        with patch("app.routers.datasets.get_storage_client"), \
             patch("app.routers.datasets.upload_file"), \
             patch("app.routers.datasets.dq.insert_dataset_row", side_effect=Exception("BQ fail")):
            resp = client.post(
                "/api/v1/datasets/upload",
                data={"name": "d", "description": "d", "license_tag": "open"},
                files={"file": ("data.csv", _csv_bytes(), "text/csv")},
            )
        assert resp.status_code == 502
        assert resp.json()["code"] == "upstream_error"

    def test_upload_error_has_request_id(self, client, mock_bq):
        with patch("app.routers.datasets.get_storage_client"), \
             patch("app.routers.datasets.upload_file", side_effect=Exception("fail")):
            resp = client.post(
                "/api/v1/datasets/upload",
                data={"name": "d", "description": "d", "license_tag": "open"},
                files={"file": ("data.csv", _csv_bytes(), "text/csv")},
            )
        assert "request_id" in resp.json()


# ── GET /api/v1/datasets ─────────────────────────────────────────────────────


class TestListDatasets:
    def test_list_happy_path(self, client, mock_bq):
        rows = [make_dataset_row(), make_dataset_row(dataset_id="ds-002")]
        with patch("app.routers.datasets.dq.list_datasets", return_value=(rows, False)):
            resp = client.get("/api/v1/datasets")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) == 2
        assert "pagination" in data

    def test_list_shape(self, client, mock_bq):
        rows = [make_dataset_row()]
        with patch("app.routers.datasets.dq.list_datasets", return_value=(rows, False)):
            resp = client.get("/api/v1/datasets")
        ds = resp.json()["data"][0]
        for field in ["dataset_id", "name", "status", "license_tag", "upload_date"]:
            assert field in ds, f"Missing field: {field}"

    def test_list_invalid_status_filter(self, client, mock_bq):
        resp = client.get("/api/v1/datasets?status=bogus")
        assert resp.status_code == 422

    def test_list_invalid_license_tag_filter(self, client, mock_bq):
        resp = client.get("/api/v1/datasets?license_tag=nope")
        assert resp.status_code == 422

    def test_list_bq_error_returns_502(self, client, mock_bq):
        with patch("app.routers.datasets.dq.list_datasets", side_effect=Exception("BQ fail")):
            resp = client.get("/api/v1/datasets")
        assert resp.status_code == 502
        data = resp.json()
        assert data["code"] == "upstream_error"
        assert "BQ fail" not in str(data)

    def test_list_has_more_cursor(self, client, mock_bq):
        rows = [make_dataset_row(dataset_id=f"ds-{i:03d}") for i in range(50)]
        with patch("app.routers.datasets.dq.list_datasets", return_value=(rows, True)):
            resp = client.get("/api/v1/datasets?limit=50")
        data = resp.json()
        assert data["pagination"]["has_more"] is True
        assert data["pagination"]["next_cursor"] is not None


# ── GET /api/v1/datasets/{dataset_id} ────────────────────────────────────────


class TestGetDataset:
    def test_get_happy_path(self, client, mock_bq):
        row = make_dataset_row(status="ready", join_key_type="game_id", row_count=500, column_count=3)
        cols = [make_column_row(), make_column_row(column_name="game_id", is_join_key=True)]
        with patch("app.routers.datasets.dq.get_dataset", return_value=row), \
             patch("app.routers.datasets.dq.get_dataset_columns", return_value=cols):
            resp = client.get("/api/v1/datasets/ds-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["dataset_id"] == "ds-001"
        assert len(data["columns"]) == 2

    def test_get_not_found(self, client, mock_bq):
        with patch("app.routers.datasets.dq.get_dataset", return_value=None):
            resp = client.get("/api/v1/datasets/does-not-exist")
        assert resp.status_code == 404
        assert resp.json()["code"] == "not_found"

    def test_get_columns_failure_still_returns_200(self, client, mock_bq):
        """Columns are best-effort; failure should not break the dataset response."""
        row = make_dataset_row()
        with patch("app.routers.datasets.dq.get_dataset", return_value=row), \
             patch("app.routers.datasets.dq.get_dataset_columns", side_effect=Exception("columns missing")):
            resp = client.get("/api/v1/datasets/ds-001")
        assert resp.status_code == 200
        assert resp.json()["columns"] == []

    def test_get_bq_error_returns_502(self, client, mock_bq):
        with patch("app.routers.datasets.dq.get_dataset", side_effect=Exception("timeout")):
            resp = client.get("/api/v1/datasets/ds-001")
        assert resp.status_code == 502
        assert resp.json()["code"] == "upstream_error"


# ── PUT /api/v1/datasets/{dataset_id}/schema ─────────────────────────────────


_SCHEMA_BODY = {
    "join_key_type": "game_id",
    "join_key_columns": {"game_id": "game_id"},
    "columns": [
        {
            "column_name": "separation_yards",
            "semantic_name": "receiver_separation_avg",
            "description": "Avg separation at target",
            "data_type": "numeric",
        }
    ],
}


class TestUpdateSchema:
    def test_update_schema_happy_path(self, client, mock_bq):
        existing_row = make_dataset_row(status="mapping")
        updated_row = make_dataset_row(status="ready", join_key_type="game_id")
        existing_cols = [make_column_row(column_name="game_id"), make_column_row()]
        with patch("app.routers.datasets.dq.get_dataset", side_effect=[existing_row, updated_row]), \
             patch("app.routers.datasets.dq.get_dataset_columns", return_value=existing_cols), \
             patch("app.routers.datasets.dq.replace_dataset_columns"), \
             patch("app.routers.datasets.dq.update_dataset_schema_metadata"):
            resp = client.put("/api/v1/datasets/ds-001/schema", json=_SCHEMA_BODY)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["join_key_type"] == "game_id"

    def test_update_schema_dataset_not_found(self, client, mock_bq):
        with patch("app.routers.datasets.dq.get_dataset", return_value=None):
            resp = client.put("/api/v1/datasets/nope/schema", json=_SCHEMA_BODY)
        assert resp.status_code == 404
        assert resp.json()["code"] == "not_found"

    def test_update_schema_unknown_column(self, client, mock_bq):
        existing_row = make_dataset_row()
        # Only "game_id" exists — "separation_yards" does not.
        with patch("app.routers.datasets.dq.get_dataset", return_value=existing_row), \
             patch("app.routers.datasets.dq.get_dataset_columns", return_value=[
                 make_column_row(column_name="game_id"),
             ]):
            resp = client.put("/api/v1/datasets/ds-001/schema", json=_SCHEMA_BODY)
        assert resp.status_code == 400
        assert resp.json()["code"] == "invalid_params"

    def test_update_schema_wrong_join_key_fields(self, client, mock_bq):
        existing_row = make_dataset_row()
        body = {**_SCHEMA_BODY, "join_key_type": "player_season_week",
                "join_key_columns": {"game_id": "game_id"}}  # wrong keys for player_season_week
        with patch("app.routers.datasets.dq.get_dataset", return_value=existing_row):
            resp = client.put("/api/v1/datasets/ds-001/schema", json=body)
        assert resp.status_code == 400
        assert resp.json()["code"] == "invalid_params"

    def test_update_schema_bq_error_returns_502(self, client, mock_bq):
        row = make_dataset_row()
        cols = [make_column_row(column_name="game_id"), make_column_row()]
        with patch("app.routers.datasets.dq.get_dataset", return_value=row), \
             patch("app.routers.datasets.dq.get_dataset_columns", return_value=cols), \
             patch("app.routers.datasets.dq.replace_dataset_columns", side_effect=Exception("DML fail")):
            resp = client.put("/api/v1/datasets/ds-001/schema", json=_SCHEMA_BODY)
        assert resp.status_code == 502
        assert resp.json()["code"] == "upstream_error"


# ── DELETE /api/v1/datasets/{dataset_id} ─────────────────────────────────────


class TestDeleteDataset:
    def test_delete_happy_path(self, client, mock_bq):
        with patch("app.routers.datasets.dq.get_dataset", return_value=make_dataset_row()), \
             patch("app.routers.datasets.dq.is_dataset_referenced_in_experiments", return_value=False), \
             patch("app.routers.datasets.dq.delete_dataset"):
            resp = client.delete("/api/v1/datasets/ds-001")
        assert resp.status_code == 204
        assert resp.content == b""   # 204 No Content

    def test_delete_not_found(self, client, mock_bq):
        with patch("app.routers.datasets.dq.get_dataset", return_value=None):
            resp = client.delete("/api/v1/datasets/does-not-exist")
        assert resp.status_code == 404
        assert resp.json()["code"] == "not_found"

    def test_delete_referenced_by_experiment_returns_409(self, client, mock_bq):
        with patch("app.routers.datasets.dq.get_dataset", return_value=make_dataset_row()), \
             patch("app.routers.datasets.dq.is_dataset_referenced_in_experiments", return_value=True):
            resp = client.delete("/api/v1/datasets/ds-001")
        assert resp.status_code == 409
        data = resp.json()
        assert data["code"] == "conflict"
        assert "request_id" in data

    def test_delete_bq_error_returns_502(self, client, mock_bq):
        with patch("app.routers.datasets.dq.get_dataset", return_value=make_dataset_row()), \
             patch("app.routers.datasets.dq.is_dataset_referenced_in_experiments", return_value=False), \
             patch("app.routers.datasets.dq.delete_dataset", side_effect=Exception("BQ fail")):
            resp = client.delete("/api/v1/datasets/ds-001")
        assert resp.status_code == 502
        assert resp.json()["code"] == "upstream_error"

    def test_delete_reference_check_error_returns_502(self, client, mock_bq):
        with patch("app.routers.datasets.dq.get_dataset", return_value=make_dataset_row()), \
             patch("app.routers.datasets.dq.is_dataset_referenced_in_experiments",
                   side_effect=Exception("BQ fail")):
            resp = client.delete("/api/v1/datasets/ds-001")
        assert resp.status_code == 502


# ── Unit tests: file parsing and column stats ─────────────────────────────────


class TestFileParsing:
    """Test parse_file and compute_column_stats directly (no HTTP layer)."""

    def test_parse_csv(self):
        from app.queries.datasets import parse_file
        csv = b"game_id,yards\n2024_01_GB_CHI,3.2\n2024_02_GB_CHI,4.1\n"
        df = parse_file(csv, "csv")
        assert list(df.columns) == ["game_id", "yards"]
        assert len(df) == 2

    def test_parse_json(self):
        from app.queries.datasets import parse_file
        data = json.dumps([{"col_a": 1, "col_b": "x"}, {"col_a": 2, "col_b": "y"}]).encode()
        df = parse_file(data, "json")
        assert set(df.columns) == {"col_a", "col_b"}
        assert len(df) == 2

    def test_parse_unsupported_extension_raises(self):
        from app.queries.datasets import parse_file
        with pytest.raises(ValueError, match="Unsupported"):
            parse_file(b"data", "parquet")

    def test_compute_column_stats_numeric(self):
        from app.queries.datasets import compute_column_stats
        df = pd.DataFrame({"yards": [1.0, 2.0, None, 4.0]})
        stats = compute_column_stats(df)
        assert len(stats) == 1
        s = stats[0]
        assert s["column_name"] == "yards"
        assert s["data_type"] == "numeric"
        assert abs(s["null_rate"] - 0.25) < 1e-6

    def test_compute_column_stats_categorical(self):
        from app.queries.datasets import compute_column_stats
        df = pd.DataFrame({"team": ["GB", "CHI", "GB"]})
        stats = compute_column_stats(df)
        assert stats[0]["data_type"] == "categorical"
        assert stats[0]["null_rate"] == 0.0

    def test_compute_column_stats_boolean(self):
        from app.queries.datasets import compute_column_stats
        df = pd.DataFrame({"covered": [True, False, True]})
        stats = compute_column_stats(df)
        assert stats[0]["data_type"] == "boolean"


# ── Unit tests: background task ───────────────────────────────────────────────


class TestProcessUploadBackground:
    """Test process_upload_background with mocked BQ calls."""

    def test_happy_path_updates_status_to_mapping(self):
        from app.queries.datasets import process_upload_background
        csv = b"game_id,yards\n2024_01_GB_CHI,3.2\n"
        mock_bq = MagicMock()
        with patch("app.queries.datasets.load_dataframe_to_bigquery") as mock_load, \
             patch("app.queries.datasets.insert_dataset_columns_rows") as mock_cols, \
             patch("app.queries.datasets.update_dataset_after_processing") as mock_update:
            process_upload_background("ds-001", csv, "csv", mock_bq)
        mock_load.assert_called_once()
        mock_cols.assert_called_once()
        mock_update.assert_called_once_with(mock_bq, "ds-001", "mapping", 1, 2)

    def test_parse_failure_updates_status_to_error(self):
        from app.queries.datasets import process_upload_background
        mock_bq = MagicMock()
        with patch("app.queries.datasets.parse_file", side_effect=Exception("bad CSV")), \
             patch("app.queries.datasets.update_dataset_after_processing") as mock_update:
            process_upload_background("ds-001", b"bad", "csv", mock_bq)
        mock_update.assert_called_once_with(mock_bq, "ds-001", "error", None, None)

    def test_bq_load_failure_updates_status_to_error(self):
        from app.queries.datasets import process_upload_background
        csv = b"game_id,yards\n2024_01_GB_CHI,3.2\n"
        mock_bq = MagicMock()
        with patch("app.queries.datasets.load_dataframe_to_bigquery", side_effect=Exception("BQ load fail")), \
             patch("app.queries.datasets.update_dataset_after_processing") as mock_update:
            process_upload_background("ds-001", csv, "csv", mock_bq)
        mock_update.assert_called_once_with(mock_bq, "ds-001", "error", None, None)
