# Phase 4 Status — Validation & Improvements

**Owner:** PROJECT-LEAD  
**Phase start:** 2026-05-16  
**Updated:** 2026-05-17 (Track 5 complete — game_universe filter implemented; sit_div and sit_late experiments run. Both NO-GO. See Track 5 table for full results.)  
**Status:** 🔴 Track 5 complete — both situational experiments fail gate. Awaiting PROJECT-LEAD Go/No-Go decision.

**Incident closed:** `INC-001-label-inversion.md` — DATA-PIPELINE fixed `derive_home_covered`, rebuilt all seasons, and MODELING re-ran all Tier 1 experiments on clean labels. INC-001 fully resolved 2026-05-17.

This file is updated by agents as they complete deliverables. PROJECT-LEAD reads it to track parallel work and decide when to engage the next agent. For the full rationale behind Phase 4 scope, see `ROADMAP.md` §Phase 4. For the detailed model validation investigation plan, see `RUSH_VALIDATION_PLAN.md`.

---

## Phase 4 Tracks

| Track | Description | Lead Agent | Status |
|-------|-------------|------------|--------|
| 1 | Model validation — does the rushing feature result hold up? | MODELING | ❌ Tier 1 NO-GO — rush features show no edge on correct labels |
| 2 | Experiment runner improvements — reproducibility + trust tooling | MODELING | ✅ Complete |
| 3 | App usability — surface what's computed, fix what's incomplete | BACKEND-API + FRONTEND + DEVOPS | ✅ Complete |
| 4 | Data fix — rebuild `curated.games` with correct `home_covered` | DATA-PIPELINE | ✅ Complete |
| 5 | Situational filtering — does the v2 feature set find edge in game subsets? | MODELING | 🟡 Active — runner change + sit_div + sit_late experiments |

---

## Track 5 — Situational Filtering (MODELING)

**Spec:** `SITUATIONAL_EXPERIMENT_PLAN.md`  
**Hypothesis:** The v2 feature set may carry signal in specific game subsets (divisional games, late-season) that gets averaged to noise across the full 1,582-game universe.

| # | Deliverable | Status | Notes |
|---|-------------|--------|-------|
| 5.1 | Add `game_universe` filter to `run_experiment.py` | ✅ Complete | Filter added after `build_feature_matrix`, before `run_walk_forward`. Supports `eq/gte/lte/ne` operators. Raises `ValueError` if <100 games remain. Appends `[UNIVERSE: ...]` tag to BQ notes string. File: `02-MODELING/backtests/run_experiment.py`. |
| 5.2 | sit_div — divisional games experiment | ❌ NO-GO | run_id: `20260517_100959_0158a4`. **47.951%** (316-343-13, 659 test games across 7 folds). Folds above 54%: **1/7** (2025 at 55.2%). No consistent signal. Full results below. |
| 5.3 | sit_late — late-season experiment (Weeks 15–18) | ❌ NO-GO | run_id: `20260517_101004_010cd1`. **48.130%** (193-208-14, 401 test games across 7 folds). Folds above 54%: **2/7** (2022 at 55.0%, 2024 at 62.5%). 2025 fold collapses to 31.3%. No consistent signal. Full results below. |
| **Go/No-Go** | PROJECT-LEAD decision on Track 5 results | 🔓 Ready for decision | Neither experiment clears 54% overall or shows ≥4/6 folds consistent. Gate not met. Awaiting PROJECT-LEAD Go/No-Go. |

### sit_div Detailed Results (run_id: `20260517_100959_0158a4`)

**Universe:** `div_game == 1` (divisional games only)  
**Overall ATS:** 316-343-13 | **Hit rate:** 47.951% | **Test games:** 659 | **Gate:** NOT MET  
**Always-home baseline:** 47.496%

| Test Season | W | L | P | Hit Rate | N Games |
|-------------|---|---|---|----------|---------|
| 2019 | 41 | 51 | 4 | 44.565% | 92 |
| 2020 | 39 | 57 | 0 | 40.625% | 96 |
| 2021 | 49 | 44 | 3 | 52.688% | 93 |
| 2022 | 40 | 55 | 1 | 42.105% | 95 |
| 2023 | 47 | 46 | 3 | 50.538% | 93 |
| 2024 | 47 | 47 | 2 | 50.000% | 94 |
| 2025 | 53 | 43 | 0 | **55.208%** | 96 |

