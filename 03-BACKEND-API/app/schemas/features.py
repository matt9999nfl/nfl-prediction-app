"""
Feature schema.  Matches API_CONTRACTS.md → Available Features response.
"""
from pydantic import BaseModel


class Feature(BaseModel):
    feature_id: str         # e.g. "curated.home_ol_pass_epa_per_att" or "user_datasets.abc.col"
    semantic_name: str
    description: str
    dataset: str            # "curated" or "user_datasets.{dataset_id}"
    data_type: str          # "numeric" | "categorical" | "boolean"
    join_key_type: str      # "game_id" | "player_season_week" | "team_season_week"
    license_tag: str        # "open" | "licensed_commercial" | "personal_use_only"


class FeatureListResponse(BaseModel):
    data: list[Feature]
