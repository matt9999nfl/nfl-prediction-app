# ROADMAP — NFL Prediction App

**Owner:** PROJECT-LEAD  
**Last updated:** 2026-05-23  
**Status:** Phase 4 complete. Phase 5 Polish Sprint active.

---

## Phase Overview

| Phase | Name | Gate | Status |
|-------|------|------|--------|
| 1 | Foundation & Validation | Infrastructure built, pipeline validated | ✅ Complete |
| 2 | Service Layer | Full self-service platform built | ✅ Complete |
| 3 | Productionize | App deployed and running in GCP | ✅ Complete |
| 4 | Validation & Improvements | App does what it says; results are trustworthy | ✅ Complete |
| 5 | Polish Sprint | App is camera-ready for public launch | 🔄 Active |

---

## Phase 1 — Foundation & Validation ✅ COMPLETE

> **Historical record.** Phase 1 complete as of 2026-05-03.

### What Was Built

- nflfastR play-by-play, schedules, and rosters loaded into BigQuery (`raw_nflfastr.*`, `curated.*`) for 2015–present
- Closing lines sourced from nflverse `spread_line` field (0% null rate, confirmed as closing lines)
- PR-001: `home_covered` sign convention fixed
- Walk-forward experiment framework: 6-fold harness, leakage guards, BigQuery output to `experiments.*`
- Two baseline experiments: ol_xgb_v1 (48.7% ATS), ol_xgb_v2 (49.6% ATS, 52 features)
- OL mismatch subset defined

### Why Phase 2 Was Unlocked

The original 54% ATS gate was retired (ADR-006). Project goal is a self-service experimentation platform — Phase 1 completion means the infrastructure works and produces real experiments, not that a specific model hit a threshold.

---

## Phase 2 — Service Layer ✅ COMPLETE

> **Historical record.** Phase 2 complete as of 2026-05-06.

### What Was Built

**DATA-PIPELINE** — `platform.*` BigQuery tables, `user_datasets` dataset, experiment config columns. 58/58 validation checks passed.

**BACKEND-API** — Full REST API: games, experiments, predictions, datasets, frameworks, features endpoints. Dataset upload flow. Experiment config + Cloud Run Job trigger. Claude API schema inference.

**MODELING** — Config-driven runner (`backtests/run_experiment.py`). Dynamic feature matrix from curated catalog + user dataset joins. Walk-forward with config-derived folds. BigQuery writes for all Phase 2 fields. Feature importance captured.

**FRONTEND** — All pages built: dashboard, game detail, datasets, experiment wizard, experiment results, model page, frameworks, about. Honest evaluation banner until `gate_passed = true`.

---

## Phase 3 — Productionize ✅ COMPLETE

> **Historical record.** Phase 3 complete as of 2026-05-07.

### What Was Built

**DEVOPS** — Full GCP deployment via Terraform: Cloud Run service (API), Cloud CDN + GCS (frontend), Cloud Run Jobs (experiment runner + data pipeline), Cloud Scheduler (weekly ingest + production refresh), monitoring alerts + runbooks. CI/CD pipelines for API and frontend deploys.

**TESTING-QA** — Integration test suite: pipeline→curated schema tests, no-lookahead data quality tests, runner→BQ write tests, API contract tests, license filtering tests, end-to-end experiment run tests. CI tier documentation.

**BACKEND-API** — `GET /api/v1/predictions?season=N&week=N` endpoint for game-card prediction overlays.

**MODELING** — join-key fix (`_resolve_dataset_join_info`), feature importance scores to BigQuery, `run_production_refresh.py` wrapper.

### Deployment URLs

| Service | URL |
|---------|-----|
| BACKEND-API | https://nfl-backend-api-rmaehdhzhq-uc.a.run.app |
| FRONTEND | http://34.49.20.115 |

### What Didn't Make Phase 3

| Item | Deferred to |
|------|-------------|
| Dataset upload background task → Cloud Run Job | Phase 4 (DEVOPS) |
| `/teams/:team` OL rating time series page | Phase 4 (FRONTEND) |
| Feature importance display in experiment results | Phase 4 (FRONTEND + BACKEND-API) |

---

## Phase 4 — Validation & Improvements 🔄 IN PLANNING

**Start date:** 2026-05-16  
**Status:** Plan written, not yet started. Awaiting project owner review before agents are engaged.  
**Tracking:** `PHASE4_STATUS.md`

### What Phase 4 Is

Phases 1–3 built and shipped the app. Phase 4 is about making it trustworthy and genuinely useful. The app is live, the pipeline runs, and users can configure and trigger experiments — but two things are not yet true:

1. **The results shown can't yet be fully trusted.** The experiment runner has no leakage-detection tooling, no reproducibility controls (hardcoded random seed), and the UI shows only aggregate hit rates with no per-fold breakdown. A user looking at a result like "58.3% ATS" has no way to tell whether it's real, noisy, or an artifact.