**Folds above 54%:** 1/7 (only 2025). Pattern is inconsistent — 2020 fold is the worst in the full experiment set at 40.6%.

**Top 5 features (mean importance):**
1. `home_rolling_3wk_epa_trend` — 0.0226
2. `home_def_rush_yards_allowed_per_att` — 0.0225
3. `away_def_qb_hit_rate` — 0.0224
4. `away_ol_qb_hit_rate` — 0.0218
5. `home_qb_cpoe` — 0.0218

Note: feature importances are very flat (all top features ~0.022), consistent with no single feature driving the model.

---

### sit_late Detailed Results (run_id: `20260517_101004_010cd1`)

**Universe:** `week >= 15` (late-season games, Weeks 15–18)  
**Overall ATS:** 193-208-14 | **Hit rate:** 48.130% | **Test games:** 401 | **Gate:** NOT MET  
**Always-home baseline:** 53.367% (baseline outperforms model in this universe)

| Test Season | W | L | P | Hit Rate | N Games |
|-------------|---|---|---|----------|---------|
| 2019 | 21 | 22 | 5 | 48.837% | 43 |
| 2020 | 21 | 27 | 0 | 43.750% | 48 |
| 2021 | 31 | 31 | 2 | 50.000% | 62 |
| 2022 | 33 | 27 | 3 | **55.000%** | 60 |
| 2023 | 27 | 33 | 4 | 45.000% | 60 |
| 2024 | 40 | 24 | 0 | **62.500%** | 64 |
| 2025 | 20 | 44 | 0 | 31.250% | 64 |

**Folds above 54%:** 2/7 (2022 at 55.0%, 2024 at 62.5%). 2025 fold is 31.3% — the worst fold across both experiments. 2024 outlier alone is pulling up the average. High variance, no stable pattern.

**Top 5 features (mean importance):**
1. `away_qb_cpoe` — 0.0278
2. `home_def_pass_epa_allowed_per_att` — 0.0267
3. `home_def_sack_rate` — 0.0258
4. `home_def_epa_per_play` — 0.0245
5. `away_def_explosive_pass_allowed_rate` — 0.0244

---

### Track 5 Summary

Neither situational filter reveals consistent edge. Key observations:
- **sit_div:** 47.95% overall. Model performs similarly to the full-universe baseline (50.19%). Divisional familiarity hypothesis not supported.
- **sit_late:** 48.13% overall with the always-home baseline *outperforming the model* at 53.4%. The 2024 fold (62.5%) is a single-season outlier; the 2025 collapse to 31.3% in the same universe strongly suggests the 2024 result was noise. Model is not learning a stable late-season pattern.
- The v2 feature set does not appear to carry exploitable signal in any of the three universes tested (full, div, late-season).

Local report files: `02-MODELING/backtests/reports/20260517_100959_0158a4_sit_div_*.csv` and `20260517_101004_010cd1_sit_late_*.csv`

---

## Track 2 — Experiment Runner Improvements (MODELING)

> **Brief for MODELING:** implement these four changes before starting the Track 1 investigation. Each item has an exact file and implementation spec in `RUSH_VALIDATION_PLAN.md §Part B`.

| # | Deliverable | Status | Files | Notes |
|---|-------------|--------|-------|-------|
| 2.1 | Configurable `random_seed` via methodology config | ✅ Complete | `models/ol_xgb.py`, `models/xgb_v2.py`, `backtests/walk_forward.py`, `backtests/run_experiment.py` | `ol_xgb.py` and `xgb_v2.py` already had `random_seed` param. Added `random_seed: int = 42` to `run_walk_forward()` and wired to `_model_class(random_seed=random_seed)`. `run_experiment.py` reads `methodology.get("random_seed", 42)` and passes to `run_walk_forward`. |
| 2.2 | `shuffle_labels` mode for leakage detection | ✅ Complete | `backtests/run_experiment.py` | `shuffle_labels` read from methodology; permutes `home_covered` within each season using `np.random.default_rng(random_seed)` before `build_feature_matrix`; forces `gate_passed=False`; appends `[SHUFFLE_LABELS=True]` to BQ notes. Tested: A3 run produced 51.1% as expected. |
| 2.3 | `analyze_experiment.py` — post-hoc analysis script | ✅ Complete | New: `backtests/analyze_experiment.py` | CLI: `--run_id <id> [--project ...] [--analyses spread,calibration,permutation]`. Spread-slice: 4 buckets by \|spread\|. Calibration: 10 equal-width bins. Permutation importance: rebuilds feature matrix + reruns fold inference with each feature permuted in test set. All outputs to `backtests/reports/`. |
| 2.4 | `compare_experiments.py` — side-by-side comparison script | ✅ Complete | New: `backtests/compare_experiments.py` | CLI: `--run_ids <id1> <id2> ...`. Queries `experiments.backtest_runs` (aggregate) + `experiments.backtest_predictions` (per-season). Prints Markdown table + writes `backtests/reports/{timestamp}_comparison.md`. Top 3 features per experiment included. |

