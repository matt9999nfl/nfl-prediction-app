"""
Tests for Step 5 — POST /api/v1/datasets/{id}/infer-schema.

All Claude API calls are patched via app.claude_inference.infer_dataset_schema.
BQ calls are patched via app.queries.datasets module functions.
"""
import json
from unittest.mock import patch

import pytest

from app.claude_inference import ClaudeInferenceError
from tests.conftest import make_game_row


# ── Shared helpers ────────────────────────────────────────────────────────────


def make_dataset_row(**kwargs):
    defaults = {
        "dataset_id": "ds-001",
        "name": "Snap counts 2024",
        "description": "Player snap count data",
        "upload_date": "2024-06-01T00:00:00Z",
        "join_key_type": None,
        "row_count": 1000,
        "column_count": 5,
        "license_tag": "open",
        "status": "mapping",
        "schema_source": "form",
    }
    defaults.update(kwargs)
    return defaults


EXISTING_COLS = [
    {"column_name": "player_id",       "data_type": "categorical", "null_rate": 0.0,  "semantic_name": None, "description": None, "is_join_key": False},
    {"column_name": "season",          "data_type": "numeric",     "null_rate": 0.0,  "semantic_name": None, "description": None, "is_join_key": False},
    {"column_name": "week",            "data_type": "numeric",     "null_rate": 0.0,  "semantic_name": None, "description": None, "is_join_key": False},
    {"column_name": "snap_count",      "data_type": "numeric",     "null_rate": 0.02, "semantic_name": None, "description": None, "is_join_key": False},
    {"column_name": "snap_pct",        "data_type": "numeric",     "null_rate": 0.05, "semantic_name": None, "description": None, "is_join_key": False},
]

SAMPLE_ROWS = [
    {"player_id": "00-1234567", "season": 2024, "week": 1, "snap_count": 65, "snap_pct": 0.91},
    {"player_id": "00-7654321", "season": 2024, "week": 1, "snap_count": 58, "snap_pct": 0.81},
]

VALID_CLAUDE_RESPONSE = {
    "suggested_join_key_type": "player_season_week",
    "suggested_join_key_columns": {
        "player_id": "player_id",
        "season": "season",
        "week": "week",
    },
    "suggested_columns": [
        {"column_name": "player_id",  "semantic_name": "Player ID",    "description": "GSIS player ID",        "data_type": "categorical"},
        {"column_name": "season",     "semantic_name": "Season",       "description": "NFL season year",       "data_type": "numeric"},
        {"column_name": "week",       "semantic_name": "Week",         "description": "Week number",            "data_type": "numeric"},
        {"column_name": "snap_count", "semantic_name": "Snap Count",   "description": "Total snaps played",    "data_type": "numeric"},
        {"column_name": "snap_pct",   "semantic_name": "Snap %",       "description": "Pct of team snaps",     "data_type": "numeric"},
    ],
    "data_quality_flags": [
        {"column": "snap_pct", "issue": "5% null rate", "severity": "warning"},
    ],
    "confidence": 0.91,
}


def _patch_bq(ds_row=None, col_rows=None, sample=None):
    """Returns a context manager chain patching all three BQ calls."""
    return (
        patch("app.queries.datasets.get_dataset", return_value=ds_row or make_dataset_row()),
        patch("app.queries.datasets.get_dataset_columns", return_value=col_rows or EXISTING_COLS),
        patch("app.queries.datasets.get_dataset_sample_rows", return_value=sample or SAMPLE_ROWS),
    )


# ── Happy path ────────────────────────────────────────────────────────────────


