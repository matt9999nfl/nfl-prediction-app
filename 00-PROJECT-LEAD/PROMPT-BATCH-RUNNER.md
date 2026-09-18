# PROMPT-BATCH-RUNNER — run many backtests from one file, and the standing reverse-experiment suite

Start in: C:\Users\OEM\OneDrive\Desktop\nfl-prediction-app
Written: 2026-09-18 by PROJECT-LEAD. Stage 3a of 4. Previous: `PROMPT-WEEK1-ANALYSIS.md` (done). Next: PROMPT-MARKET-AND-PATTERN-GRIDS, then the weekly job, then the results pages.

## Matt's request
> I think we need to add extensive back testing and reverse experiments to find an edge. Why aren't we running as many tests as possible each week to find what data has the most effect and potential edges this season?

This stage builds the machinery and runs the first suite. The market tests, the pattern tests from the week analysis, and the weekly automation are the stages after it.

## Task
When this is done, Matt can put one YAML file in front of the platform and get back a set of comparable backtests — each a real platform experiment — with a summary he can read as one thing, and the standing reverse-experiment suite has been run once on 2015–2025.

## Read first
- `00-PROJECT-LEAD/PROJECT-CHARTER.md`, `STATE.md` (Decisions)
- `00-PROJECT-LEAD/context/talking-to-matt.md`
- `02-MODELING/backtests/run_experiment.py`, `walk_forward.py`, `bq_writer.py`, `create_blend_backtest_configs.py` (how a config row is made and run — ADR-011: experiments go through platform config records)
- `02-MODELING/features/families.py` (the family map the suite drops and isolates)
- `docs/DECISIONS.md` ADR-013 (the tuning/confirmation season split)
- `02-MODELING/backtests/reports/week_analysis_2026_wk01.md`, section 4 (the hypotheses; they run in the next stage, but the runner must be able to express them)

## Build

### 1. `02-MODELING/backtests/run_grid.py --grid <file.yaml>`
- Each grid cell becomes one `platform.experiment_configs` row, created the way `create_blend_backtest_configs.py` does it, then run through `run_experiment.py`. A cell's records must be indistinguishable from a wizard-built experiment.
- A grid file has `name`, `question`, a `baseline` cell, and its cells.
- Cells run in parallel as separate processes locally, or as parallel executions of the `nfl-experiment-runner` Cloud Run job with `--remote`. `n_jobs=1` stays inside every run.
- **Default to `--remote`.** Numbers that are evidence come from the production Linux image (`CLAUDE.md` standing rule).
- Idempotent: re-running a grid skips cells already completed with the same config hash. `--force` re-runs.
- Results land in `experiments.grid_results` (grid_id, grid_name, cell, config_id, run_id, metrics, created_at) so a grid reads as one thing.

### 2. Metrics, per cell
Overall, per season, and for week 1, weeks 2–4 and weeks 5+: log loss, Brier score, ATS hit rate, game count, and a seeded bootstrap 95% interval on the difference from the grid's baseline cell.
Every summary carries two reference rows: a constant 0.5 prediction, and the market-implied probability where moneylines exist. Season split as in ADR-013: tune on 2015–2022 folds, confirm on 2023–2025. 2026 is reported separately.

### 3. `02-MODELING/backtests/grids/standing_suite.yaml`
1. **Leave-one-family-out** — drop each family from the production feature set.
2. **One-family-only** — each family alone, plus venue/context.
3. **Add-one-family** — venue/context plus each family, for marginal value.
4. **Permutation importance** — shuffle one feature, then one family, in each fold's test matrix using the already-fitted model. No retraining. This is the fast weekly one.
5. **Counterfactual swaps on the current week's picks** — replace each family's values with the league average, and separately swap home and away values; record how each pick's probability and side move. Store per game so a later stage can show "what would flip this pick".
6. **Blend weight** — N in {8, 10, 12, 16}.
7. **Home/away symmetry** — a differenced version (home − away) of each stat against the current separate home/away features.

### 4. Run it
Run the whole suite once, remote. Write `02-MODELING/backtests/reports/standing_suite_<date>.md`: one table per grid, cells sorted by log loss, with the interval against the baseline and both reference rows. Report what the numbers show, neutrally. No verdict on the model.

## Scope
Allowed to change: `02-MODELING/backtests/run_grid.py`, `grids/**`, `walk_forward.py` and `run_experiment.py` only where the grid needs a hook, `bq_writer.py` for the new table, tests, `reports/**`. New BigQuery table `experiments.grid_results`; new rows in `platform.experiment_configs`, `experiments.backtest_runs`, `backtest_predictions`, `prediction_explanations`.
Must not change: the production feature list, the live prediction path, `predict_upcoming.py` / `run_production_refresh.py` behaviour, stored production picks or their explanations, schedules, the data pipeline.

## Kill-switch
Stop, write to `00-PROJECT-LEAD/QUESTIONS.md`, and tell Matt if:
- a grid cell would write to the production experiment id `00000000-0000-4000-8000-00000000f0re`;
- the baseline cell's metrics differ from the 2026-09-16 blend N=8 backtest by more than the bootstrap interval (that would mean the platform, not the experiment, changed);
- the suite would cost more than about 200 Cloud Run job executions, or a single cell runs longer than 2 hours;
- a change is needed outside the allowed list.

## Acceptance (each line true or false)
- [ ] `run_grid.py --grid grids/standing_suite.yaml --remote` completes, and every cell has a row in `experiments.grid_results` with a `config_id` and `run_id`.
- [ ] A cell picked at random has a `platform.experiment_configs` row with the same shape as `e9568d66-8b67-47bd-96f7-4446fa34066e`.
- [ ] Re-running the same grid without `--force` runs zero cells.
- [ ] Every cell's summary has log loss, Brier, ATS and game count, overall and for week 1, weeks 2–4, weeks 5+, plus the bootstrap interval against the baseline.
- [ ] Both reference rows (constant 0.5, market-implied) appear in every grid table.
- [ ] `reports/standing_suite_<date>.md` has a table for each of the 7 grids.
- [ ] Each run's `env_platform` is Linux and each carries its `git_sha`.
- [ ] Counterfactual swap results are stored per game for the current week.
- [ ] Tests: counts before and after, all green. Tests cover grid parsing, config-hash idempotency, the metric split by week bucket, and the bootstrap seeding.

## Returns-with
`00-PROJECT-LEAD/HANDOFF-2026-09-<dd>-batch-runner.md`: goal achieved yes/no (first line), commit SHAs, grid id, the number of cells and their run IDs, the report path, the headline table for each grid, test counts before and after, and anything left open.
