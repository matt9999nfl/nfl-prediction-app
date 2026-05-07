"""
GET /api/v1/games
GET /api/v1/games/{game_id}

Reads from curated.games (+ curated.plays for game detail).
All BigQuery queries are parameterized; user input never touches SQL text.

Pagination: offset-based cursor (base64-encoded integer offset).
Season: optional for list; derived from game_id for single-game endpoint.
"""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from google.cloud import bigquery

from app.config import settings
from app.dependencies import decode_cursor, encode_cursor, get_bq_client, get_request_id
from app.queries import games as gq
from app.schemas.common import ErrorResponse, Pagination
from app.schemas.games import (
    Game,
    GameDetail,
    GameListResponse,
    TeamStatLine,
    TeamStats,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/games", tags=["games"])


# ── GET /api/v1/games ────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=GameListResponse,
    responses={400: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    summary="List games",
    description=(
        "List games with optional filters.  "
        "Defaults to the current NFL season when `season` is omitted."
    ),
)
def list_games(
    request: Request,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
    season: Annotated[int | None, Query(description="NFL season year (e.g. 2024)")] = None,
    week: Annotated[int | None, Query(ge=1, le=22)] = None,
    team: Annotated[str | None, Query(max_length=3)] = None,
    status: Annotated[str | None, Query(pattern="^(scheduled|final)$")] = None,
    limit: Annotated[int, Query(ge=1, le=settings.games_max_limit)] = settings.games_default_limit,
    cursor: Annotated[str | None, Query()] = None,
) -> GameListResponse:
    offset = decode_cursor(cursor)
    try:
        rows, has_more = gq.list_games(
            client=bq,
            season=season,
            week=week,
            team=team,
            status=status,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        logger.error("[%s] BigQuery error listing games: %s", request_id, exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    next_cursor = encode_cursor(offset + limit) if has_more else None
    games = [Game.model_validate(r) for r in rows]
    return GameListResponse(
        data=games,
        pagination=Pagination(next_cursor=next_cursor, has_more=has_more),
    )


# ── GET /api/v1/games/{game_id} ──────────────────────────────────────────────


@router.get(
    "/{game_id}",
    response_model=GameDetail,
    responses={404: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    summary="Get a single game with full detail",
)
def get_game(
    game_id: str,
    request: Request,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
) -> GameDetail:
    try:
        row = gq.get_game_by_id(bq, game_id)
    except Exception as exc:
        logger.error("[%s] BigQuery error fetching game %s: %s", request_id, game_id, exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": f"Game '{game_id}' not found", "code": "not_found", "request_id": request_id},
        )

    game_season: int = row["season"]

    # Play count (best-effort; don't fail the request if curated.plays is empty)
    play_count: int | None = None
    try:
        play_count = gq.get_play_count(bq, game_id, game_season)
    except Exception as exc:
        logger.warning("[%s] Could not fetch play_count for %s: %s", request_id, game_id, exc)

    # Team stats (best-effort; team_stats is undefined in API_CONTRACTS.md — see note)
    team_stats: TeamStats | None = None
    try:
        raw_stats = gq.get_team_stats(bq, game_id, game_season)
        if raw_stats and row.get("home_team") and row.get("away_team"):
            home_raw = raw_stats.get(row["home_team"], {})
            away_raw = raw_stats.get(row["away_team"], {})
            team_stats = TeamStats(
                home=TeamStatLine(
                    score=row.get("home_score"),
                    pass_yards=home_raw.get("pass_yards"),
                    rush_yards=home_raw.get("rush_yards"),
                    total_yards=home_raw.get("total_yards"),
                    pass_attempts=home_raw.get("pass_attempts"),
                    rush_attempts=home_raw.get("rush_attempts"),
                ),
                away=TeamStatLine(
                    score=row.get("away_score"),
                    pass_yards=away_raw.get("pass_yards"),
                    rush_yards=away_raw.get("rush_yards"),
                    total_yards=away_raw.get("total_yards"),
                    pass_attempts=away_raw.get("pass_attempts"),
                    rush_attempts=away_raw.get("rush_attempts"),
                ),
            )
    except Exception as exc:
        logger.warning("[%s] Could not fetch team_stats for %s: %s", request_id, game_id, exc)

    return GameDetail(**row, play_count=play_count, team_stats=team_stats)
