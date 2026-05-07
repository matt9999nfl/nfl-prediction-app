# ROADMAP — NFL Prediction App

**Owner:** PROJECT-LEAD
**Last updated:** 2026-05-06
**Status:** Phase 3 in progress — DEVOPS agent engaged 2026-05-06; deployment underway

---

## Phase Overview

| Phase | Name | Gate | Status |
|-------|------|------|--------|
| 1 | Foundation & Validation | Platform infrastructure built and validated | **Complete ✅** |
| 2 | Service Layer | Phase 1 complete | **Software complete ✅** |
| 3 | Productionize | Phase 2 shipped | **Ready to unlock** |

---

## Phase 1 — Foundation & Validation ✅ COMPLETE

> **This section is a historical record.** Phase 1 is complete as of 2026-05-03. The content below documents what was decided and built. It is not active guidance — do not use it to constrain Phase 2 work.

### What Was Built

- nflfastR play-by-play, schedules, and rosters loaded into BigQuery (`raw_nflfastr.*`, `curated.*`) for 2015–present
- Closing lines sourced from nflverse schedules `spread_line` field (0% null rate, confirmed as closing lines from Pro-Football-Reference via nflverse)
- PR-001 resolved: `home_covered` sign convention fixed (nflverse stores spread as positive = home favored)
- Walk-forward experiment framework built: 6-fold harness, leakage guards, BigQuery output to `experiments.*`
- Two baseline experiments run: ol_xgb_v1 (48.7% ATS) and ol_xgb_v2 (49.6% ATS, 52 features)
- OL mismatch subset defined and approved (see `experiments/OL_COMPOSITE_PROPOSAL.md`)

### Why Phase 2 Was Unlocked

The original 54% ATS gate was retired (ADR-006). The project goal is a self-service experimentation platform — Phase 1 completion means the infrastructure is working and producing real experiments, not that a specific model hit a threshold. Experiment-level gates live on the experiment, not the project phase.

### Original Phase 1 Design Decisions (for reference)

| # | Decision | Choice |
|---|----------|--------|
| 1 | Gate metric *(superseded by ADR-006)* | ATS hit rate vs. closing line, flat bet |
| 2 | Gate threshold *(superseded by ADR-006)* | ≥54% ATS on ≥250 games |
| 3 | Backtest window | 2015–present |
| 4 | Walk-forward structure | Rolling 4-year train, 1-year test |
| 5 | Backtest output | Edge metrics only (flat bet) |
| 6 | Evaluation scope | Full universe + OL mismatch subset (diagnostic) |
| 7 | ATS baseline | Closing line only |

---

## Phase 2 — Service Layer ✅ Software Complete

Phase 1 is complete. Phase 2 builds the full self-service experimentation platform on top of the validated foundation.

### What Phase 2 Delivers

**DATA-PIPELINE** ✅ Complete — 2026-05-04
- `platform.*` BigQuery tables and `user_datasets` dataset created per `docs/PIPELINE_SCHEMA_MIGRATION_PHASE2.md`
- `experiment_config_id` and `success_criteria` columns added to `experiments.backtest_runs`
- 58/58 validation checks passed; migration script idempotent at `scripts/migrate_phase2.py`

**BACKEND-API** ✅ Complete — 2026-05-04
- All 5 steps delivered per `docs/BACKEND_API_SPEC_PHASE2.md` and `docs/API_CONTRACTS.md`
  - Step 1 ✅ read endpoints (games, experiments, predictions, features)
  - Step 2 ✅ dataset upload flow (GCS + BigQuery async background task)
  - Step 3 ✅ experiment config + run trigger (stub runner, swappable when MODELING delivers)
  - Step 4 ✅ framework CRUD
  - Step 5 ✅ Claude API schema inference (`claude-haiku-4-5-20251001`, 503 fallback to form)
- 6 contract ambiguities resolved and logged in `docs/API_CONTRACTS.md` (2026-05-04)

**MODELING** ✅ Complete — 2026-05-06
- Config-driven runner `backtests/run_experiment.py` delivered. Reads `EXPERIMENT_CONFIG_ID` env var, fetches config from `platform.experiment_configs`, builds feature matrix dynamically (curated catalog + user dataset joins), runs walk-forward with fold structure derived from config, writes all Phase 2 fields to `experiments.backtest_runs`, updates `platform.experiment_configs` status/gate_passed in finally block.
- `folds_complete`, `folds_total`, `completed_at`, `error_message` added to `experiments.backtest_runs` via `_alter_runs_table_phase2()` DDL.
- `run_phase1_backtest.py` untouched — Phase 1 historical record preserved.
- MODEL_REGISTRY updated: `"xgboost"` → `OLXGBModelV2` (canonical FRONTEND name); legacy aliases `"ol_xgb_v1"` / `"ol_xgb_v2"` retained for Phase 1 backward compat; `"logistic_regression"` and `"random_forest"` registered as `NotImplementedError` stubs; unknown types raise `ValueError` at config-load time with valid key list.
- **Known pre-Phase-3 fix required:** runner assumes literal join key column names (`team`, `season`, `week`, `game_id`) for user dataset joins. Must be updated to read `join_key_columns` from `platform.datasets` before the first real user dataset is used in an experiment.

