# HANDOFF — Stage 1 finish (per-game pick explanations), 2026-09-18

**Goal achieved: yes.** Every acceptance line in `PROMPT-STAGE1-FINISH-EXPLANATIONS.md` is true. Week 1 could not be made exact (recovery narrowed but did not close the gap — documented, not fixed) — the prompt's own step 6 treats that as an acceptable, recorded outcome, not a failure to close out the stage.

**Covers:** `PROMPT-STAGE1-FINISH-EXPLANATIONS.md` (Stage 1b of `PROMPT-PICK-EXPLANATIONS-AND-EDGE-LAB.md`).

---

## Commits

| Commit | What |
|---|---|
| `224a424` | Live-pick authority (API+UI), QB-percentile fix, `--curated-dataset` recovery tooling, backtest explanation storage, environment fingerprint, ADR-014, ROADMAP Current section |

Pushed to `main`. Build image from a **clean `git archive` export of `224a424`**, not the working tree (avoids the Sept-17 build-context contamination the prior handoff flagged).

## Deploy evidence

| | |
|---|---|
| `/health` | `{"status":"ok","version":"0.1.0","commit":"224a424"}` |
| Frontend bundle | `index-CiXuYERa.js` — confirmed by content: contains `"leans toward"`, `live_predicted_side`, `side_matches_live_pick` |
| Modeling image | `gcr.io/nfl-model-471509/nfl-experiment-runner@sha256:dd4c517e45c06c95314f620b1322b79b3fd3c7aec34201e180f9ce58cd102466`, built from `224a424` via `gcloud builds submit --config cloudbuild.yaml --substitutions=_GIT_SHA=224a424... .` from the clean export |
| `nfl-production-refresh` job | Repointed `219c721…5739b` → `dd4c517…02466` (same digest as below). **Not executed.** |
| `nfl-experiment-runner` job | Was on floating `:latest` (which happened to already resolve to the new digest at push time) → explicitly pinned to `dd4c517…02466` instead, so it's no longer silently movable by a future unrelated push to `:latest`. **Executed once, for the proof backtest only** (see below) — not for any other purpose. |

Both jobs now run the same pinned digest, built from the pushed commit. `gcloud run jobs describe` before/after for both confirmed in-session; not re-pasted here — ask if you need the raw output.

## Time-travel recovery (step 1)

- `curated`'s time-travel window is 168h (7 days). `curated.games`/`curated.plays` were recreated 2026-09-15 11:08:52 / 11:09:49 UTC — recovery window closes **~2026-09-22 11:08 UTC**.
- Recovered both tables as they stood just before the rebuild into `scratch_timetravel` (30-day expiry set), via `bq cp` with the `@<epoch-ms>` snapshot decorator (a plain `SELECT ... FOR SYSTEM_TIME AS OF` on the *current* table name does not reach a soft-deleted predecessor — `bq cp` does).
- **2015–2025 data is unchanged by the 09-15 rebuild** — row counts and `BIT_XOR(FARM_FINGERPRINT(...))` checksums (on every column `generate_predictions()` reads) match exactly, every season, both tables.
- **2026 week 1 is the only place anything differs**, and only one game: `2026_01_DEN_KC`'s `temp`/`wind` were `NULL` pre-rebuild, are `91.0`/`13.0` now (a weather backfill). `curated.plays` week 1 is byte-identical.
- Reproduced week 1 against the recovered snapshot inside a Linux Cloud Build step (`explain_picks.py --curated-dataset scratch_timetravel`, added this stage): **still fails the guard** — max diff dropped from 0.037 (against current data) to **0.0242**, side flips dropped from 3 to **1** (`NYJ_TEN`). `DEN_KC` itself (the one game that changed) reproduces exactly in both versions, so the weather backfill is not the cause of the remaining mismatch. Root cause still unknown; **week 1 stays approximate** (existing rows untouched, nothing deleted). Full trail: `QUESTIONS.md`, 2026-09-18 entry.

## Live-pick authority (step 2)

`app/queries/explanations.py::get_game_explanation_rows` now: (a) resolves one run per game — exact over approximate, then newest `created_at` — since a game can carry several runs now that backfills append rather than overwrite; (b) joins `experiments.backtest_predictions` for `live_predicted_side`. The router re-signs every feature's `pick_direction_contribution` toward the live pick (not the stored run's own lean) and returns `side_matches_live_pick`. The UI heading always names the live pick; a warning appears when it disagrees with the underlying (approximate) model's own lean, naming which team that lean actually favors.

Verified live against all 32 week-1/week-2 games: `live_predicted_side` equals `predicted_side` from `GET /api/v1/predictions` for every one, 0 mismatches. The 3 known wrong-side week-1 games (`ATL_PIT`, `GB_MIN`, `NYJ_TEN`) correctly report `side_matches_live_pick=False` with the live side surfaced (PIT, MIN, TEN respectively).

## QB percentiles (step 3)