---

## Track 1 — Model Validation (MODELING)

> **Brief for MODELING:** run in order. Do not start Tier 2 without explicit PROJECT-LEAD Go/No-Go. Full investigation spec in `RUSH_VALIDATION_PLAN.md §Part A`.

### Tier 1 — "Is the harness trustworthy?" (gates Tier 2)

| # | Deliverable | Status | Notes |
|---|-------------|--------|-------|
| 1.1 | Per-fold hit rate breakdown for test3 | ✅ Complete — **CORRECTED** | run_id: `20260517_020637_245bc9`. Post-fix results: 2020=46.5%, 2021=55.2%, 2022=48.3%, 2023=51.6%, 2024=47.0%, 2025=44.3%. Overall 48.8% (772-810-33, 1,582 games). Only 1/6 folds above 54%. Decision: FAIL — signal not distributed. Pre-fix (invalid) results: 2020=58.6%, 2021=62.3%, 2022=59.2%, 2023=53.0%, 2024=61.4%, 2025=55.6% — these were entirely label-inversion artifacts. |
| 1.2 | 23-feature v2 reproduction through config-driven runner | ✅ Complete — **PASS** | run_id: `20260517_020202_0504ff`. Post-fix result: 50.190% (794-788-33, 1,582 games). Target was ≈49.65% (±1 pp). Delta = +0.54 pp. Runner is faithful. (Note: A2 uses 23 base features, matching the actual v2 feature catalog, not 52 as originally described in the spec; the 52-feature count includes home_ and away_ prefixes.) Pre-fix (invalid) result was 68.74% — label-inversion artifact. |
| 1.3 | Shuffled-label test on test3 config | ✅ Complete — **PASS** | run_id: `20260517_020425_38cf03`. Post-fix result: 51.075% (808-774-33, 1,582 games). Well below 52% threshold. No leakage. gate_passed forced False; notes tagged [SHUFFLE_LABELS=True] in BQ. Confirms feature pipeline architecture is clean. |
| **Go/No-Go** | PROJECT-LEAD decision on Tier 1 results | ❌ **NO-GO — Signal absent on correct data** | A2 and A3 pass (infrastructure clean). A1 fails: only 1/6 folds above 54% on correct labels, overall 48.8%. The 58.3% figure from test1/test2/test3 was entirely driven by label inversion — the model was predicting inverted outcomes and being rewarded for it. Rush features show no detectable edge on real data. Tier 2 criteria not met. Full decision rationale in `RUSH_VALIDATION_PLAN.md §Tier 1 Results`. |

### Tier 2 — "Is the signal stable and broad?" (gates Tier 3)

*Locked until Tier 1 Go/No-Go is confirmed.*

| # | Deliverable | Status | Notes |
|---|-------------|--------|-------|
| 1.4 | Seed stability — 5 additional seeds (1, 7, 99, 314, 2024) | 🔒 Locked | Requires 2.1 (seed config). Max−Min across seeds should be ≤2 pp. |
| 1.5 | 2025 holdout — train 2021–2024, test 2025 cold | 🔒 Locked | Single-fold, genuinely out-of-sample season. Target: ≥56%. |
| 1.6 | Feature ablation — rush-only / v2-only / union | 🔒 Locked | 3 configs run and compared. Diagnoses whether lift is from rush features or from feature-count reduction. |
| 1.7 | Per-spread-size hit rate slice | 🔒 Locked | Requires 2.3 (analyze_experiment.py). Edge in large spreads only = known market quirk, not broad signal. |
| **Go/No-Go** | PROJECT-LEAD decision on Tier 2 results | 🔒 Locked | Decision recorded in `RUSH_VALIDATION_PLAN.md`. |

