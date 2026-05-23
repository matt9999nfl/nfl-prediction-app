"""
BigQuery queries for the /teams endpoints.

curated.plays columns used here:
  posteam     — offensive team abbreviation
  season      — season year (partition key)
  week        — week number
  play_type   — 'pass' or 'run' (plus others we filter out)
  epa         — expected points added
  down        — down number (non-null = official scrimmage play)

Cumulative season-to-date logic:
  For each (team, season, week=W), aggregate all plays from
  weeks 1..(W) of that season. This gives a snapshot of OL
  performance as it stood heading into week W+1 — matching the
  look-ahead-safe logic used by the MODELING layer.

Partition constraint:
  curated.plays is partitioned on `season`. When a season filter is
  supplied we apply it; otherwise we read all seasons (acceptable for
  a single team time-series query that the user explicitly requests).
"""
import logging
from typing import Any

from google.cloud import bigquery

from app.config import settings

logger = logging.getLogger(__name__)

PROJECT = settings.bigquery_project


def _run_query(
    client: bigquery.Client,
    query: str,
    params: list[bigquery.ScalarQueryParameter],
) -> list[dict[str, Any]]:
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    rows = list(client.query(query, job_config=job_config).result())
    return [dict(row) for row in rows]


def get_ol_rating(
    client: bigquery.Client,
    team: str,
    season: int | None = None,
) -> list[dict[str, Any]]:
    """
    Return cumulative season-to-date OL rating history for a team.

    For each (season, week) where the team appeared as the offensive team,
    compute the average ol_rush_epa and ol_pass_epa across all plays from
    week 1 through that week of that season.

    Pass plays: play_type = 'pass', down IS NOT NULL
    Rush plays: play_type = 'run',  down IS NOT NULL

    Season filter is applied when provided to leverage the partition key.
    Returns rows ordered by season ASC, week ASC.
    """
    season_filter = "AND p.season = @season" if season is not None else ""
    params: list[bigquery.ScalarQueryParameter] = [
        bigquery.ScalarQueryParameter("team", "STRING", team),
    ]
    if season is not None:
        params.append(bigquery.ScalarQueryParameter("season", "INT64", season))

    # Step 1: aggregate per-game pass and rush stats for the team.
    # Step 2: for each (season, week), compute cumulative averages over
    #         all weeks 1..week in that season.
    query = f"""
        WITH per_week AS (
            -- Offensive pass plays: EPA per pass attempt
            SELECT
                season,
                week,
                SAFE_DIVIDE(
                    SUM(CASE WHEN play_type = 'pass' AND down IS NOT NULL THEN epa ELSE 0 END),
                    NULLIF(COUNTIF(play_type = 'pass' AND down IS NOT NULL), 0)
                ) AS week_pass_epa_per_att,
                -- Offensive rush plays: EPA per rush attempt
                SAFE_DIVIDE(
                    SUM(CASE WHEN play_type = 'run' AND down IS NOT NULL THEN epa ELSE 0 END),
                    NULLIF(COUNTIF(play_type = 'run' AND down IS NOT NULL), 0)
                ) AS week_rush_epa_per_att,
                -- Counts for weighted cumulation
                COUNTIF(play_type = 'pass' AND down IS NOT NULL) AS pass_att,
                COUNTIF(play_type = 'run'  AND down IS NOT NULL) AS rush_att,
                SUM(CASE WHEN play_type = 'pass' AND down IS NOT NULL THEN epa ELSE 0 END) AS pass_epa_sum,
                SUM(CASE WHEN play_type = 'run'  AND down IS NOT NULL THEN epa ELSE 0 END) AS rush_epa_sum
            FROM `{PROJECT}.curated.plays` p
            WHERE p.posteam = @team
              {season_filter}
            GROUP BY season, week
        ),
        cumulative AS (
            SELECT
                season,
                week,
                -- Cumulative pass EPA per att: sum(EPA) / sum(attempts) up to this week
                SAFE_DIVIDE(
                    SUM(pass_epa_sum) OVER (
                        PARTITION BY season
                        ORDER BY week
                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                    ),
                    NULLIF(
                        SUM(pass_att) OVER (
                            PARTITION BY season
                            ORDER BY week
                            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                        ),
                        0
                    )
                ) AS ol_pass_epa_per_att,
                -- Cumulative rush EPA per att: sum(EPA) / sum(attempts) up to this week
                SAFE_DIVIDE(
                    SUM(rush_epa_sum) OVER (
                        PARTITION BY season
                        ORDER BY week
                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                    ),
                    NULLIF(
                        SUM(rush_att) OVER (
                            PARTITION BY season
                            ORDER BY week
                            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                        ),
                        0
                    )
                ) AS ol_rush_epa_per_att
            FROM per_week
        )
        SELECT
            season,
            week,
            ol_rush_epa_per_att,
            ol_pass_epa_per_att
        FROM cumulative
        ORDER BY season ASC, week ASC
    """

    return _run_query(client, query, params)
