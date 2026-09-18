# PROMPT-STAGE1-FINISH-EXPLANATIONS — finish per-game explanations: exact week 1 if recoverable, fix wrong-side panels, backtests store explanations

Start in: C:\Users\OEM\OneDrive\Desktop\nfl-prediction-app
Written: 2026-09-17 by PROJECT-LEAD. Stage 1b of 4 (finishes Stage 1 of `PROMPT-PICK-EXPLANATIONS-AND-EDGE-LAB.md`). Next stage: PROMPT-WEEK1-ANALYSIS (not written yet).

## Matt's request
> Every pick, live or backtest, stores what the model weighted and by how much. Explain what the model weighted on each of the 16 week-1 picks.

This stage covers: explanations for backtests, exact week-1 explanations (if the old data can be recovered), and fixes to what shipped on 2026-09-17.

Matt's decisions (2026-09-17, don't re-ask):
- On a game where the explanation's model leans the other way from the live pick: the heading shows the **live pick**, plus a clear warning. Never show the other side as "the pick".
- Try to recover the pre-2026-09-15 curated data (BigQuery time travel) to get exact week-1 explanations.
- Move the `nfl-experiment-runner` job to the new modeling image.

## Task
When this is done:
- The live app never labels a pick the app didn't make.
- Week 1 has exact explanations if the old data could be recovered, and a recorded answer on whether the 09-15 rebuild changed 2015–2025 data.
- QB features show league percentiles.
- Every backtest run through `run_experiment.py` stores explanations for its test games.
- Every run records the environment that produced it.
- Both Cloud Run jobs run one image, built from a clean commit.

## Read first
- `00-PROJECT-LEAD/HANDOFF-2026-09-17-pick-explanations.md` (what shipped, and its open items)
- `00-PROJECT-LEAD/STATE.md`: the Decisions section, and the Stage 1 status under "Matt's current priority"
- `00-PROJECT-LEAD/context/talking-to-matt.md`
- `02-MODELING/backtests/explanations.py` (`_percentile_table`, `build_explanations`), `explanations_bq.py`, `explain_picks.py`
- `02-MODELING/backtests/walk_forward.py`, `run_experiment.py`, `bq_writer.py`, `create_blend_backtest_configs.py`
- `03-BACKEND-API/app/queries/explanations.py`, `app/routers/predictions.py`, `app/schemas/explanations.py`
- `04-FRONTEND/src/components/WhyThisPick.tsx`, `GameCardWithExplanation.tsx`

## Steps

### 1. Recover the pre-rebuild data (time-sensitive: do this first)
BigQuery time travel covers at most 7 days. `curated.games` was recreated at 2026-09-15 11:08:52 UTC and `curated.plays` at 11:09:49 UTC, so the old versions are gone by about **2026-09-22 11:08 UTC** at the latest.
1. Read `max_time_travel_hours` for the `curated` dataset (`INFORMATION_SCHEMA.SCHEMATA_OPTIONS`). Find when the stored week-1 picks were written: the latest `created_at` / run row for week 1 under the production experiment.
2. Copy both tables as they stood just before the rebuild (e.g. `curated.games@<epoch ms of 2026-09-15 11:08:00 UTC>`) into a new dataset `scratch_timetravel`. Set a 30-day default table expiration on it. Never write to `curated`.
3. Compare old against current for 2015–2025: row counts per season, plus a per-season checksum of the columns `generate_predictions` uses. Report which seasons and columns differ.
4. Add a `--curated-dataset` option to `explain_picks.py` (default `curated`). Run `--season 2026 --week 1` against `scratch_timetravel`, inside the production Linux image (one-off Cloud Build step, as on 09-17).
5. If it passes the guard (≤1e-6): **append** the exact week-1 explanations under a new `run_id`, with `is_approximate = False`. **Do not delete the approximate rows.** Explanations for kicked-off games are never rewritten, only added to.
6. If recovery is impossible or the guard still fails: record why, keep week 1 approximate, and carry on with step 2.

### 2. Live-pick side is authoritative
- API: join the live pick from `experiments.backtest_predictions`. Return `live_predicted_side` and `side_matches_live_pick`, and compute pick-direction values relative to the **live** pick. When a game has several explanation runs, serve exact over approximate, then the newest.
- UI: the heading always names the live pick. When `side_matches_live_pick` is false, show a warning: "The approximate model leans toward <other team>. These drivers don't explain this pick." Show the stat name next to each family label. Vitest tests cover both cases.

