"""
Runtime configuration loaded from environment variables.
All settings have sane defaults so the service starts without a .env file
(ADC handles BigQuery credentials on Cloud Run automatically).
"""
import os
from datetime import date


def _get_current_nfl_season() -> int:
    """Best-guess 'current' NFL season based on calendar date.

    NFL seasons start in September.  If today is before September, the
    most-recently-completed season is the previous calendar year.
    """
    today = date.today()
    return today.year if today.month >= 9 else today.year - 1


class Settings:
    bigquery_project: str = os.getenv("BIGQUERY_PROJECT", "nfl-model-471509")
    api_version: str = os.getenv("API_VERSION", "0.1.0")
    git_commit: str = os.getenv("GIT_COMMIT", "unknown")
    owner_api_key: str | None = (os.getenv("OWNER_API_KEY") or "").strip() or None  # Phase 3
    default_season: int = _get_current_nfl_season()

    # ── Production forward predictions (DEC-A / DEC-C) ────────────────────────
    #
    # The designated experiment that serves GET /api/v1/predictions for upcoming
    # games.  This exists because no experiment has ever cleared its success
    # gate, and DEC-C ruled that gate-passing is NOT a prerequisite for emitting
    # a forward prediction — but the honest-evaluation banner IS.  So the
    # endpoint may serve this experiment ungated, and reports gate_passed
    # truthfully in the response so the UI cannot present it as validated.
    #
    # Set to "" to disable ungated serving entirely and require a gate-passed
    # experiment, which is the original Phase 3 behaviour.
    production_experiment_id: str = os.getenv(
        "PRODUCTION_EXPERIMENT_ID", "00000000-0000-4000-8000-00000000f0re"
    ).strip()

    # ── Claude API (Step 5 — schema inference) ────────────────────────────────
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    # Fast, capable model for structured JSON inference tasks.
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

    # Pagination limits
    games_default_limit: int = 50
    games_max_limit: int = 200
    experiments_default_limit: int = 50
    experiments_max_limit: int = 200
    predictions_default_limit: int = 100
    predictions_max_limit: int = 500


settings = Settings()