class TestInferSchemaHappyPath:
    def test_returns_200_with_correct_shape(self, client, mock_bq):
        with patch("app.queries.datasets.get_dataset", return_value=make_dataset_row()), \
             patch("app.queries.datasets.get_dataset_columns", return_value=EXISTING_COLS), \
             patch("app.queries.datasets.get_dataset_sample_rows", return_value=SAMPLE_ROWS), \
             patch("app.routers.datasets.settings") as mock_settings, \
             patch("app.routers.datasets.infer_dataset_schema", return_value=VALID_CLAUDE_RESPONSE):
            mock_settings.anthropic_api_key = "sk-test"
            mock_settings.anthropic_model = "claude-haiku-4-5-20251001"
            resp = client.post("/api/v1/datasets/ds-001/infer-schema")

        assert resp.status_code == 200
        data = resp.json()
        assert data["suggested_join_key_type"] == "player_season_week"
        assert data["suggested_join_key_columns"] == {
            "player_id": "player_id", "season": "season", "week": "week"
        }
        assert len(data["suggested_columns"]) == 5
        assert data["confidence"] == 0.91
        assert len(data["data_quality_flags"]) == 1
        assert data["data_quality_flags"][0]["severity"] == "warning"

    def test_suggested_columns_have_correct_fields(self, client, mock_bq):
        with patch("app.queries.datasets.get_dataset", return_value=make_dataset_row()), \
             patch("app.queries.datasets.get_dataset_columns", return_value=EXISTING_COLS), \
             patch("app.queries.datasets.get_dataset_sample_rows", return_value=SAMPLE_ROWS), \
             patch("app.routers.datasets.settings") as mock_settings, \
             patch("app.routers.datasets.infer_dataset_schema", return_value=VALID_CLAUDE_RESPONSE):
            mock_settings.anthropic_api_key = "sk-test"
            mock_settings.anthropic_model = "claude-haiku-4-5-20251001"
            resp = client.post("/api/v1/datasets/ds-001/infer-schema")

        cols = {c["column_name"]: c for c in resp.json()["suggested_columns"]}

        # Join key columns flagged correctly.
        assert cols["player_id"]["is_join_key"] is True
        assert cols["season"]["is_join_key"] is True
        assert cols["week"]["is_join_key"] is True
        assert cols["snap_count"]["is_join_key"] is False

        # null_rate carried from existing column stats.
        assert cols["snap_pct"]["null_rate"] == 0.05
        assert cols["snap_count"]["null_rate"] == 0.02

        # dataset_id populated.
        assert cols["player_id"]["dataset_id"] == "ds-001"

    def test_ready_dataset_also_inferrable(self, client, mock_bq):
        """status='ready' datasets are also valid for inference."""
        with patch("app.queries.datasets.get_dataset", return_value=make_dataset_row(status="ready")), \
             patch("app.queries.datasets.get_dataset_columns", return_value=EXISTING_COLS), \
             patch("app.queries.datasets.get_dataset_sample_rows", return_value=SAMPLE_ROWS), \
             patch("app.routers.datasets.settings") as mock_settings, \
             patch("app.routers.datasets.infer_dataset_schema", return_value=VALID_CLAUDE_RESPONSE):
            mock_settings.anthropic_api_key = "sk-test"
            mock_settings.anthropic_model = "claude-haiku-4-5-20251001"
            resp = client.post("/api/v1/datasets/ds-001/infer-schema")

        assert resp.status_code == 200

    def test_claude_called_with_correct_args(self, client, mock_bq):
        with patch("app.queries.datasets.get_dataset", return_value=make_dataset_row()), \
             patch("app.queries.datasets.get_dataset_columns", return_value=EXISTING_COLS), \
             patch("app.queries.datasets.get_dataset_sample_rows", return_value=SAMPLE_ROWS), \
             patch("app.routers.datasets.settings") as mock_settings, \
             patch("app.routers.datasets.infer_dataset_schema", return_value=VALID_CLAUDE_RESPONSE) as mock_claude:
            mock_settings.anthropic_api_key = "sk-test"
            mock_settings.anthropic_model = "claude-haiku-4-5-20251001"
            client.post("/api/v1/datasets/ds-001/infer-schema")

        mock_claude.assert_called_once()
        call_kwargs = mock_claude.call_args.kwargs
        assert call_kwargs["api_key"] == "sk-test"
        assert call_kwargs["model"] == "claude-haiku-4-5-20251001"
        assert "player_id" in call_kwargs["column_names"]
        assert call_kwargs["sample_rows"] == SAMPLE_ROWS

    def test_invalid_claude_data_type_coerced(self, client, mock_bq):
        """If Claude returns an invalid data_type, fall back to existing column stat."""
        bad_response = {
            **VALID_CLAUDE_RESPONSE,
            "suggested_columns": [
                {"column_name": "snap_count", "semantic_name": "Snap Count",
                 "description": "Total snaps", "data_type": "integer"},  # not a valid type
            ],
        }
        with patch("app.queries.datasets.get_dataset", return_value=make_dataset_row()), \
             patch("app.queries.datasets.get_dataset_columns", return_value=EXISTING_COLS), \
             patch("app.queries.datasets.get_dataset_sample_rows", return_value=SAMPLE_ROWS), \
             patch("app.routers.datasets.settings") as mock_settings, \
             patch("app.routers.datasets.infer_dataset_schema", return_value=bad_response):
            mock_settings.anthropic_api_key = "sk-test"
            mock_settings.anthropic_model = "claude-haiku-4-5-20251001"
            resp = client.post("/api/v1/datasets/ds-001/infer-schema")

        assert resp.status_code == 200
        col = resp.json()["suggested_columns"][0]
        assert col["data_type"] == "numeric"   # from existing_col_rows stats

    def test_confidence_clamped_above_1(self, client, mock_bq):
        over = {**VALID_CLAUDE_RESPONSE, "confidence": 1.5}
        with patch("app.queries.datasets.get_dataset", return_value=make_dataset_row()), \
             patch("app.queries.datasets.get_dataset_columns", return_value=EXISTING_COLS), \
             patch("app.queries.datasets.get_dataset_sample_rows", return_value=SAMPLE_ROWS), \
             patch("app.routers.datasets.settings") as mock_settings, \
             patch("app.routers.datasets.infer_dataset_schema", return_value=over):
            mock_settings.anthropic_api_key = "sk-test"
            mock_settings.anthropic_model = "claude-haiku-4-5-20251001"
            resp = client.post("/api/v1/datasets/ds-001/infer-schema")

        assert resp.json()["confidence"] == 1.0

    def test_empty_sample_rows_still_calls_claude(self, client, mock_bq):
        """Empty table should not block inference — pass empty sample rows."""
        with patch("app.queries.datasets.get_dataset", return_value=make_dataset_row()), \
             patch("app.queries.datasets.get_dataset_columns", return_value=EXISTING_COLS), \
             patch("app.queries.datasets.get_dataset_sample_rows", return_value=[]), \
             patch("app.routers.datasets.settings") as mock_settings, \
             patch("app.routers.datasets.infer_dataset_schema", return_value=VALID_CLAUDE_RESPONSE) as mock_claude:
            mock_settings.anthropic_api_key = "sk-test"
            mock_settings.anthropic_model = "claude-haiku-4-5-20251001"
            resp = client.post("/api/v1/datasets/ds-001/infer-schema")

        assert resp.status_code == 200
        assert mock_claude.call_args.kwargs["sample_rows"] == []


