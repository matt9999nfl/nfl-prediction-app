# Phase 3 Status

**Owner:** PROJECT-LEAD
**Last updated:** 2026-05-07
**Phase 3 start date:** 2026-05-06

This file is updated by agents as they complete deliverables. PROJECT-LEAD reads it to track parallel work and decide when to engage the next agent.

---

## Deployment URLs

| Service | URL | Status |
|---------|-----|--------|
| BACKEND-API (Cloud Run) | https://nfl-backend-api-rmaehdhzhq-uc.a.run.app | ✅ Live |
| FRONTEND (Cloud Storage + CDN) | _pending frontend deploy_ | 🔧 Code ready |

**Bootstrap Status:** ✅ Complete. All GCP infrastructure provisioned via Terraform on 2026-05-07.

---

## DEVOPS Deliverables

| # | Deliverable | Status | Notes |
|---|-------------|--------|-------|
| 1a | `nfl-backend-api` Cloud Run service deployed + healthy | ✅ Complete | Live at https://nfl-backend-api-rmaehdhzhq-uc.a.run.app — `/health` returning 200 |
| 1b | CI pipeline for API deploys | ✅ Complete | `.github/workflows/api-deploy.yml` with smoke tests, traffic shift |
| 2a | FRONTEND static site at HTTPS URL | 🔧 Code ready | Terraform + CDN provisioned; frontend files not yet deployed to bucket |
| 2b | CI pipeline for frontend deploys | ✅ Complete | `.github/workflows/frontend-deploy.yml` with cache headers |
| 3a | Experiment runner packaged as Cloud Run Job | ✅ Complete | `02-MODELING/Dockerfile.job`, Terraform job config ready |
| 3b | BACKEND-API stub → real Cloud Run Job trigger | ✅ Complete | Real `trigger_experiment_runner()` function in experiments.py + router call updated |
| 3c | Dataset upload background task swap | ⏳ Pending | Requires similar job infrastructure (deferred) |
| 4 | DATA-PIPELINE Cloud Run Jobs + Scheduler | ✅ Complete | `01-DATA-PIPELINE/Dockerfile.job`, wrapper script, Terraform jobs + scheduler |
| 5 | Production refresh Scheduler (needs MODELING wrapper) | 🔧 Code ready | Terraform job/scheduler configured, stub at `02-MODELING/backtests/run_production_refresh.py` |
| 6 | Monitoring, alerting, budgets, runbooks | ✅ Complete | Terraform alerts, email channel, 4 runbooks (`api-down`, `pipeline-failure`, `cost-spike`, `terraform-bootstrap`) |
| 7 | Everything in Terraform, reproducible | ✅ Complete | Full Terraform modules in `05-DEVOPS/infra/terraform/` (main, variables, iam, secrets, cloud_run, jobs, scheduler, storage, monitoring) |

---

## TESTING-QA Deliverables (unblocks: DEVOPS Step 1a)

| # | Deliverable | Status | Notes |
|---|-------------|--------|-------|
| 1 | `conftest.py`, `pytest.ini`, `requirements.txt` | ✅ Complete | Shared fixtures, markers, dependencies |
| 2 | Schema contract tests (Seam 1) | ✅ Complete | `test_pipeline_to_curated.py` — curated.* shape + coverage |
| 3 | Data quality tests (Seam 2) | ✅ Complete | `test_no_lookahead.py` — no look-ahead leakage, prob ranges |
| 4 | Runner → BQ writes tests (Seam 3, Tier 3) | ✅ Complete | `test_runner_bq_writes.py` — backtest_runs, predictions, status |
| 5 | API contract tests (Seam 4) | ✅ Complete | `test_api_contract.py` — health, games, experiments, features, predictions |
| 6 | License filtering tests (Seam 5, critical) | ✅ Complete | `test_license_filtering.py` — personal_use_only never in public API |
| 7 | End-to-end tests (Seam 6, Tier 3, live) | ✅ Complete | `test_e2e_experiment_run.py` — create → run → poll → verify |
| 8 | CI tier documentation | ✅ Complete | `ci-tiers.md` — Tier 2 (PR), Tier 3 (nightly) with commands |

---

## BACKEND-API Deliverables (unblocks: DEVOPS Step 1a)

| # | Deliverable | Status | Notes |
|---|-------------|--------|-------|
| 1 | `GET /api/v1/predictions?season=N&week=N` endpoint | ✅ Complete | Router + query layer + schemas + tests + API contract. X-API-Key enforcement live on write endpoints. |

---

## MODELING Deliverables (unblocks: DEVOPS Step 3)

| # | Deliverable | Status | Notes |
|---|-------------|--------|-------|
| 1 | Fix join-key to read `join_key_columns` from `platform.datasets` | ✅ Complete | `_resolve_dataset_join_info()` + `_join_user_dataset()` use actual column names |
| 2 | Write feature importance scores to BigQuery | ✅ Complete | `feature_importances JSON` column added to backtest_runs; mean importances captured |
| 3 | Write `run_production_refresh.py` wrapper | ✅ Complete | Full Cloud Run Job trigger implementation; queries gate_passed experiments |

---

## FRONTEND Deliverables (unblocks: BACKEND-API predictions endpoint)

| # | Deliverable | Status | Notes |
|---|-------------|--------|-------|
| — | Add `/teams/:team` page (OL rating time series) | ⏳ Not started | Needs `GET /api/v1/teams/{team}/ol-rating` live |
| — | Feature importance display on experiment results | ⏳ Not started | Needs MODELING + API endpoint |

---

## Incidents

_None yet._