2. **The usability is incomplete.** Feature importance isn't displayed in the UI. The per-fold chart on the experiment results page may not be receiving fold-level data from the API. There's no way to compare two experiments side by side. There's no team-level OL rating history page.

Phase 4 fixes both. It is not about adding new model types or new data sources — that is Phase 5 territory. It is about what we already have working correctly and being presented clearly.

### Phase 4 Scope

**Track 1 — Model Validation (does the rushing feature result hold up?)**  
The immediate trigger for Phase 4. Three experiments using 10 rushing features reported 58–61% ATS — a result that contradicts the May 3 baseline (49.65%). Before the app displays this as a meaningful result, it must be verified. Full investigation plan in `RUSH_VALIDATION_PLAN.md`.

**Track 2 — Experiment Runner Improvements (reproducibility and trust tooling)**  
- Configurable random seed via experiment config (currently hardcoded at 42)
- Shuffle-labels mode for leakage detection (currently impossible without ad hoc code edits)
- Standalone analysis script: per-spread-size slice, calibration plot, permutation feature importance
- Standalone comparison script: side-by-side experiment comparison

**Track 3 — App Usability Improvements (surfacing what's already computed)**  
- Per-fold hit rate breakdown surfaced via API and rendered in the experiment results UI
- Feature importance scores displayed on the experiment results page
- `/teams/:team` OL rating time series page
- Dataset upload background task moved to Cloud Run Job (completing the deferred Phase 3 item)

### Phase 4 Agent Engagement Order

Track 2 (runner improvements) and Track 3 (UI/API) can run in parallel once the Phase 4 plan is approved. Track 1 (validation) gates on Track 2's code changes being available first.

| Order | Agent | Work | Unblocks |
|-------|-------|------|----------|
| 1 | MODELING | Track 2 code changes (seed, shuffle, analysis scripts) | Track 1 investigation |
| 1 (parallel) | BACKEND-API | Per-fold data in experiment detail endpoint; feature importance endpoint | FRONTEND Track 3 |
| 2 | MODELING | Track 1 Tier 1 investigation (A1, A2, A3) | PROJECT-LEAD Go/No-Go |
| 2 (parallel) | FRONTEND | Per-fold chart fix, feature importance display, `/teams/:team` | — |
| 2 (parallel) | DEVOPS | Dataset upload Cloud Run Job | — |
| 3 | PROJECT-LEAD | Tier 1 Go/No-Go decision | Track 1 Tier 2 |
| 4 | MODELING | Track 1 Tier 2 investigation (A4–A7) | Track 1 Tier 3 / gate review |
| 5 | PROJECT-LEAD | Formal gate review on validated experiment | Retire honest-eval banner for that experiment |

### Phase 4 Complete When

- At least one experiment has passed the full Tier 1 + Tier 2 validation process and received a formal gate review
- Experiment runner supports configurable seeds and shuffle-labels testing
- Per-fold hit rate breakdown is visible in the experiment results UI (not just the aggregate)
- Feature importance is displayed on the experiment results page
- The honest-evaluation banner is retired for at least one gate-passed experiment
- All Phase 3 deferred items are resolved (dataset upload job, `/teams/:team` page)

---

## Phase 5 — Polish Sprint 🔄 ACTIVE

**Start date:** 2026-05-23  
**Status:** In progress. Triggered by a full live walkthrough of the deployed app (http://34.49.20.115) on 2026-05-23.  
**Tracking:** `PHASE5_STATUS.md`

### What Phase 5 Is

A targeted bug-fix and polish sprint before the app is shown publicly as part of the "Predicting the Game" YouTube series. Every issue below was observed directly during a real user walkthrough — configure an experiment from scratch, run it, and navigate every page.

### Issues Found

| # | Severity | Area | Description |
|---|----------|------|-------------|
| P5-01 | 🔴 Critical | FRONTEND | React Router routes are swapped. Navigating directly to `/experiments` renders the Dashboard. The Experiments nav link routes to `/model`. Any link shared externally lands on the wrong page. |
| P5-02 | 🟠 High | FRONTEND | Experiment wizard Step 3 (Features): clicking checkboxes can trigger backwards navigation to Step 2. Reproducible when the Next/Back buttons are not fully visible in the viewport. |
| P5-03 | 🟠 High | BACKEND-API + FRONTEND | Dataset stuck in `uploading` status since May 9 with no error fallback. Cloud Run Job failed silently; the status in `platform.datasets` was never updated to `error`. No retry, no dismissal, no error message for the user. |
| P5-04 | 🟡 Medium | FRONTEND | Experiment wizard Step 5 (Methodology): `end_season` defaults to 2024. Data runs to 2025. Default should be 2025. |
| P5-05 | 🟡 Medium | FRONTEND + BACKEND-API | Dashboard shows 0 completed experiments despite experiments existing in the system from Phase 4 work. |
| P5-06 | 🟠 High | BACKEND-API | `latest_run` in `GET /api/v1/experiments/:id` response is missing the `per_fold` array. Frontend compensates by fetching predictions filtered to `season=2024`, showing only the most recent fold (F6, 272 games) instead of all 7 folds across 1,828 games. |
| P5-07 | 🟠 High | BACKEND-API | `GET /api/v1/experiments/:id/feature-importance` returns 404. Endpoint not deployed or route not registered in the live Cloud Run service. Feature importance panel never renders. |
| P5-08 | 🟡 Medium | FRONTEND | Experiment wizard shows "5 selected" but the runner automatically mirrors each home feature to its away counterpart, running 10 features total. The wizard should communicate this — e.g. "5 selected (10 with away mirrors)" — so users aren't surprised when results show double the features. |

### Fix Plan

**FRONTEND** owns P5-01, P5-02, P5-04, and the display side of P5-05:

- P5-01: Audit `src/router` (or equivalent routing config). Correct the path-to-component mappings so `/experiments` → ExperimentsPage, `/model` → ModelPage. Verify all six nav links route to the correct URL and component.
- P5-02: Investigate the Features step scroll/click interaction. Likely cause: a click on a low-positioned checkbox is being captured by an underlying Back button when the wizard card is partially scrolled. Fix hit targets or ensure Back/Next are outside the scrollable card.
- P5-04: In the New Experiment wizard Step 5, change the `end_season` default from `2024` to `2025`.
- P5-05 (display): Once the API correctly returns completed experiment counts, ensure the dashboard stat card re-fetches and renders correctly.

**BACKEND-API** owns P5-03, P5-05 (query), P5-06, and P5-07:

- P5-03: Add a timeout-based status reconciliation for datasets stuck in `uploading`. Any dataset in `uploading` state for more than 30 minutes should be flipped to `error` with a human-readable message. Implement either as a check on the `GET /api/v1/datasets/:id` endpoint (lazy reconciliation) or as a Cloud Scheduler job (proactive). Also add a `DELETE /api/v1/datasets/:id` endpoint so users can remove failed datasets.
- P5-05 (query): Audit the `GET /api/v1/dashboard` (or equivalent) query. Confirm it is counting completed experiments from `experiments.backtest_runs` correctly and returning the right count to the frontend.
- P5-06: Add `per_fold: [{season, wins, losses, pushes, hit_rate, n_games}]` to the `latest_run` object in `GET /api/v1/experiments/:id`. Source from `experiments.backtest_predictions` grouped by season for the `latest_run_id`. This was specced in Phase 4 Track 3 item 3.1 but is absent from the live API response.
- P5-07: Verify `GET /api/v1/experiments/:id/feature-importance` is correctly registered in `app/main.py` and included in the deployed Cloud Run image. The endpoint returns 404 in production. Check router inclusion and redeploy if needed.

**FRONTEND** owns P5-01, P5-02, P5-04, P5-05 (display), and P5-08:

- P5-01: Audit `src/router` (or equivalent routing config). Correct the path-to-component mappings so `/experiments` → ExperimentsPage, `/model` → ModelPage. Verify all six nav links route to the correct URL and component.
- P5-02: Investigate the Features step scroll/click interaction. Likely cause: a click on a low-positioned checkbox is being captured by an underlying Back button when the wizard card is partially scrolled. Fix hit targets or ensure Back/Next are outside the scrollable card.
- P5-04: In the New Experiment wizard Step 5, change the `end_season` default from `2024` to `2025`.
- P5-05 (display): Once the API correctly returns completed experiment counts, ensure the dashboard stat card re-fetches and renders correctly.
- P5-08: In Step 3 (Features), add a note below the selected count explaining that each selected feature is automatically mirrored to its away-team counterpart — e.g. "5 selected · 10 features used in model (home + away mirrors)".

### Agent Engagement Order

| Order | Agent | Items |
|-------|-------|-------|
| 1 (parallel) | FRONTEND | P5-01, P5-02, P5-04, P5-05 display, P5-08 |
| 1 (parallel) | BACKEND-API | P5-03, P5-05 query, P5-06, P5-07 |

### Phase 5 Complete When

- All routes in the nav work correctly and direct URL navigation works
- A new user can complete the full experiment wizard without being kicked back to a previous step
- Stuck datasets show an error state and can be deleted
- `end_season` defaults to 2025
- Dashboard experiment count reflects reality
- Per-fold chart displays all folds, not just the most recent season
- Feature importance panel renders on completed experiment results pages
- Wizard communicates the home/away feature mirroring behaviour

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
| 010 | Terraform selected for IaC | Accepted |