# ── Dataset state errors ──────────────────────────────────────────────────────


class TestInferSchemaDatasetErrors:
    def test_dataset_not_found_returns_404(self, client, mock_bq):
        with patch("app.queries.datasets.get_dataset", return_value=None):
            resp = client.post("/api/v1/datasets/nonexistent/infer-schema")

        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == "not_found"
        assert "request_id" in body

    def test_uploading_status_returns_400(self, client, mock_bq):
        with patch("app.queries.datasets.get_dataset", return_value=make_dataset_row(status="uploading")):
            resp = client.post("/api/v1/datasets/ds-001/infer-schema")

        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == "dataset_not_ready"
        assert "request_id" in body

    def test_error_status_returns_400(self, client, mock_bq):
        with patch("app.queries.datasets.get_dataset", return_value=make_dataset_row(status="error")):
            resp = client.post("/api/v1/datasets/ds-001/infer-schema")

        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == "dataset_not_ready"

    def test_bq_dataset_fetch_error_returns_502(self, client, mock_bq):
        with patch("app.queries.datasets.get_dataset", side_effect=Exception("BQ down")):
            resp = client.post("/api/v1/datasets/ds-001/infer-schema")

        assert resp.status_code == 502
        assert resp.json()["code"] == "upstream_error"

    def test_bq_columns_fetch_error_returns_502(self, client, mock_bq):
        with patch("app.queries.datasets.get_dataset", return_value=make_dataset_row()), \
             patch("app.queries.datasets.get_dataset_columns", side_effect=Exception("BQ down")):
            resp = client.post("/api/v1/datasets/ds-001/infer-schema")

        assert resp.status_code == 502
        assert resp.json()["code"] == "upstream_error"

    def test_bq_sample_rows_error_returns_502(self, client, mock_bq):
        with patch("app.queries.datasets.get_dataset", return_value=make_dataset_row()), \
             patch("app.queries.datasets.get_dataset_columns", return_value=EXISTING_COLS), \
             patch("app.queries.datasets.get_dataset_sample_rows", side_effect=Exception("BQ down")):
            resp = client.post("/api/v1/datasets/ds-001/infer-schema")

        assert resp.status_code == 502
        assert resp.json()["code"] == "upstream_error"