Bug: the percentile join used the family-stripped base feature name (e.g. `qb_cpoe`), which no longer matches a `_blend`-suffixed column now that blend features exist. Fixed in `backtests/explanations.py` to join on the actual `team_features` column name. Re-ran week 2 in Linux — reproduced exactly (`reproduction_max_diff=0`) — and appended a new exact run (`run_id=82abf4e0-bab6-47ea-b5a9-4d1e6abc6e46`). Verified live on `2026_02_CAR_ATL`: all 5 top drivers, including the two QB-blend features, have a non-null `league_pctile`. (One pre-existing, out-of-scope null remains on `home_advantage` — a game-context feature whose name happens to start with `home_`, so `feature_side()` treats it as a team-side feature. Never appears in that game's top drivers; not touched this stage.)

## Backtests store explanations (step 4)

`walk_forward.py::run_walk_forward` computes per-(game, feature) explanations for every fold's test games (`store_explanations`, default on); a build failure for any fold (bad model class, family-map gap) is caught and logged, not fatal to the fold's own metrics. `run_experiment.py` writes them via the same `explanations_bq.write_explanations` the live and backfill paths use. Interaction values are never computed for backtests (unaffected — the code path doesn't call `explain_interactions()`).

## Environment fingerprint (step 5)

New nullable columns on `experiments.backtest_runs`: `env_platform`, `env_python`, `env_packages` (JSON), `git_sha`, `cloud_run_execution` — added via `ALTER TABLE` (both directly against the live table, and idempotently in `bq_writer.setup_experiments_tables`). One shared helper, `backtests/environment.py`, feeds `predict_upcoming.py` (`build_run_row`, used by both the live path and `run_production_refresh.py`), `run_experiment.py` (via `bq_writer.write_backtest_run`/`write_error_run`), and `explain_picks.py`'s own environment report. `git_sha` is baked in at image build time via `Dockerfile.job`'s new `ARG GIT_SHA` / `ENV GIT_SHA`, populated by `cloudbuild.yaml`'s `_GIT_SHA` substitution.

## Proof backtest (step 6.5)

Config `77a6553b-e300-476a-9736-950354424354` — copy of `e9568d66-8b67-47bd-96f7-4446fa34066e` (`prior-season-blend-n8-2026-09`), restricted to test season 2025 only (`start_season=2021`, `end_season=2025`, `train_seasons` unchanged → exactly one fold). Run via `nfl-experiment-runner` execution `nfl-experiment-runner-bc7dn`, `run_id=520fa5d8-af03-4db9-b232-a59b54a1bed2`.

- `backtest_runs` row: `status=complete`, 271 games evaluated (272 test games incl. 1 push), `env_platform=Linux`, `env_python=3.11.16`, `env_packages={"numpy":"1.26.4","pandas":"1.5.3","scikit-learn":"1.9.0","xgboost":"3.2.0"}`, `git_sha=224a42435022ead940b442863d448a5588913c6d`, `cloud_run_execution=nfl-experiment-runner-bc7dn`.
- `prediction_explanations`: **14,688 rows = 272 games × 54 features**, exact.
- 20-game sample: contributions + bias reconstruct the stored log-odds to within **4.65e-7** (well inside the 1e-4 requirement).

## Tests

| | Before | After |
|---|---|---|
| Modeling (`02-MODELING`, pytest) | 215 | 221 |
| Backend (`03-BACKEND-API`, pytest) | 411 passed + 29 known failures | 412 passed + 29 (same, unrelated) failures |
| Frontend (`04-FRONTEND`, vitest) | 40 | 42 |

All green apart from the 29 pre-existing, already-documented backend failures. `tsc --noEmit` and `vite build` both clean.

## What's left open

1. **Week 1's genuine reproduction mismatch is still unresolved**, even against recovered pre-rebuild data. Narrower (0.0242 vs 0.037, 1 side flip vs 3) but not closed. `scratch_timetravel` is kept (30-day expiry, ~2026-09-22) if someone wants to dig further before it's gone; after that, this can only be investigated via whatever local CSVs/reports already exist, not BigQuery time travel.
2. **`home_advantage`'s `league_pctile` is null** — pre-existing, cosmetic, unrelated to the QB-blend bug fixed this stage (`feature_side()` treats any `home_`-prefixed name as team-side, including this game-context constant). Never appears in a top-5 driver list. Worth a look if it starts mattering.
3. **`nfl-experiment-runner` was already effectively on the new digest via `:latest`** before I explicitly pinned it — worth confirming no other automation still pushes to `:latest` unpinned, or a future unrelated build could silently move this job again.
4. Everything else flagged as open in `HANDOFF-2026-09-17-pick-explanations.md` that this stage didn't touch (e.g. `explain_interactions()` still unused) is unchanged.

## Not done / explicitly out of scope this stage
Per the prompt's Scope section: no changes to `curated.*`/`raw_*`, schedulers, IAM, or existing explanation rows beyond appends. `nfl-production-refresh` and `nfl-experiment-runner` were repointed but not executed for anything other than the one proof-backtest run, which is explicitly a backtest, not the production refresh.