### Tier 3 — Pre-production due diligence

*Locked until Tier 2 Go/No-Go is confirmed.*

| # | Deliverable | Status | Notes |
|---|-------------|--------|-------|
| 1.8 | Calibration plot (P(home covers) bin vs actual cover rate) | 🔒 Locked | Requires 2.3. Real-edge models track the diagonal. |
| 1.9 | Permutation feature importance | 🔒 Locked | Requires 2.3. Identifies if one feature is doing all the work. |
| 1.10 | Formal gate review | 🔒 Locked | PROJECT-LEAD writes gate review doc if Tier 3 passes. `gate_passed` set on the experiment. Honest-eval banner retired for this experiment. |

---

## Track 3 — App Usability Improvements

Tracks 2 and 3 are parallel — Track 3 does not depend on the model validation results.

### BACKEND-API

| # | Deliverable | Status | Notes |
|---|-------------|--------|-------|
| 3.1 | Per-fold data in `GET /api/v1/experiments/:id` response | ✅ Complete | Added `per_fold: [{season, wins, losses, pushes, hit_rate, n_games}]` to `ExperimentDetailResponse`. Sourced from `experiments.backtest_predictions` grouped by season for `latest_run_id`. Returns `[]` if no run or no predictions. Schema: `FoldResult` in `app/schemas/experiments.py`. Query: `get_per_fold_results()` + `get_latest_run_id()` in `app/queries/experiments.py`. Tests in `tests/test_experiments.py`. FRONTEND per-fold chart is unblocked. |
| 3.2 | `GET /api/v1/experiments/:id/feature-importance` endpoint | ✅ Complete | New endpoint. Reads `feature_importances` JSON column from `experiments.backtest_runs` for `latest_run_id`. Returns `[{feature, importance}]` sorted descending. Returns `{run_id: null, features: []}` if no run. Schema: `FeatureImportanceResponse` + `FeatureImportanceItem` in `app/schemas/experiments.py`. Query: `get_feature_importances()` in `app/queries/experiments.py`. Tests in `tests/test_experiments.py`. FRONTEND feature importance panel is unblocked. |
| 3.3 | `GET /api/v1/teams/{team}/ol-rating` endpoint | ✅ Complete | New endpoint (deferred from Phase 3). Computes cumulative season-to-date `ol_rush_epa_per_att` and `ol_pass_epa_per_att` directly from `curated.plays` via SQL window functions — no MODELING code imported. Optional `season` query param. New files: `app/routers/teams.py`, `app/queries/teams.py`, `app/schemas/teams.py`. Wired into `app/main.py`. Tests in `tests/test_teams.py`. `docs/API_CONTRACTS.md` updated. FRONTEND `/teams/:team` page is unblocked. |

### FRONTEND

| # | Deliverable | Status | Notes |
|---|-------------|--------|-------|
| 3.3 | Per-fold hit rate chart on experiment results page | ✅ Complete | Consumes `per_fold` array from `GET /api/v1/experiments/:id` (BACKEND-API 3.1). **Component built; pending live endpoint** — shows empty-state message when `per_fold` is absent/empty. Bar chart with W-L-P tooltip, color-coded bars, reference lines at 52.38% (break-even at -110) and 54% (gate threshold). Wiring is a one-line swap once BACKEND-API 3.1 ships. |
| 3.4 | Feature importance panel on experiment results page | ✅ Complete | Fetches `GET /api/v1/experiments/:id/feature-importance` (BACKEND-API 3.2). **Component built; pending live endpoint** — shows empty-state message when endpoint not yet deployed. Horizontal bar chart of top 15 features, cleaned display labels (strips home_/away_ prefix), full raw name in tooltip. |
| 3.5 | `/teams/:team` OL rating time series page | ✅ Complete | New route `/teams/:team`. Fetches `GET /api/v1/teams/{team}/ol-rating`. **Built; pending live endpoint** — `useTeamOLRating` query wired to correct URL path, shows error state if endpoint not deployed. Season selector (button tabs), defaults to most recent season. Line chart for `ol_rush_epa_per_att` and `ol_pass_epa_per_att` with zero reference line. `/games/:gameId` matchup header and score card team names are now clickable links to `/teams/:team`. All 32 NFL team abbreviations hardcoded in `TeamPage.tsx`. |