# ── Claude API failures ───────────────────────────────────────────────────────


class TestInferSchemaClaudeFailures:
    def _patch_bq_ok(self):
        return (
            patch("app.queries.datasets.get_dataset", return_value=make_dataset_row()),
            patch("app.queries.datasets.get_dataset_columns", return_value=EXISTING_COLS),
            patch("app.queries.datasets.get_dataset_sample_rows", return_value=SAMPLE_ROWS),
        )

    def _exact_503_shape(self, resp) -> None:
        """Assert the 503 response matches the spec contract exactly."""
        assert resp.status_code == 503
        body = resp.json()
        assert body["error"] == "ai_unavailable"
        assert body["fallback"] == "use_form"
        # Spec does not include request_id or code in this shape.
        assert "request_id" not in body

    def test_claude_api_error_returns_503(self, client, mock_bq):
        with patch("app.queries.datasets.get_dataset", return_value=make_dataset_row()), \
             patch("app.queries.datasets.get_dataset_columns", return_value=EXISTING_COLS), \
             patch("app.queries.datasets.get_dataset_sample_rows", return_value=SAMPLE_ROWS), \
             patch("app.routers.datasets.settings") as mock_settings, \
             patch("app.routers.datasets.infer_dataset_schema", side_effect=ClaudeInferenceError("API timeout")):
            mock_settings.anthropic_api_key = "sk-test"
            mock_settings.anthropic_model = "claude-haiku-4-5-20251001"
            resp = client.post("/api/v1/datasets/ds-001/infer-schema")

        self._exact_503_shape(resp)

    def test_json_parse_error_returns_503(self, client, mock_bq):
        with patch("app.queries.datasets.get_dataset", return_value=make_dataset_row()), \
             patch("app.queries.datasets.get_dataset_columns", return_value=EXISTING_COLS), \
             patch("app.queries.datasets.get_dataset_sample_rows", return_value=SAMPLE_ROWS), \
             patch("app.routers.datasets.settings") as mock_settings, \
             patch("app.routers.datasets.infer_dataset_schema",
                   side_effect=ClaudeInferenceError("Claude response is not valid JSON")):
            mock_settings.anthropic_api_key = "sk-test"
            mock_settings.anthropic_model = "claude-haiku-4-5-20251001"
            resp = client.post("/api/v1/datasets/ds-001/infer-schema")

        self._exact_503_shape(resp)

    def test_missing_keys_in_response_returns_503(self, client, mock_bq):
        with patch("app.queries.datasets.get_dataset", return_value=make_dataset_row()), \
             patch("app.queries.datasets.get_dataset_columns", return_value=EXISTING_COLS), \
             patch("app.queries.datasets.get_dataset_sample_rows", return_value=SAMPLE_ROWS), \
             patch("app.routers.datasets.settings") as mock_settings, \
             patch("app.routers.datasets.infer_dataset_schema",
                   side_effect=ClaudeInferenceError("Claude response missing required keys: ['confidence']")):
            mock_settings.anthropic_api_key = "sk-test"
            mock_settings.anthropic_model = "claude-haiku-4-5-20251001"
            resp = client.post("/api/v1/datasets/ds-001/infer-schema")

        self._exact_503_shape(resp)

    def test_missing_api_key_returns_503_without_calling_claude(self, client, mock_bq):
        """If ANTHROPIC_API_KEY is unset, return 503 immediately without calling Claude."""
        with patch("app.queries.datasets.get_dataset", return_value=make_dataset_row()), \
             patch("app.queries.datasets.get_dataset_columns", return_value=EXISTING_COLS), \
             patch("app.queries.datasets.get_dataset_sample_rows", return_value=SAMPLE_ROWS), \
             patch("app.routers.datasets.settings") as mock_settings, \
             patch("app.routers.datasets.infer_dataset_schema") as mock_claude:
            mock_settings.anthropic_api_key = ""   # empty = not configured
            mock_settings.anthropic_model = "claude-haiku-4-5-20251001"
            resp = client.post("/api/v1/datasets/ds-001/infer-schema")

        self._exact_503_shape(resp)
        mock_claude.assert_not_called()


