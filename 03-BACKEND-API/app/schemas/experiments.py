"""
Experiment, BacktestRun, and Prediction schemas.
Matches API_CONTRACTS.md → ExperimentConfig, BacktestRun, and prediction response.

run_id ruling (Step 1, #3): run_id is now a required field on new BacktestRun rows.
Kept optional here for backward-compat with pre-Phase-2 rows that may not have it.
"""
from typing import Literal, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import Pagination
from app.schemas.features import DeprecatedFeatureInfo


# ── Phase 4 / Deliverable 3.1: Per-fold result ───────────────────────────────

class FoldResult(BaseModel):
    """Per-season fold summary from experiments.backtest_predictions."""
    season: int
    wins: int
    losses: int
    pushes: int
    hit_rate: float | None = None
    n_games: int


# ── Phase 4 / Deliverable 3.2: Feature importance ────────────────────────────

class FeatureImportanceItem(BaseModel):
    feature: str
    importance: float


class FeatureImportanceResponse(BaseModel):
    run_id: str | None = None
    features: list[FeatureImportanceItem] = Field(default_factory=list)


# ── Experiment sub-types ──────────────────────────────────────────────────────

class GameUniverseFilter(BaseModel):
    field: Literal["div_game", "week"]
    operator: Literal["eq", "gte", "lte", "ne"]
    value: Union[bool, int]

    @model_validator(mode="after")
    def value_type_matches_field(self) -> "GameUniverseFilter":
        if self.field == "div_game" and not isinstance(self.value, bool):
            raise ValueError("div_game filter value must be a boolean")
        if self.field == "week" and isinstance(self.value, bool):
            raise ValueError("week filter value must be an integer, not a boolean")
        if self.field == "week" and not isinstance(self.value, int):
            raise ValueError("week filter value must be an integer")
        return self


class FeatureRef(BaseModel):
    dataset: str
    column: str
    semantic_name: str | None = None   # optional — may not be stored in older configs


class EvaluationConfig(BaseModel):
    metric: Literal["ats_hit_rate", "accuracy", "log_loss", "rmse"]
    success_threshold: float
    min_sample: int


class MethodologyConfig(BaseModel):
    type: Literal["walk_forward"] = "walk_forward"   # default for legacy rows missing this field
    train_seasons: int
    test_seasons: int
    start_season: int
    end_season: int
    game_universe: Optional[GameUniverseFilter] = None


class ModelConfig(BaseModel):
    type: Literal["xgboost", "logistic_regression", "random_forest"]
    hyperparams: dict = Field(default_factory=dict)


# ── Core types ────────────────────────────────────────────────────────────────

class ExperimentConfig(BaseModel):
    experiment_id: str
    name: str
    created_at: str                    # ISO 8601
    # Legacy BQ rows may have target values that predate the current enum;
    # accept any string so old experiments don't crash the list endpoint.
    target: str
    features: list[FeatureRef]
    evaluation: EvaluationConfig
    methodology: MethodologyConfig
    model: ModelConfig
    status: Literal["draft", "running", "complete", "failed"]
    gate_passed: bool | None = None
    has_deprecated_features: bool = False   # BUG-002: lightweight flag for list UI


class BacktestRun(BaseModel):
    run_id: str | None = None          # not in original contract spec; added — see note above
    experiment_id: str
    name: str
    run_at: str                        # ISO 8601
    model_type: str
    features: list[str]
    ats_hit_rate: float | None = None
    n_games_evaluated: int | None = None
    gate_passed: bool | None = None
    notes: str | None = None


# ── Compound responses ────────────────────────────────────────────────────────

class ExperimentDetailResponse(BaseModel):
    config: ExperimentConfig
    latest_run: BacktestRun | None = None
    run_history: list[BacktestRun] = Field(default_factory=list)
    per_fold: list[FoldResult] = Field(default_factory=list)
    deprecated_features: list[DeprecatedFeatureInfo] = Field(default_factory=list)  # BUG-002


class ExperimentListResponse(BaseModel):
    data: list[ExperimentConfig]
    pagination: Pagination


# ── Predictions ───────────────────────────────────────────────────────────────

class PredictionItem(BaseModel):
    game_id: str
    season: int
    week: int
    fold: int | None = None    # walk-forward fold index; None for non-walk-forward runs
    home_team: str
    away_team: str
    predicted_home_cover_prob: float
    predicted_side: Literal["home", "away"]
    actual_home_covered: bool | None = None
    correct: int | None = None
    confidence_tier: Literal["high", "medium", "low"] | None = None


class PredictionListResponse(BaseModel):
    data: list[PredictionItem]
    pagination: Pagination


# ── Step 3: write / trigger schemas ──────────────────────────────────────────

class ExperimentCreateRequest(BaseModel):
    """
    Body for POST /api/v1/experiments.
    experiment_id, created_at, status, and gate_passed are server-assigned.
    """
    name: str
    target: Literal["ats_cover", "outright_winner", "total_over", "team_total_yards"]
    features: list[FeatureRef]
    evaluation: EvaluationConfig
    methodology: MethodologyConfig
    model: ModelConfig


class ExperimentCreateResponse(BaseModel):
    """201 response for POST /api/v1/experiments."""
    experiment_id: str
    status: str = "draft"


class ExperimentRunResponse(BaseModel):
    """202 response for POST /api/v1/experiments/{id}/run."""
    run_id: str
    status: str = "running"
    estimated_duration_seconds: int = 120


class RunProgress(BaseModel):
    folds_complete: int
    folds_total: int


class ExperimentRunStatus(BaseModel):
    """
    Response for GET /api/v1/experiments/{id}/status.

    progress, completed_at, and error are null in Phase 2 (stub runner).
    The MODELING runner will populate these fields when it writes results to
    experiments.backtest_runs.
    """
    experiment_id: str
    run_id: str | None = None
    status: Literal["draft", "running", "complete", "failed"]
    progress: RunProgress | None = None
    started_at: str | None = None       # run_at from experiments.backtest_runs
    completed_at: str | None = None     # set by runner on completion
    error: str | None = None            # set by runner on failure


# ── Production predictions endpoint schemas ──────────────────────────────────

class ProductionPredictionItem(BaseModel):
    """Single prediction from the production predictions endpoint."""
    game_id: str
    week: int
    home_team: str
    away_team: str
    predicted_home_cover_prob: float
    predicted_side: Literal["home", "away"]
    actual_home_covered: bool | None = None
    correct: bool | None = None
    confidence_tier: Literal["high", "medium", "low"] | None = None


class ProductionPredictionsResponse(BaseModel):
    """Response for GET /api/v1/predictions?season=N&week=N."""
    experiment_id: str
    experiment_name: str
    season: int
    week: int
    generated_at: str              # ISO 8601 — completed_at from backtest_runs
    data: list[ProductionPredictionItem]
