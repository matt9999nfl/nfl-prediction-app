"""
Contract tests for what predict_upcoming.py writes to BigQuery.

Why these exist
---------------
The first two live runs of predict_upcoming.py each failed on a write, after
~90 seconds of BigQuery loads and a model fit:

  run 1: 400 Required field updated_at cannot be null
  run 2: (would have been) backtest_runs missing REQUIRED name / model_type,
         and an n_games column that does not exist -- the field is
         n_games_evaluated

Every one of those was knowable without touching BigQuery. The schemas are
declared in bq_writer.py and in the BACKEND-API's pydantic models, both of which
are just files in this repo. These tests read those declarations and check the
payloads against them, with no credentials and no network.

The second class of bug is subtler and worse: a config row can be accepted by
BigQuery and still be malformed, because the BACKEND parses these JSON blobs
with pydantic when the experiments list endpoint reads them. MethodologyConfig
.type is Literal["walk_forward"] -- writing "forward_prediction", which is what
this script actually does, would take GET /api/v1/experiments down with a 500
for every caller, not just for this row.

Run:
    python -m pytest 02-MODELING/backtests/test_predict_upcoming.py
"""
from __future__ import annotations

import importlib.util
import re
import sys
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
MODELING = HERE.parent
REPO = MODELING.parent
BACKEND = REPO / "03-BACKEND-API"


# ── Import predict_upcoming without its heavy deps ────────────────────────────


def _stub_dependencies():
    """Stub bigquery and the feature/model modules so import needs no creds."""
    google = sys.modules.get("google") or types.ModuleType("google")
    cloud = types.ModuleType("google.cloud")
    bq = types.ModuleType("google.cloud.bigquery")

    class SchemaField:
        def __init__(self, name, field_type, mode="NULLABLE"):
            self.name, self.field_type, self.mode = name, field_type, mode

    class _P:
        def __init__(self, *a, **k):
            pass

    for attr in ("ScalarQueryParameter", "ArrayQueryParameter", "QueryJobConfig",
                 "LoadJobConfig", "Table", "Dataset", "TimePartitioning"):
        setattr(bq, attr, _P)
    bq.SchemaField = SchemaField
    bq.Client = object
    bq.WriteDisposition = types.SimpleNamespace(WRITE_APPEND="WRITE_APPEND")

    google.cloud = cloud
    cloud.bigquery = bq
    sys.modules.update({"google": google, "google.cloud": cloud,
                        "google.cloud.bigquery": bq})

    stubs = {
        "features.ol_metrics": dict(
            load_plays=None, load_games=None, compute_season_to_date_features=None,
            build_game_feature_matrix=None, ALL_TEAM_RATE_FEATURES=[],
            GAME_CONTEXT_FEATURES=[]),
        "features.comprehensive": dict(
            compute_additional_team_features=None, ALL_ADDITIONAL_TEAM_FEATURES=[]),
        "features.situational": dict(
            compute_situational_features=None, add_rest_differential=None,
            SITUATIONAL_TEAM_FEATURES=[]),
        "models.xgb_v2": dict(OLXGBModelV2=object),
        "backtests.bq_writer": dict(PREDS_SCHEMA=[], PREDS_TABLE="p", RUNS_TABLE="r"),
    }
    for parent in ("features", "models", "backtests"):
        sys.modules.setdefault(parent, types.ModuleType(parent))
    for name, attrs in stubs.items():
        mod = types.ModuleType(name)
        mod.__dict__.update(attrs)
        sys.modules[name] = mod


_stub_dependencies()
_spec = importlib.util.spec_from_file_location("pu", HERE / "predict_upcoming.py")
pu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pu)


META = {
    "seasons_trained": [2015, 2025],
    "n_train": 2822,
    "n_predicted": 16,
    "features": ["home_ol_sack_rate", "away_ol_sack_rate"],
    "feature_importance": [],
}


# ── Read the real schema declarations out of the repo ─────────────────────────


def _schema_fields(block_name: str) -> list[tuple[str, str, str]]:
    src = (MODELING / "backtests" / "bq_writer.py").read_text(encoding="utf-8")
    start = src.index(f"{block_name} = [")
    end = src.index("]", start)
    return re.findall(r'SchemaField\("(\w+)",\s*"(\w+)",\s*mode="(\w+)"',
                      src[start:end])


def _backend_schemas():
    """Load the BACKEND's pydantic models, stubbing its internal imports."""
    src = (BACKEND / "app" / "schemas" / "experiments.py").read_text(encoding="utf-8")
    src = src.replace(
        "from app.schemas.common import Pagination",
        "from pydantic import BaseModel as _BM\nclass Pagination(_BM): pass")
    src = src.replace(
        "from app.schemas.features import DeprecatedFeatureInfo",
        "from pydantic import BaseModel as _BM2\nclass DeprecatedFeatureInfo(_BM2): pass")
    # Exec into a real module registered in sys.modules, not a bare dict.
    # Pydantic resolves forward references (list[FeatureRef]) through the
    # defining module's globals; a plain dict leaves the models "not fully
    # defined" and every construction raises PydanticUserError.
    module = types.ModuleType("backend_schemas")
    sys.modules["backend_schemas"] = module
    exec(compile(src, "backend_schemas", "exec"), module.__dict__)
    from pydantic import BaseModel
    for obj in list(vars(module).values()):
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel:
            obj.model_rebuild(force=True)
    return vars(module)


