"""
Teams endpoints.

GET /api/v1/teams/{team}/ol-rating
  Returns season-to-date OL rating history (ol_rush_epa_per_att,
  ol_pass_epa_per_att) for a given team, computed directly from
  curated.plays in BigQuery.

Source table: curated.plays — posteam, season, week, play_type, epa, down
"""
import logging
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from google.cloud import bigquery

from app.dependencies import get_bq_client, get_request_id
from app.queries import teams as tq
from app.schemas.common import ErrorResponse
from app.schemas.teams import OLRatingPoint, OLRatingResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/teams", tags=["teams"])

# nflfastR team abbreviations are 2-3 uppercase letters.
_TEAM_RE = re.compile(r"^[A-Z]{2,4}$")


@router.get(
    "/{team}/ol-rating",
    response_model=OLRatingResponse,
    responses={
        400: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
    summary="Season-to-date OL rating history for a team",
    description=(
        "Returns cumulative season-to-date offensive line EPA ratings for each "
        "(season, week) where the team appeared as the offensive team in "
        "`curated.plays`. Each point represents the running average of "
        "`ol_rush_epa_per_att` and `ol_pass_epa_per_att` across all plays from "
        "week 1 through that week of that season. "
        "Optional `season` query param restricts to a single season."
    ),
)
def get_ol_rating(
    team: str,
    request: Request,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
    season: Annotated[
        int | None,
        Query(description="Filter to a single season year (e.g. 2024). Optional."),
    ] = None,
) -> OLRatingResponse:
    # Basic validation — team codes are uppercase letters only.
    team_upper = team.upper()
    if not _TEAM_RE.match(team_upper):
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Invalid team code '{team}'. Expected 2-4 uppercase letters.",
                "code": "invalid_team",
                "request_id": request_id,
            },
        )

    try:
        rows = tq.get_ol_rating(bq, team_upper, season=season)
    except Exception as exc:
        logger.error(
            "[%s] BigQuery error fetching OL rating for team '%s': %s",
            request_id, team_upper, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    ratings = [OLRatingPoint.model_validate(r) for r in rows]
    return OLRatingResponse(team=team_upper, ratings=ratings)
