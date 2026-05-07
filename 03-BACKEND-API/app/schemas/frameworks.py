"""
Framework schemas.
Matches API_CONTRACTS.md → Framework type.

A Framework is a named, saved experiment config used as a reusable template.
It stores a full ExperimentConfig snapshot so it is independent of the source
experiment (which may be deleted or re-run without affecting the framework).

POST body rules (enforced by model_validator):
  - Provide EITHER base_experiment_id OR config — not both, not neither.
  - If base_experiment_id: router fetches config from platform.experiment_configs.
  - If config: caller supplies the full config parameters directly.

PUT body:
  - All fields optional; at least one must be present.
"""
from pydantic import BaseModel, Field, model_validator

from app.schemas.common import Pagination
from app.schemas.experiments import ExperimentConfig, ExperimentCreateRequest


# ── Core type ─────────────────────────────────────────────────────────────────


class Framework(BaseModel):
    framework_id: str
    name: str
    description: str
    created_at: str                         # ISO 8601
    updated_at: str                         # ISO 8601
    base_experiment_id: str | None = None   # experiment this was saved from (if any)
    config: ExperimentConfig                # full saved config snapshot


# ── List response ─────────────────────────────────────────────────────────────


class FrameworkListResponse(BaseModel):
    data: list[Framework]
    pagination: Pagination


# ── Write schemas ─────────────────────────────────────────────────────────────


class FrameworkCreateRequest(BaseModel):
    """
    POST /api/v1/frameworks body.

    Exactly one source must be supplied:
      - base_experiment_id: copy config snapshot from an existing experiment.
      - config: provide the config fields directly (no source experiment).
    """
    name: str
    description: str
    base_experiment_id: str | None = None
    config: ExperimentCreateRequest | None = None

    @model_validator(mode="after")
    def validate_config_source(self) -> "FrameworkCreateRequest":
        has_exp = self.base_experiment_id is not None
        has_cfg = self.config is not None
        if not has_exp and not has_cfg:
            raise ValueError(
                "Either 'base_experiment_id' or 'config' must be provided"
            )
        if has_exp and has_cfg:
            raise ValueError(
                "Provide either 'base_experiment_id' or 'config', not both"
            )
        return self


class FrameworkUpdateRequest(BaseModel):
    """
    PUT /api/v1/frameworks/{id} body.
    All fields optional — omitted fields are left unchanged.
    At least one field must be present.
    """
    name: str | None = None
    description: str | None = None
    config: ExperimentCreateRequest | None = None

    @model_validator(mode="after")
    def validate_has_update(self) -> "FrameworkUpdateRequest":
        if self.name is None and self.description is None and self.config is None:
            raise ValueError("At least one field (name, description, config) must be provided")
        return self
