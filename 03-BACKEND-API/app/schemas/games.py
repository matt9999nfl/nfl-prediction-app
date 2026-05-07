"""
Game schemas.  Matches API_CONTRACTS.md → Game type exactly.

NOTE — Ambiguity flagged for PROJECT-LEAD:
  GET /api/v1/games/{game_id} returns Game "extended with play_count, team_stats".
  The `team_stats` field is not typed in API_CONTRACTS.md.  We implement it as an
  optional dict with per-team pass/rush/total yards and score, derived from
  curated.plays.  Confirm or refine shape before FRONTEND integrates.
"""
from typing import Literal
from pydantic import BaseModel

from app.schemas.common import Pagination


class Game(BaseModel):
    game_id: str
    season: int
    week: int
    game_date: str                  # ISO 8601 date string
    home_team: str                  # 3-letter nflfastR code
    away_team: str
    home_score: int | None = None
    away_score: int | None = None
    status: Literal["scheduled", "final"]
    home_spread_close: float | None = None   # home perspective; negative = home favoured
    total_close: float | None = None
    home_covered: bool | None = None
    div_game: bool | None = None
    roof: str | None = None
    temp: float | None = None
    wind: float | None = None


class TeamStatLine(BaseModel):
    """Per-team aggregate stats for a completed game.

    Derived from curated.plays.  Fields are null for scheduled games or when
    curated.plays is not yet populated for this game_id.
    """
    score: int | None = None
    pass_yards: float | None = None
    rush_yards: float | None = None
    total_yards: float | None = None
    pass_attempts: int | None = None
    rush_attempts: int | None = None


class TeamStats(BaseModel):
    home: TeamStatLine
    away: TeamStatLine


class GameDetail(Game):
    """Game extended with play-level aggregates (returned by GET /games/{game_id})."""
    play_count: int | None = None
    team_stats: TeamStats | None = None


class GameListResponse(BaseModel):
    data: list[Game]
    pagination: Pagination
