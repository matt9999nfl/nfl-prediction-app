"""
GET /api/v1/features

Returns the union of the hardcoded nflfastR catalog and user-uploaded dataset
columns (platform.dataset_columns) where the parent dataset is 'ready'.
No pagination — the catalog is bounded and returned in full.
"""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from google.cloud import bigquery

from app.dependencies import get_bq_client, get_request_id
from app.queries import features as fq
from app.schemas.common import ErrorResponse
from app.schemas.features import Feature, FeatureListResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/features", tags=["features"])


@router.get(
    "",
    response_model=FeatureListResponse,
    responses={502: {"model": ErrorResponse}},
    summary="List all features available to the experiment builder",
    description=(
        "Returns nflfastR-derived features (hardcoded catalog) "
        "plus columns from registered user datasets with status='ready'."
    ),
)
def list_features(
    request: Request,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
    dataset: Annotated[
        str | None,
        Query(description='Filter by dataset, e.g. "curated" or "user_datasets.abc123"'),
    ] = None,
    data_type: Annotated[
        str | None,
        Query(pattern="^(numeric|categorical|boolean)$"),
    ] = None,
    join_key_type: Annotated[
        str | None,
        Query(pattern="^(game_id|player_season_week|team_season_week)$"),
    ] = None,
) -> FeatureListResponse:
    try:
        raw = fq.list_features(
            client=bq,
            dataset=dataset,
            data_type=data_type,
            join_key_type=join_key_type,
        )
    except Exception as exc:
        logger.error("[%s] Error building feature list: %s", request_id, exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail={"error": "Feature list unavailable", "code": "upstream_error", "request_id": request_id},
        )

    features = [Feature.model_validate(f) for f in raw]
    return FeatureListResponse(data=features)
