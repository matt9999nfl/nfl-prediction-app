# Agent: MODELING

**Rewritten 2026-09-17.** The June version (written when the project was framed around the offensive-line hypothesis) is in `archive/instructions-pre-2026-09-17.md`. Read the repo root `CLAUDE.md` first.

## What you own

Features, models, the experiment runner, backtests, live weekly picks and their grading, and the `experiments.*` result tables. You build what lets Matt run experiments and see why the model picks what it picks.

You don't ingest data (DATA-PIPELINE), serve HTTP (BACKEND-API), or deploy (DEVOPS).

## What's here

| Path | What it is |
|---|---|
| `backtests/predict_upcoming.py` | Live picks. Retrains on all completed games, predicts a week, writes to the production experiment (`PRODUCTION_EXPERIMENT_ID`). `--season S --week N`, `--grade` to grade |
| `backtests/run_production_refresh.py` | What the weekly job runs: grade finished weeks, predict the next |
| `backtests/run_experiment.py` | The experiment runner. Reads a `platform.experiment_configs` row and runs it. Default command of the image |
| `backtests/walk_forward.py`, `bq_writer.py` | Backtest harness and BigQuery writes |
| `backtests/create_blend_backtest_configs.py`, `report_blend_backtest.py` | Pattern for creating config rows and reporting a set of runs (ADR-013) |
| `backtests/analyze_experiment.py`, `compare_experiments.py` | Run analysis |
| `backtests/explanations*.py`, `features/families.py` | Per-game explanations. **In progress 2026-09-17** (`00-PROJECT-LEAD/PROMPT-PICK-EXPLANATIONS-AND-EDGE-LAB.md`) |
| `backtests/run_phase1_backtest.py`, `run_situational.py`, root `_*.py` scripts, `RUN.md` | Old (May–June). Don't use as patterns |
| `features/comprehensive.py`, `situational.py`, `ol_metrics.py`, `mismatch.py` | Feature builders, including the prior-season blend |
| `models/ol_xgb.py` | `OLXGBModel`, the base XGBoost wrapper (imputer + scaler) |
| `models/xgb_v2.py` | `OLXGBModelV2`, the production model |
| `experiments/EXPERIMENTS.md` | Experiment log |

## Production setup

- Target: `home_covered` against the closing spread. The closing spread is the label, not a feature (market-aware features are planned as new, selectable features).
- Features: `PRODUCTION_FEATURE_LIST` (blended team stats, `PRODUCTION_BLEND_N = 8`, ADR-013) plus game context and `rest_differential`.
- `build_team_features()` defaults to `blend_n=4`. Always pass the value you mean.
- Tables: `platform.experiment_configs`, `experiments.backtest_runs`, `experiments.backtest_predictions`, and (new) `experiments.prediction_explanations`.

## How it deploys

Committing doesn't deploy. From this folder: `gcloud builds submit --config cloudbuild.yaml .` builds `gcr.io/nfl-model-471509/nfl-experiment-runner`. Then point `nfl-production-refresh` (and, if Matt agrees, `nfl-experiment-runner`) at the new digest. Hand Matt any command that needs his credentials.

## Rules

1. **`n_jobs=1`** on every model. Reproducibility beats speed.
2. **Out of sample only.** Walk-forward by season-week. ADR-013 tuned on 2019–2022 test seasons and confirmed on 2023–2025; reuse that split unless the prompt says otherwise.
3. **Experiments go through config rows and `run_experiment.py`** (ADR-011), so every run is a platform record.
4. **Report with reference rows.** Log loss, Brier, ATS and game count, next to a constant-0.5 row and (where available) the market. State results neutrally in reports; don't add commentary on model quality unless asked.
5. **Every run gets an entry in `experiments/EXPERIMENTS.md`** with a real Notes / Observations section. Invalidated runs are marked `Status: INVALIDATED` with the reason.
6. **May 2026 runs are never evidence.**
7. **Existing feature columns never change meaning.** New things are new columns.
8. **Never rewrite a pick for a kicked-off game.** `replace_week_predictions()` is destructive after kickoff; `grade_completed()` must run straight after it. There is no kickoff lock yet.
9. **Read the live schema before writing** (`preflight()` in `predict_upcoming.py`).
10. **Label and leakage checks are platform checks**, run as part of a run, not as a chat warning.

## Retired framing still in code

Treat these as defects to remove when a prompt covers them: `success_threshold: 0.54` written by `predict_upcoming.py` (charter A-1), the gate language in the `ol_xgb.py` docstring (A-3), `ol_mismatch_flag` in the prediction schema (A-4).

## Tests

`python -m pytest backtests/test_predict_upcoming.py features/test_prior_season_blend.py` plus any new `test_*.py` beside the code.

## Current task

Stage 1 of `00-PROJECT-LEAD/PROMPT-PICK-EXPLANATIONS-AND-EDGE-LAB.md` (in progress).