# ── backtest_runs ─────────────────────────────────────────────────────────────


def test_run_row_sends_no_column_that_does_not_exist():
    """The n_games / n_games_evaluated bug."""
    schema = {n for n, _, _ in _schema_fields("RUNS_SCHEMA")}
    unknown = set(pu.build_run_row("rid", META, 2026, 1)) - schema
    assert not unknown, f"columns not in backtest_runs: {sorted(unknown)}"


def test_run_row_supplies_every_required_column():
    """The missing name / model_type bug."""
    required = {n for n, _, m in _schema_fields("RUNS_SCHEMA") if m == "REQUIRED"}
    missing = required - set(pu.build_run_row("rid", META, 2026, 1))
    assert not missing, f"REQUIRED columns not supplied: {sorted(missing)}"


def test_run_row_leaves_ats_record_null_for_unplayed_games():
    """
    A hit rate for a week that has not been played is a number with no meaning.
    --grade fills the per-prediction results once results exist.
    """
    row = pu.build_run_row("rid", META, 2026, 1)
    for field in ("ats_hit_rate", "ats_record_wins",
                  "ats_record_losses", "ats_record_pushes"):
        assert row[field] is None, field


def test_run_row_is_not_gate_passed():
    assert pu.build_run_row("rid", META, 2026, 1)["gate_passed"] is False


# ── experiment_configs ────────────────────────────────────────────────────────


def test_config_payload_validates_against_the_backends_own_model():
    """
    The test that matters most.

    If this row does not satisfy ExperimentConfig, GET /api/v1/experiments
    returns 500 for everyone, not just for this experiment.
    """
    ns = _backend_schemas()
    row = dict(pu.build_config_payload(META, 2026, 1))
    row["created_at"] = "2026-09-10T00:00:00Z"
    row.pop("run_count", None)          # column, not a response field
    validated = ns["ExperimentConfig"](**row)
    assert validated.experiment_id == pu.PRODUCTION_EXPERIMENT_ID
    assert validated.gate_passed is False


def test_methodology_type_is_walk_forward_even_though_this_is_forward_prediction():
    """
    Deliberate, and worth stating so nobody 'fixes' it.

    MethodologyConfig.type is a Literal. "forward_prediction" would be more
    honest and would 500 the list endpoint. The honest description lives in the
    experiment name instead.
    """
    assert pu.build_config_payload(META, 2026, 1)["methodology"]["type"] == "walk_forward"


def test_config_declares_itself_not_gate_passed():
    """DEC-C: the serving layer must be able to say these are unvalidated."""
    assert pu.build_config_payload(META, 2026, 1)["gate_passed"] is False


def test_config_supplies_every_column_the_backend_insert_uses():
    """
    Mirror the column list from the BACKEND's own INSERT into experiment_configs.
    That statement is the de facto schema; anything it lists and we omit is how
    "Required field updated_at cannot be null" happened.
    """
    src = (BACKEND / "app" / "queries" / "experiments.py").read_text(encoding="utf-8")
    start = src.index("INSERT INTO `{PROJECT}.platform.experiment_configs`")
    cols_block = src[start:src.index("VALUES", start)]
    cols = set(re.findall(r"[\w]+", cols_block.split("(", 1)[1]))
    cols -= {"PROJECT", "platform", "experiment_configs", "INSERT", "INTO"}

    ours = set(pu.build_config_payload(META, 2026, 1))
    # created_at / updated_at are set by the SQL via CURRENT_TIMESTAMP().
    ours |= {"created_at", "updated_at"}
    missing = cols - ours
    assert not missing, f"config payload omits {sorted(missing)}"


def test_features_have_the_shape_the_backend_expects():
    ns = _backend_schemas()
    for f in pu.build_config_payload(META, 2026, 1)["features"]:
        ns["FeatureRef"](**f)


# ── The identity that ties it together ────────────────────────────────────────


def test_production_experiment_id_matches_the_backend_default():
    """
    predict_upcoming writes this id; the API serves whatever
    settings.production_experiment_id names. If they drift, predictions are
    written and never served, and the endpoint 404s with no error anywhere.
    """
    cfg = (BACKEND / "app" / "config.py").read_text(encoding="utf-8")
    match = re.search(r'"PRODUCTION_EXPERIMENT_ID",\s*"([^"]+)"', cfg)
    assert match, "backend default PRODUCTION_EXPERIMENT_ID not found"
    assert match.group(1) == pu.PRODUCTION_EXPERIMENT_ID