**FRONTEND** ✅ Complete — 2026-05-06
- All pages delivered. Routes: `/`, `/games/:gameId`, `/datasets`, `/datasets/:datasetId`, `/experiments/new` (6-step wizard), `/experiments/:id`, `/model`, `/frameworks`, `/frameworks/:id`, `/about`.
- Upload flow with AI inference (503 fallback to form), schema mapping, experiment builder, per-fold results chart, framework save/load, `/about` with honest hypothesis status all shipped.
- Honest evaluation banner on all pages until `gate_passed = true` on a real experiment.
- 3 gaps flagged and resolved: `fold` added to predictions contract (2026-05-06); production experiment concept and `/teams/:team` deferred to Phase 3.
- `fold` field added to `03-BACKEND-API/app/schemas/experiments.py` and `queries/experiments.py` during type generation — ruled as a one-time exception (changes correct and necessary; scope boundary reinforced in FRONTEND instructions).
- Run `npm run types:generate` from `04-FRONTEND/` once API is running locally to replace hand-authored `types.ts` with generated `openapi.gen.ts`.
- **Phase 3 — feature importance:** importance scores are not in BigQuery and no API endpoint exists. Requires MODELING to write scores to BQ + BACKEND-API to add an endpoint before FRONTEND can display them.

### Phase 2 Complete When
- API is live and serving data from `experiments.*` and `curated.*` ✅
- Dataset upload flow works end-to-end (upload → schema map → available in experiment builder) ✅
- MODELING's experiment runner accepts config JSON (not hardcoded feature lists) ✅
- At least one experiment has been configured and run through the dashboard UI ⏳ — UI is built and triggering works; full completion pending Phase 3 DEVOPS (Cloud Run Job wiring)

### Experiment Gates (ADR-006)
Each experiment defines its own success criteria. `experiments.backtest_runs.gate_passed` is set by the runner. The frontend uses this to distinguish production-ready experiments from exploratory runs. No project-level gate blocks Phase 2 or Phase 3.

---

### Phase 3 — In Progress 🚀 (started 2026-05-06)

**Status:** DEVOPS agent engaged. Spec at `docs/DEVOPS_SPEC_PHASE3.md`.

**Phase 3 agent engagement order:**
1. **DEVOPS** — first. All deployment blocked on infra. Spec delivered 2026-05-06. ← *active*
2. **TESTING-QA** — unblocks when DEVOPS delivers Step 1 (Cloud Run URL live)
3. **BACKEND-API** — unblocks when DEVOPS delivers Step 1 (add `GET /api/v1/predictions` endpoint)
4. **MODELING** — unblocks when DEVOPS delivers Step 3 (write `run_production_refresh.py` + join-key fix)
5. **FRONTEND** — unblocks when BACKEND-API delivers `/api/v1/predictions` endpoint

**ADR-010 added:** Terraform selected for IaC (see `docs/DECISIONS.md`).

**Phase 3 complete when:**
- All agents deliver their Phase 3 items
- At least one experiment runs end-to-end through the deployed platform
- Production predictions visible in the dashboard for a gate-passed experiment

---

### Phase 3 (locked until Phase 2 ships) — HISTORICAL NOTES

- **DEVOPS** deploys Cloud Run service and Cloud Run Jobs, sets Cloud Scheduler jobs (weekly ingest + prediction refresh), instruments monitoring. Swap BACKEND-API's `BackgroundTasks` for real Cloud Run Job triggers (see ADR-008).
- **TESTING-QA** hardens integration tests across pipeline → model → API seam
- Supplemental data sources (FTN, NGS, SIS) evaluated and integrated by DATA-PIPELINE based on experiment contribution
- Platform iteration: model comparison views, bankroll simulation, confidence-filtered prediction surfacing
- **BACKEND-API:** Add `GET /api/v1/predictions?season=N&week=N` convenience endpoint that reads from the most recent `gate_passed = true` experiment. This unblocks the dashboard game-card prediction overlays (flagged by FRONTEND, 2026-05-06). No `is_production` flag needed — `gate_passed` is the signal.
- **FRONTEND:** Add `/teams/:team` route (OL rating time series) once DEVOPS has the weekly data pipeline running and `GET /api/v1/teams/{team}/ol-rating` is live.

---

## Key Decisions (full ADRs in `docs/DECISIONS.md`)

| ADR | Decision | Status |
|-----|----------|--------|
| 001 | Use existing GCP project `nfl-model-471509` | Accepted |
| 002 | nflfastR / nflverse as primary data spine | Accepted |
| 003 | Cloud Run for the API service | Accepted |
| 004 | BigQuery as the only data store | Accepted |
| 005 | Project goal is a comprehensive NFL prediction platform | Accepted |
| 006 | Experiment gates are per-experiment, not project-level | Accepted |
| 007 | Self-service platform with form-based upload + future Claude API schema inference | Accepted |
| 008 | FastAPI BackgroundTasks for Phase 2 async processing; swap to Cloud Run Jobs in Phase 3 | Accepted |
| 009 | model.type uses abstract names in API contract; runner resolves to concrete implementations | Accepted |
