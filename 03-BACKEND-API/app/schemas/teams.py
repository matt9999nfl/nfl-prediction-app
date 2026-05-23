"""
Teams schemas — OL rating time series.
"""
from pydantic import BaseModel, Field


class OLRatingPoint(BaseModel):
    """Season-to-date OL rating snapshot for a (team, season, week)."""
    season: int
    week: int
    ol_rush_epa_per_att: float | None = None
    ol_pass_epa_per_att: float | None = None


class OLRatingResponse(BaseModel):
    team: str
    ratings: list[OLRatingPoint] = Field(default_factory=list)
