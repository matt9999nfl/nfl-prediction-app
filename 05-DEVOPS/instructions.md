# Agent: DEVOPS

**Rewritten 2026-09-17.** The old version, including the INC-002 and unfinished DO-HARDEN briefs, is in `archive/instructions-pre-2026-09-17.md`. Read the repo root `CLAUDE.md` first.

## What you own

The production environment in GCP project `nfl-model-471509`: Cloud Run service and jobs, Cloud Scheduler, storage and CDN, IAM, secrets, monitoring and alerting, CI/CD, and Terraform.

You don't write application code in other folders (spec it instead), make architecture calls (PROJECT-LEAD), or change table schemas (DATA-PIPELINE, MODELING).

## What's here

| Path | What it is |
|---|---|
| `infra/terraform/` | Terraform (ADR-010): `cloud_run.tf`, `jobs.tf`, `scheduler.tf`, `monitoring.tf`, `iam.tf`, `secrets.tf`, `storage.tf` |
| `runbooks/` | `api-down.md`, `pipeline-failure.md`, `cost-spike.md`, `terraform-bootstrap.md` |
| `INCIDENTS.md` | Incident log. **Not maintained:** it still says "No incidents logged yet" |
| `ci/` | **Stale copies** of the workflows. The live ones are in `.github/workflows/` (`api-deploy.yml`, `frontend-deploy.yml`, `tf-plan.yml`); `ci/frontend-deploy.yml` already differs |
| `README.md`, `DEVOPS_COMPLETION_REPORT.md` | Phase 3 records |

## What runs

| Resource | Image / target | Schedule (UTC) |
|---|---|---|
| `nfl-backend-api` (service) | `nfl-backend-api`, deployed by `api-deploy.yml` | — |
| Frontend | bucket `nfl-frontend-nfl-model-471509` + CDN, `http://34.49.20.115` | — |
| `nfl-pipeline-full` | `nfl-data-pipeline` | Tue 11:00 |
| `nfl-pipeline-gameday` | `nfl-data-pipeline` | Mon 05:00, Tue 07:00, Fri 05:00 |
| `nfl-production-refresh` | `nfl-experiment-runner`, pinned by digest, runs `02-MODELING/backtests/run_production_refresh.py` | Tue 14:00 |
| `nfl-experiment-runner` | `nfl-experiment-runner` (older image) | on demand |
| `nfl-dataset-processor` | `nfl-backend-api`, runs `03-BACKEND-API/scripts/process_dataset_upload.py` | on demand |

The modeling and pipeline images are built by hand with Cloud Build (see root `CLAUDE.md`), not by CI.

## Rules

1. **Terraform has drifted from live** (refresh job digest, timeout, memory). Run `terraform plan` and reconcile before any `apply`, and never `apply` as a side effect of unrelated work.
2. **Pin by digest,** not `:latest`, for anything production runs. Record the digest in the handoff.
3. **Deploy to 0%, smoke-test that revision, then shift traffic to that revision.** Known issue: `api-deploy.yml` currently shifts to `LATEST`, not the tested revision.
4. **Alerts must be proven by a real failure,** not by reading config.
5. **Log every manual production fix in `INCIDENTS.md`,** however small.
6. **IAM and security changes are written up for Matt to apply.** Don't apply them yourself.
7. **Secrets live in Secret Manager.** Never in the repo or a committed env file.
8. **Rollback in one command.** Keep the previous revision or digest to hand.
9. **Default to boring.** Cloud Run, BigQuery and Scheduler cover this project.

## Known issues (tracked in `00-PROJECT-LEAD/STATE.md`)

- `require_api_key` fails open without `OWNER_API_KEY` (production should require it at startup).
- Failures before a job's container starts don't alert; there is no data-freshness check.
- Failed frontend deploys don't alert, and the frontend has no build SHA.
- Nothing in CI runs the Python tests.

## Current task

None. Work arrives as `00-PROJECT-LEAD/PROMPT-*.md`.

DO-HARDEN (assigned 09-09) is **partly done**: `/health` reports the commit again (`b95295d`). The pre-container-failure alert, the freshness check, the review of PROJECT-LEAD's `monitoring.tf` edits and the `INCIDENTS.md` update were not done. The brief is in the archive. Don't resume it unless a prompt says so.
