"""
BigQuery queries for the /games endpoints.

All queries are parameterized — never f-string SQL with user data.
The only dynamic SQL construction is the WHERE-clause fragment assembly,
which uses only static string literals chosen by this code, never raw user input.

Partition constraint:
  curated.games is partitioned (or clustered) on `season`.
  Every query that touches this table MUST include a season predicate.
  list_games() defaults to settings.default_season when the caller omits it.
"""
import json
import logging
from typing import Any

from google.cloud import bigquery

from app.config import settings

logger = logging.getLogger(__name__)

PROJECT = settings.bigquery_project

# ── Helpers ───────────────────────────────────────────────────────────────────


def _run_query(
    client: bigquery.Client,
    query: str,
    params: list[bigquery.ScalarQueryParameter],
) -> list[dict[str, Any]]:
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    rows = list(client.query(query, job_config=job_config).result())
    return [dict(row) for row in rows]


def _game_select() -> str:
    """Standard column list for curated.games → Game schema."""
    return """
        game_id,
        season,
        week,
        CAST(game_date AS STRING)   AS game_date,
        home_team,
        away_team,
        home_score,
        away_score,
        status,
        home_spread_close,
        total_close,
        home_covered,
        div_game,
        roof,
        temp,
        wind
    """


# ── List games ────────────────────────────────────────────────────────────────


def list_games(
    client: bigquery.Client,
    season: int | None,
    week: int | None,
    team: str | None,
    status: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Return a page of games plus a has_more flag.

    Season defaults to settings.default_season so we never do a full scan
    without a partition filter.
    """
    effective_season = season if season is not None else settings.default_season

    conditions: list[str] = ["season = @season"]
    params: list[bigquery.ScalarQueryParameter] = [
        bigquery.ScalarQueryParameter("season", "INT64", effective_season),
    ]

    if week is not None:
        conditions.append("week = @week")
        params.append(bigquery.ScalarQueryParameter("week", "INT64", week))

    if team is not None:
        # Match either side of the matchup.
        conditions.append("(home_team = @team OR away_team = @team)")
        params.append(bigquery.ScalarQueryParameter("team", "STRING", team))

    if status is not None:
        conditions.append("status = @status")
        params.append(bigquery.ScalarQueryParameter("status", "STRING", status))

    where = "WHERE " + " AND ".join(conditions)

    # Fetch one extra row to determine has_more without a separate COUNT query.
    params.extend([
        bigquery.ScalarQueryParameter("lim", "INT64", limit + 1),
        bigquery.ScalarQueryParameter("off", "INT64", offset),
    ])

    query = f"""
        SELECT {_game_select()}
        FROM `{PROJECT}.curated.games`
        {where}
        ORDER BY season DESC, week DESC, game_id ASC
        LIMIT @lim OFFSET @off
    """

    rows = _run_query(client, query, params)
    has_more = len(rows) > limit
    return rows[:limit], has_more


# ── Single game ───────────────────────────────────────────────────────────────


def _extract_season_from_game_id(game_id: str) -> int | None:
    """Parse season from nflfastR game_id format '2024_01_GB_CHI'."""
    try:
        year = int(game_id.split("_")[0])
        if 2000 <= year <= 2100:
            return year
    except (ValueError, IndexError):
        pass
    return None


def get_game_by_id(
    client: bigquery.Client,
    game_id: str,
) -> dict[str, Any] | None:
    """Fetch a single game row.  Returns None if not found."""
    season = _extract_season_from_game_id(game_id)
    if season is None:
        # Unknown format — can't apply partition filter; return not-found.
        logger.warning("Cannot extract season from game_id '%s'; returning None", game_id)
        return None

    query = f"""
        SELECT {_game_select()}
        FROM `{PROJECT}.curated.games`
        WHERE game_id = @game_id
          AND season = @season
        LIMIT 1
    """
    params = [
        bigquery.ScalarQueryParameter("game_id", "STRING", game_id),
        bigquery.ScalarQueryParameter("season", "INT64", season),
    ]
    rows = _run_query(client, query, params)
    return rows[0] if rows else None


# ── Play count for game detail ────────────────────────────────────────────────


def get_play_count(
    client: bigquery.Client,
    game_id: str,
    season: int,
) -> int:
    """Count plays in curated.plays for a given game (season-filtered)."""
    query = f"""
        SELECT COUNT(*) AS cnt
        FROM `{PROJECT}.curated.plays`
        WHERE game_id = @game_id
          AND season = @season
    """
    params = [
        bigquery.ScalarQueryParameter("game_id", "STRING", game_id),
        bigquery.ScalarQueryParameter("season", "INT64", season),
    ]
    rows = _run_query(client, query, params)
    return int(rows[0]["cnt"]) if rows else 0


# ── Team stats for game detail ────────────────────────────────────────────────


def get_team_stats(
    client: bigquery.Client,
    game_id: str,
    season: int,
) -> dict[str, Any] | None:
    """
    Compute per-team aggregate stats from curated.plays for a completed game.

    NOTE — team_stats schema is not defined in API_CONTRACTS.md (ambiguity flagged).
    We derive what we can from curated.plays.  If plays data is unavailable, returns None.
    """
    query = f"""
        SELECT
            posteam                             AS team,
            SUM(pass_attempt)                   AS pass_attempts,
            SUM(rush_attempt)                   AS rush_attempts,
            SUM(yards_gained)                   AS total_yards,
            SUM(IF(pass_attempt = 1, yards_gained, 0)) AS pass_yards,
            SUM(IF(rush_attempt = 1, yards_gained, 0)) AS rush_yards
        FROM `{PROJECT}.curated.plays`
        WHERE game_id = @game_id
          AND season  = @season
          AND posteam IS NOT NULL
        GROUP BY posteam
    """
    params = [
        bigquery.ScalarQueryParameter("game_id", "STRING", game_id),
        bigquery.ScalarQueryParameter("season", "INT64", season),
    ]
    rows = _run_query(client, query, params)
    if not rows:
        return None

    # We need to know which posteam is home / away; look that up from the game row.
    return {row["team"]: row for row in rows}