### DEVOPS

| # | Deliverable | Status | Notes |
|---|-------------|--------|-------|
| 3.6 | Dataset upload background task → Cloud Run Job | ✅ Complete | Cloud Run Job `nfl-dataset-processor` added. Script: `03-BACKEND-API/scripts/process_dataset_upload.py`. Job uses `nfl-backend-api:latest` image (same as API — no separate build needed). Env vars: `DATASET_ID` (UUID), `FILE_EXT` (csv/xlsx/xls/json), `BIGQUERY_PROJECT`. IAM: new SA `nfl-dataset-processor-sa` with GCS objectViewer on uploads bucket, BQ dataEditor on platform + user_datasets, BQ jobUser on project. API SA granted `roles/run.invoker` on the job. Router updated to call `trigger_dataset_processor()` instead of BackgroundTasks. Dockerfile updated to copy `scripts/` dir. To test manually: `gcloud run jobs execute nfl-dataset-processor --region us-central1 --update-env-vars DATASET_ID=<uuid>,FILE_EXT=csv` |

---

## Track 4 — Data Fix: curated.games rebuild (DATA-PIPELINE)

**Incident:** INC-001. Full record: `INC-001-label-inversion.md`.

| # | Deliverable | Status | Notes |
|---|-------------|--------|-------|
| 4.1 | Fix `derive_home_covered` in `build_curated_games.py` | ✅ Complete | Removed negation: `required_margin = home_spread_close`. Docstring updated. nflverse sign convention documented inline. |
| 4.2 | Rebuild `curated.games` for all seasons 2015–2025 | ✅ Complete | All 11 seasons rebuilt successfully. 2015–2020: 256 rows each; 2021–2025: 271–272 rows each. Run at 2026-05-17 13:31–13:37. |
| 4.3 | Spread-bin diagnostic to confirm fix | ✅ Complete — CLEAN | **Results:** home_dog_10+=50.8% (135/266), home_dog_3-10=47.5% (532/1120), home_fav_10+=54.4% (43/79), home_fav_3-10=50.7% (349/689), pick_em=47.6% (318/668). All buckets within 45–55%. Pre-fix values were home_dog_10+=86.8%, home_fav_10+=6.3% — confirmed inversion is fully resolved. |
| 4.4 | Add cover-rate sanity check to `validate_and_report.py` | ✅ Complete | New section 3b added. Checks all 5 spread buckets (must be 45–55%) and overall cover rate (must be 46–54%). Fails loudly with error message referencing INC-001 and PIPELINE_REMEDIATION_002.md. |
| 4.5 | Annotate invalidated BQ rows and write `PIPELINE_REMEDIATION_002.md` | ✅ Complete | `PIPELINE_REMEDIATION_002.md` written to `01-DATA-PIPELINE/`. BQ DML run: 10 rows in `experiments.backtest_runs` annotated with `[INC-001: labels inverted pre-2026-05-17 rebuild]` (all `experiment_id IS NOT NULL AND run_at < '2026-05-17 13:31:00'`). Phase 1 standalone runs not touched. |

**Unblocks:** Track 1 (MODELING) — A2 re-run must confirm ≈49.65% before Tier 1 Go/No-Go can proceed.

---

## Incidents

### INC-001 — Label inversion in `curated.games.home_covered` (2026-05-17)

**Full record:** `INC-001-label-inversion.md`  
**Severity:** Critical  
**Root cause:** `derive_home_covered` uses `required_margin = -home_spread_close` (inverted sign). Must be `required_margin = home_spread_close`.  
**Affected:** All config-runner experiments. May 3 standalone runs remain valid.  
**Status:** ✅ FULLY RESOLVED — MODELING rerun complete. All three Tier 1 experiments re-run on correct labels. Results recorded in `RUSH_VALIDATION_PLAN.md §Tier 1 Results` and Track 1 items 1.1–1.3 above.
