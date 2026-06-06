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
