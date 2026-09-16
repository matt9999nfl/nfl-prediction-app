#!/usr/bin/env python3
"""
Create the baseline + N-sweep experiment_configs rows for the prior-season
blend backtest (PROMPT-PRIOR-SEASON-BLEND.md §4).

Baseline: current 23 curated features, no blend.
Variants: the blended feature set (predict_upcoming.ALL_CURATED_TEAM_FEATURES_BLEND)
at N = 2, 4, 6, 8. Everything else identical: model, seed, folds, seasons.

Folds: walk-forward, 4 training seasons, 1-season test folds, test seasons
2019-2025 -> start_season=2015, end_season=2025, train_seasons=4, test_seasons=1.

Does NOT touch experiments.backtest_runs/backtest_predictions — those are
written by run_experiment.py when each config is actually run.

Usage:
    python backtests/create_blend_backtest_configs.py
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from google.cloud import bigquery

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from features.ol_metrics import ALL_TEAM_RATE_FEATURES  # noqa: E402
from features.comprehensive import ALL_ADDITIONAL_TEAM_FEATURES  # noqa: E402
from features.situational import SITUATIONAL_TEAM_FEATURES  # noqa: E402
from backtests.predict_upcoming import ALL_CURATED_TEAM_FEATURES_BLEND  # noqa: E402

PROJECT = "nfl-model-471509"
CONFIGS_TABLE = f"{PROJECT}.platform.experiment_configs"

BASE_23 = ALL_TEAM_RATE_FEATURES + ALL_ADDITIONAL_TEAM_FEATURES + SITUATIONAL_TEAM_FEATURES

METHODOLOGY_COMMON = dict(
    type="walk_forward",
    train_seasons=4,
    test_seasons=1,
    start_season=2015,
    end_season=2025,
)


def _feature_refs(cols: list[str]) -> list[dict]:
    return [{"dataset": "curated", "column": c, "semantic_name": c} for c in cols]


def _insert_config(client: bigquery.Client, name: str, description: str,
                    features: list[str], methodology_extra: dict) -> str:
    experiment_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    methodology = {**METHODOLOGY_COMMON, **methodology_extra}
    payload = dict(
        experiment_id=experiment_id,
        name=name,
        description=description,
        target="ats_cover",
        features=json.dumps(_feature_refs(features)),
        evaluation=json.dumps({"metric": "ats_hit_rate", "success_threshold": 0.54, "min_sample": 250}),
        methodology=json.dumps(methodology),
        model=json.dumps({"type": "xgboost", "hyperparams": {"name": "ol_xgb_v2", "random_state": 42}}),
        status="pending",
        run_count=0,
    )
    query = f"""
        INSERT INTO `{CONFIGS_TABLE}`
        (experiment_id, name, description, created_at, updated_at, target,
         features, evaluation, methodology, model, status, gate_passed, run_count)
        VALUES (
            @experiment_id, @name, @description, TIMESTAMP(@now), TIMESTAMP(@now), @target,
            PARSE_JSON(@features), PARSE_JSON(@evaluation), PARSE_JSON(@methodology), PARSE_JSON(@model),
            @status, NULL, @run_count
        )
    """
    params = [
        bigquery.ScalarQueryParameter("experiment_id", "STRING", payload["experiment_id"]),
        bigquery.ScalarQueryParameter("name", "STRING", payload["name"]),
        bigquery.ScalarQueryParameter("description", "STRING", payload["description"]),
        bigquery.ScalarQueryParameter("now", "STRING", now),
        bigquery.ScalarQueryParameter("target", "STRING", payload["target"]),
        bigquery.ScalarQueryParameter("features", "STRING", payload["features"]),
        bigquery.ScalarQueryParameter("evaluation", "STRING", payload["evaluation"]),
        bigquery.ScalarQueryParameter("methodology", "STRING", payload["methodology"]),
        bigquery.ScalarQueryParameter("model", "STRING", payload["model"]),
        bigquery.ScalarQueryParameter("status", "STRING", payload["status"]),
        bigquery.ScalarQueryParameter("run_count", "INT64", payload["run_count"]),
    ]
    client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
    return experiment_id


def main() -> None:
    client = bigquery.Client(project=PROJECT)
    results = {}

    results["baseline"] = _insert_config(
        client,
        name="prior-season-blend-baseline-2026-09",
        description=(
            "Fresh baseline for the prior-season blend backtest (PROMPT-PRIOR-SEASON-BLEND.md §4). "
            "Current 23 curated features, no prior-season blend. Do NOT confuse with any "
            "May-2026 experiment (e.g. v2-23base-faithful-2015-2024-rerun) — those are unreliable "
            "per Matt's ruling and are not used as a baseline here."
        ),
        features=BASE_23,
        methodology_extra={},
    )

    for n in (2, 4, 6, 8):
        results[f"blend_n{n}"] = _insert_config(
            client,
            name=f"prior-season-blend-n{n}-2026-09",
            description=(
                f"Prior-season-blended feature set at N={n} pseudo-games "
                "(PROMPT-PRIOR-SEASON-BLEND.md §3a/§4). Identical to the baseline "
                "config in every other respect: model, seed, folds, seasons."
            ),
            features=ALL_CURATED_TEAM_FEATURES_BLEND,
            methodology_extra={"blend_n": n},
        )

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