# ── claude_inference unit tests ───────────────────────────────────────────────


class TestClaudeInferenceModule:
    """Unit tests for the infer_dataset_schema function itself (no HTTP layer)."""

    def test_happy_path_returns_dict(self):
        from app.claude_inference import infer_dataset_schema

        mock_content = type("Block", (), {"text": json.dumps(VALID_CLAUDE_RESPONSE)})()
        mock_message = type("Msg", (), {"content": [mock_content]})()

        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = mock_message
            result = infer_dataset_schema(
                api_key="sk-test",
                model="claude-haiku-4-5-20251001",
                column_names=["player_id", "snap_count"],
                sample_rows=[{"player_id": "00-123", "snap_count": 65}],
            )

        assert result["suggested_join_key_type"] == "player_season_week"
        assert result["confidence"] == 0.91

    def test_strips_json_code_fences(self):
        from app.claude_inference import infer_dataset_schema

        wrapped = f"```json\n{json.dumps(VALID_CLAUDE_RESPONSE)}\n```"
        mock_content = type("Block", (), {"text": wrapped})()
        mock_message = type("Msg", (), {"content": [mock_content]})()

        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = mock_message
            result = infer_dataset_schema("sk-test", "m", ["col"], [])

        assert result["confidence"] == 0.91

    def test_api_error_raises_inference_error(self):
        from app.claude_inference import ClaudeInferenceError, infer_dataset_schema

        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.side_effect = Exception("network error")
            with pytest.raises(ClaudeInferenceError, match="Claude API call failed"):
                infer_dataset_schema("sk-test", "m", ["col"], [])

    def test_non_json_response_raises_inference_error(self):
        from app.claude_inference import ClaudeInferenceError, infer_dataset_schema

        mock_content = type("Block", (), {"text": "Sure! Here are some suggestions..."})()
        mock_message = type("Msg", (), {"content": [mock_content]})()

        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = mock_message
            with pytest.raises(ClaudeInferenceError, match="not valid JSON"):
                infer_dataset_schema("sk-test", "m", ["col"], [])

    def test_missing_key_raises_inference_error(self):
        from app.claude_inference import ClaudeInferenceError, infer_dataset_schema

        incomplete = {k: v for k, v in VALID_CLAUDE_RESPONSE.items() if k != "confidence"}
        mock_content = type("Block", (), {"text": json.dumps(incomplete)})()
        mock_message = type("Msg", (), {"content": [mock_content]})()

        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = mock_message
            with pytest.raises(ClaudeInferenceError, match="missing required keys"):
                infer_dataset_schema("sk-test", "m", ["col"], [])

    def test_non_dict_response_raises_inference_error(self):
        from app.claude_inference import ClaudeInferenceError, infer_dataset_schema

        mock_content = type("Block", (), {"text": json.dumps([1, 2, 3])})()
        mock_message = type("Msg", (), {"content": [mock_content]})()

        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = mock_message
            with pytest.raises(ClaudeInferenceError, match="not a JSON object"):
                infer_dataset_schema("sk-test", "m", ["col"], [])