### 3. QB percentiles
Find why `league_pctile` is null for `*_qb_cpoe_blend` and `*_qb_epa_under_pressure_blend` (e.g. `2026_02_CAR_ATL`). Fix it in `explanations.py`. Existing rows can only be fixed by appending a new run (step 1's rule): do that for week 2 only if week 2's reproduction still passes the guard in the Linux image.

### 4. Backtests store explanations (Stage 1.2 item 5)
`walk_forward.py` / `run_experiment.py`: every test game of every fold stores explanations keyed to that run's `run_id`. Use a config flag, default on. Skip interaction values for backtests.

### 5. Environment fingerprint on every run
Add nullable columns to `experiments.backtest_runs` (new columns only, and update `preflight()`):
- `env_platform`
- `env_python`
- `env_packages` (JSON: pandas / numpy / scikit-learn / xgboost)
- `git_sha` (baked into the image at build time via a Dockerfile `ARG`)
- `cloud_run_execution` (from `CLOUD_RUN_EXECUTION`, when set)

Write them from `predict_upcoming.py`, `run_production_refresh.py`, `run_experiment.py` and `explain_picks.py`.

### 6. Build, deploy, repoint
1. Commit and push the `02-MODELING`, `03-BACKEND-API` and `04-FRONTEND` changes. Leave `00-PROJECT-LEAD` alone.
2. Build the image from a **clean export of the pushed commit** (`git worktree` or `git archive` outside the repo), not the working tree.
3. Point **both** `nfl-production-refresh` and `nfl-experiment-runner` at the new digest. Show `gcloud run jobs describe` before and after for each. Don't execute either job.
4. **Do not repoint anything between Tue 22 Sep 11:00 and 15:00 UTC** (full rebuild and weekly refresh). If you would land in that window, stop and tell Matt.
5. Proof backtest: create a platform config copying `e9568d66-8b67-47bd-96f7-4446fa34066e`, restricted to test season 2025, the way `create_blend_backtest_configs.py` does. Run it with `nfl-experiment-runner` (this is a backtest, not the production refresh).

### 7. Paperwork
- ADR (next number in `docs/DECISIONS.md`): TreeSHAP method, table design, approximate/exact rows, live-pick side rule, Linux-only reproduction.
- `00-PROJECT-LEAD/ROADMAP.md`: add a "Current" section at the top.

## Scope
Allowed to change: `02-MODELING/**`, `03-BACKEND-API/app/**` and tests, `04-FRONTEND/src/**`, `docs/DECISIONS.md`, `00-PROJECT-LEAD/ROADMAP.md`, `QUESTIONS.md`, the handoff file. BigQuery: new dataset `scratch_timetravel`, appends to `experiments.prediction_explanations`, new nullable columns on `experiments.backtest_runs`, the proof backtest's rows.

Must not change: stored picks, the `curated.*` / `raw_*` tables, schedulers, IAM, existing explanation rows (append only), any other `00-PROJECT-LEAD` file.

## Kill-switch
Stop, write to `00-PROJECT-LEAD/QUESTIONS.md`, and tell Matt if:
- a step would delete or modify existing rows in `prediction_explanations` or `backtest_predictions`;
- the time-travel copy needs an IAM change or a support request;
- the old-vs-current comparison shows 2015–2025 data changed. Report it; don't fix the pipeline in this stage;
- a job repoint would fall in the Tue 11:00–15:00 UTC window, or anything would execute `nfl-production-refresh`;
- week-2 explanations no longer reproduce in the new image.

## Acceptance (each line true or false)
- [ ] `QUESTIONS.md` or the handoff states whether the pre-rebuild tables were recovered, and gives old-vs-current row counts per season for 2015–2025.
- [ ] If recovered and the guard passed: the API returns `is_approximate: false` for all 16 week-1 games. Otherwise the reason is recorded.
- [ ] For every week-1 and week-2 game, the API's `live_predicted_side` equals `predicted_side` from `/api/v1/predictions?season=2026&week=N`.
- [ ] `2026_01_ATL_PIT` detail page: the heading names PIT. If `side_matches_live_pick` is false, the warning text is present (checked in the served bundle and by a Vitest test).
- [ ] Top-5 drivers have no null `league_pctile` for team-side features on `2026_02_CAR_ATL`, or a recorded reason why week 2 couldn't be re-appended.
- [ ] The proof backtest's `run_id` has explanation rows for every test game (count = games × features). For a sample of 20 games, contributions + bias equal the stored log-odds within 1e-4.
- [ ] The proof backtest's `backtest_runs` row has the new `env_*` and `git_sha` columns filled, and `env_platform` is Linux.
- [ ] Both jobs show the same new digest in `describe`, built from the pushed commit.
- [ ] Tests: modeling, backend and frontend counts before and after all given, all green (apart from the 29 known backend failures).
- [ ] `/health` commit and frontend bundle name match the pushed commit's deploy.
- [ ] ADR added, and `ROADMAP.md` has a "Current" section.

## Returns-with
Write `00-PROJECT-LEAD/HANDOFF-2026-09-<dd>-stage1-finish.md`: goal achieved yes/no (first line), commit SHAs, `/health` commit, bundle name, image digest (both jobs), proof-backtest config and run IDs, time-travel result and data-comparison table, test counts before and after, anything left open.
