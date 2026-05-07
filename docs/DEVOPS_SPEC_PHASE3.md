# DEVOPS Spec — Phase 3

**Owner:** PROJECT-LEAD
**Assigned to:** DEVOPS
**Date:** 2026-05-06
**Status:** Active — DEVOPS agent engaged

---

## Read These First

Before writing a line of infrastructure code, read these documents in order:

1. `../05-DEVOPS/instructions.md` — your role, principles, and layout
2. `../docs/ARCHITECTURE.md` — system design, component boundaries, data flow cadence
3. `../docs/DECISIONS.md` — ADR-001 through ADR-010, especially ADR-003 (Cloud Run), ADR-008 (BackgroundTasks swap), ADR-010 (Terraform)
4. `../docs/API_CONTRACTS.md` — understand the API surface before wiring secrets

Everything you build must be reproducible from `05-DEVOPS/infra/terraform/`. If a resource exists in production but not in `.tf` files, it's technical debt. No exceptions.

---

## What You Are Deploying

The full Phase 3 deployment in sequence. Steps 1 and 2 unblock TESTING-QA, BACKEND-API, and FRONTEND work. Step 3 unblocks end-to-end experiment runs. Steps 4–6 complete the production data refresh cycle. Step 7 is continuous — IaC is woven throughout.

---

## Step 1 — Deploy BACKEND-API as a Cloud Run Service

**Deliverable:** `https://api.{your-cloud-run-url}/health` returns `{"status": "ok"}`. Smoke test passes.

### Container

The Dockerfile is at `03-BACKEND-API/Dockerfile`. It expects:
- Python 3.11-slim base
- `pyproject.toml` dependencies installed
- `app/` copied in
- Exposed on port 8080
- `GIT_COMMIT` build arg baked in (pass from CI via `--build-arg GIT_COMMIT=$(git rev-parse --short HEAD)`)

### Service Account

Create a dedicated service account `nfl-api-sa@nfl-model-471509.iam.gserviceaccount.com` with exactly these roles:

| Permission | Why |
|------------|-----|
| `roles/bigquery.dataViewer` on `platform.*`, `experiments.*`, `curated.*`, `user_datasets.*` | Read all API-served data |
| `roles/bigquery.dataEditor` on `platform.*` | Write experiment configs, dataset registry, frameworks |
| `roles/bigquery.dataEditor` on `experiments.backtest_runs` | Write initial run row on trigger |
| `roles/bigquery.jobUser` on project | Execute queries |
| `roles/storage.objectAdmin` on `gs://nfl-model-471509-uploads` | Dataset file upload + read |
| `roles/run.invoker` on the experiment-runner Cloud Run Job | Trigger jobs from the API (Step 3) |
| `roles/secretmanager.secretAccessor` on `ANTHROPIC_API_KEY`, `OWNER_API_KEY` | Read secrets at runtime |

Do not grant project-level `bigquery.admin` or `roles/editor`. Least-privilege per ADR-001 consequences and `05-DEVOPS/instructions.md` principle 3.

### Secrets

Store these in Secret Manager (project `nfl-model-471509`). Never in `.env` files, never in git:

| Secret name | Value | Used by |
|-------------|-------|---------|
| `ANTHROPIC_API_KEY` | Anthropic API key | BACKEND-API (`claude_inference.py`) |
| `OWNER_API_KEY` | A random 32-char token you generate | BACKEND-API (`app/config.py` — Phase 3 auth) |

Mount both as environment variables in the Cloud Run service definition. The `app/config.py` already reads them via `os.getenv("ANTHROPIC_API_KEY")` and `os.getenv("OWNER_API_KEY")`.

### Cloud Run Service Config

```
Service name:      nfl-backend-api
Region:            us-central1
Min instances:     0  (scale-to-zero — solo project, no idle cost)
Max instances:     3
Memory:            512Mi
CPU:               1
Concurrency:       80
Timeout:           60s
Port:              8080
Ingress:           all (public HTTPS)
Service account:   nfl-api-sa@nfl-model-471509.iam.gserviceaccount.com
Env vars (from Secret Manager):
  ANTHROPIC_API_KEY  → secret:ANTHROPIC_API_KEY/latest
  OWNER_API_KEY      → secret:OWNER_API_KEY/latest
Env vars (direct):
  BIGQUERY_PROJECT   = nfl-model-471509
  GIT_COMMIT         = (set at deploy time from git SHA)
```

### CI Deploy Pipeline

Create `05-DEVOPS/ci/api-deploy.yml` (GitHub Actions). Trigger: push to `main` where `03-BACKEND-API/**` changed.

```
Steps:
1. Checkout
2. Authenticate to GCP (Workload Identity Federation preferred; fallback: SA key from repo secret GCP_SA_KEY)
3. docker build --build-arg GIT_COMMIT=$(git rev-parse --short HEAD) -t gcr.io/nfl-model-471509/nfl-backend-api:$SHA 03-BACKEND-API/
4. docker push gcr.io/nfl-model-471509/nfl-backend-api:$SHA
5. gcloud run deploy nfl-backend-api --image gcr.io/nfl-model-471509/nfl-backend-api:$SHA --no-traffic
6. Smoke test: curl https://{new-revision-url}/health → assert {"status": "ok"}
7. gcloud run services update-traffic nfl-backend-api --to-latest
8. Alert on failure (Step 6 failure = failed deploy alert)
```

Traffic-at-zero on deploy + smoke test before shifting traffic is the required SOP from `instructions.md`.

### Smoke Test Checklist (run after deploy)

- `GET /health` → 200, `{"status": "ok"}`
- `GET /api/v1/games?season=2024&limit=5` → 200, non-empty `data` array
- `GET /api/v1/experiments?limit=5` → 200 (may be empty, no error)
- `GET /api/v1/features` → 200, non-empty `data` array
- `POST /api/v1/experiments/{bogus-id}/run` → 404 (validates routing works)

**Output of this step:** Post the deployed Cloud Run URL to `00-PROJECT-LEAD/PHASE3_STATUS.md`. TESTING-QA, BACKEND-API, and FRONTEND all unblock from this URL.

---

## Step 2 — Deploy FRONTEND as Static Site on Cloud Storage + Cloud CDN

**Deliverable:** The dashboard loads at a public HTTPS URL and `VITE_API_BASE_URL` points at the Step 1 Cloud Run URL.

### Build

```bash
cd 04-FRONTEND
VITE_API_BASE_URL=https://{cloud-run-api-url} npm run build
# Outputs: dist/
```

Run `npm run types:generate` first if `openapi.gen.ts` has not been regenerated against the live API yet.

### Cloud Storage Bucket

```
Bucket name:     nfl-frontend-{project-id}   (or nfl-prediction-app-frontend)
Location:        us-central1
Storage class:   STANDARD
Public access:   allUsers objectViewer (static website hosting)
Website config:  main_page_suffix = index.html
                 not_found_page   = index.html   ← required for client-side routing (React Router)
```

The `not_found_page = index.html` is critical — without it, direct navigation to `/experiments/abc123` returns a 404 from GCS instead of letting React Router handle it.

### Cloud CDN

Attach a Cloud CDN + HTTP(S) Load Balancer backend to the bucket. This provides:
- HTTPS termination with a managed certificate
- Global edge caching for static assets
- Custom domain support (optional for Phase 3 — raw Load Balancer IP is fine)

Cache config:
```
Cache mode:        CACHE_ALL_STATIC
Default TTL:       3600s
Max TTL:           86400s
Cache-Control on index.html:  no-cache, no-store, must-revalidate  (set on upload)
Cache-Control on assets/*:    public, max-age=31536000, immutable   (hashed filenames from Vite)
```

### CI Deploy Pipeline

Create `05-DEVOPS/ci/frontend-deploy.yml` (GitHub Actions). Trigger: push to `main` where `04-FRONTEND/**` changed.

```
Steps:
1. Checkout
2. Setup Node 20
3. npm ci (in 04-FRONTEND/)
4. VITE_API_BASE_URL=https://{api-url} npm run build
5. Authenticate to GCP
6. gsutil -m rsync -r -d dist/ gs://nfl-frontend-{id}/
7. Set Cache-Control headers (index.html: no-cache; assets/: immutable)
8. Invalidate Cloud CDN cache for index.html
```

### Smoke Test

- Load the root URL in a browser → dashboard renders, no console errors
- Network tab shows API calls going to the correct Cloud Run URL
- Navigate directly to `/experiments` (not via link) → page renders (tests `not_found_page` config)

---

## Step 3 — Swap BackgroundTasks Stub for Real Cloud Run Job Trigger

**Deliverable:** `POST /api/v1/experiments/{id}/run` actually fires `02-MODELING/backtests/run_experiment.py` as a Cloud Run Job execution with `EXPERIMENT_CONFIG_ID` set to the experiment's UUID.

This is the change that makes end-to-end experiment runs work.

### The Stub (what exists now)

In `03-BACKEND-API/app/queries/experiments.py`, the function `trigger_experiment_runner_stub(experiment_id, run_id)` logs the intent but does nothing. The router at `routers/experiments.py` line 403 calls `eq.trigger_experiment_runner_stub(experiment_id, run_id)` immediately after writing the initial run row to BigQuery.

The router does not need to change. Only the stub function needs to be replaced with a real Cloud Run Jobs API call.

### Package the Experiment Runner as a Cloud Run Job

Create `02-MODELING/Dockerfile.job`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install R and nfl_data_py dependencies (see 02-MODELING/requirements.txt or pyproject.toml)
COPY pyproject.toml .
RUN pip install --no-cache-dir . 2>/dev/null || pip install --no-cache-dir -r requirements.txt

COPY . .

# Entry point: run_experiment.py reads EXPERIMENT_CONFIG_ID from env
CMD ["python", "backtests/run_experiment.py"]
```

Build and push:
```
gcr.io/nfl-model-471509/nfl-experiment-runner:latest
```

Create Cloud Run Job:
```
Job name:        nfl-experiment-runner
Region:          us-central1
Image:           gcr.io/nfl-model-471509/nfl-experiment-runner:latest
CPU:             2
Memory:          4Gi
Max retries:     0   (no retries — runner updates BQ status itself; retry would double-write)
Timeout:         3600s   (1 hour — full walk-forward can take ~30 min on large configs)
Service account: nfl-runner-sa@nfl-model-471509.iam.gserviceaccount.com
```

Runner service account `nfl-runner-sa` needs:
- `roles/bigquery.dataViewer` on `curated.*`, `user_datasets.*`
- `roles/bigquery.dataEditor` on `experiments.*`, `platform.experiment_configs` (status update)
- `roles/bigquery.jobUser` on project

### Implement the Real Trigger

Replace `trigger_experiment_runner_stub` in `03-BACKEND-API/app/queries/experiments.py` with a function that calls the Cloud Run Jobs API:

```python
import google.auth
import google.auth.transport.requests
import requests as http_requests

def trigger_experiment_runner(experiment_id: str, run_id: str) -> None:
    """
    Create a Cloud Run Job execution for the experiment runner.
    EXPERIMENT_CONFIG_ID is passed as an env var override on the execution.
    run_id is passed as NFL_RUN_ID for logging; the runner writes it to BQ.
    """
    credentials, project = google.auth.default()
    credentials.refresh(google.auth.transport.requests.Request())

    region = "us-central1"
    job_name = "nfl-experiment-runner"
    url = (
        f"https://{region}-run.googleapis.com/apis/run.googleapis.com/v1/"
        f"namespaces/{project}/jobs/{job_name}:run"
    )

    payload = {
        "overrides": {
            "containerOverrides": [{
                "env": [
                    {"name": "EXPERIMENT_CONFIG_ID", "value": experiment_id},
                    {"name": "NFL_RUN_ID", "value": run_id},
                ]
            }]
        }
    }

    resp = http_requests.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {credentials.token}"},
    )
    resp.raise_for_status()
    logger.info(
        "Cloud Run Job execution created for experiment %s (run %s): %s",
        experiment_id, run_id, resp.json().get("metadata", {}).get("name"),
    )
```

**Update the router call site** in `routers/experiments.py` line 403:
```python
# Before (stub):
eq.trigger_experiment_runner_stub(experiment_id, run_id)

# After:
eq.trigger_experiment_runner(experiment_id, run_id)
```

Also add `google-auth`, `requests` to `03-BACKEND-API/pyproject.toml` dependencies if not already present (they likely are via `google-cloud-bigquery`).

### Also Swap the Dataset Upload Background Task

Per ADR-008, `process_upload_background` in the dataset upload flow also runs in a `BackgroundTasks` stub. This is lower priority than the experiment runner but should be swapped in the same pass:

Create a second Cloud Run Job `nfl-dataset-processor` that receives `DATASET_ID` and handles parse → BigQuery load → column registration. The BACKEND-API dataset router calls this job the same way as the experiment runner.

If time is constrained, the experiment runner swap is the blocker — the dataset upload background task can follow in the same PR or a close follow-on.

### Smoke Test

1. Via the dashboard (or `curl`), create an experiment config pointing at a known-good curated feature set
2. `POST /api/v1/experiments/{id}/run` → 202, `{"run_id": "...", "status": "running"}`
3. Cloud Run Jobs console shows a new execution in `RUNNING` state for `nfl-experiment-runner`
4. Poll `GET /api/v1/experiments/{id}/status` → transitions from `running` to `complete`
5. `GET /api/v1/experiments/{id}` → `latest_run` present with `ats_hit_rate` populated
6. BigQuery: `SELECT * FROM experiments.backtest_predictions WHERE experiment_id = '{id}' LIMIT 5` → rows present

---

## Step 4 — Cloud Run Jobs for DATA-PIPELINE Scheduled Ingest

**Deliverable:** Two Cloud Scheduler entries firing Cloud Run Jobs for the nflfastR ingest on the correct schedules.

### Package the Pipeline as a Cloud Run Job

Entry point: `01-DATA-PIPELINE/scripts/run_pipeline.py`

Create `01-DATA-PIPELINE/Dockerfile.job`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# R is required for nfl_data_py (which calls R under the hood via rpy2 or nfl_data_py's own R dependency)
# Check 01-DATA-PIPELINE/requirements.txt for the exact dep chain
RUN apt-get update && apt-get install -y --no-install-recommends r-base && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir . 2>/dev/null || pip install --no-cache-dir -r requirements.txt

COPY . .

# PIPELINE_MODE is set by Cloud Scheduler: "full" or "gameday"
# Full:    python scripts/run_pipeline.py
# Gameday: python scripts/run_pipeline.py --start-at 1 (schedules only, skip PBP full rebuild)
# The wrapper script below reads PIPELINE_MODE and dispatches.
CMD ["python", "scripts/run_pipeline_job.py"]
```

**Create `01-DATA-PIPELINE/scripts/run_pipeline_job.py`** — a thin wrapper that reads `PIPELINE_MODE` env var and calls `run_pipeline.py` with the right arguments:

```python
"""
Cloud Run Job entrypoint.
PIPELINE_MODE=full    → full season refresh (all steps)
PIPELINE_MODE=gameday → gameday refresh (schedules + curated.games only)
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

mode = os.environ.get("PIPELINE_MODE", "full")

if mode == "full":
    # Full pipeline: ingest raw data + rebuild curated layer
    from scripts.run_pipeline import main
    main()
elif mode == "gameday":
    # Gameday refresh: schedules + curated.games only (skip PBP/rosters for speed)
    from scripts.run_pipeline import main
    import sys
    sys.argv = ["run_pipeline.py", "--start-at", "1"]
    main()
else:
    print(f"Unknown PIPELINE_MODE: {mode}", file=sys.stderr)
    sys.exit(1)
```

> **Note to DEVOPS:** Confirm with DATA-PIPELINE that `--start-at 1` is the correct invocation for a gameday refresh (schedules refresh → curated.games rebuild, skip PBP/rosters). If DATA-PIPELINE needs a separate `--gameday` flag, flag this to PROJECT-LEAD before deploying.

Build and push:
```
gcr.io/nfl-model-471509/nfl-data-pipeline:latest
```

### Cloud Run Jobs

```
Job name:        nfl-pipeline-full
Image:           gcr.io/nfl-model-471509/nfl-data-pipeline:latest
CPU:             2
Memory:          8Gi   (nfl_data_py loads full season PBP into memory)
Max retries:     1     (idempotent — safe to retry)
Timeout:         7200s (2 hours — full multi-season ingest)
Service account: nfl-pipeline-sa@nfl-model-471509.iam.gserviceaccount.com
Env: PIPELINE_MODE=full

Job name:        nfl-pipeline-gameday
Image:           gcr.io/nfl-model-471509/nfl-data-pipeline:latest
CPU:             2
Memory:          4Gi
Max retries:     2
Timeout:         1800s (30 min)
Service account: nfl-pipeline-sa@nfl-model-471509.iam.gserviceaccount.com
Env: PIPELINE_MODE=gameday
```

Pipeline service account `nfl-pipeline-sa` needs:
- `roles/bigquery.dataEditor` on `raw_nflfastr.*`, `curated.*`
- `roles/bigquery.jobUser` on project

### Cloud Scheduler Entries

```
Job name:   nfl-pipeline-full-weekly
Schedule:   0 11 * * 2          (Tuesday 6am ET = 11:00 UTC)
Target:     Cloud Run Job nfl-pipeline-full
Time zone:  America/New_York

Job name:   nfl-pipeline-gameday-sunday
Schedule:   0 5 * * 1           (Monday 12am ET ≈ 5:00 UTC Monday — covers Sunday games)
Target:     Cloud Run Job nfl-pipeline-gameday
Time zone:  UTC

Job name:   nfl-pipeline-gameday-monday
Schedule:   0 7 * * 2           (Tuesday 2am ET = 7:00 UTC — covers Monday Night)
Target:     Cloud Run Job nfl-pipeline-gameday
Time zone:  UTC

Job name:   nfl-pipeline-gameday-thursday
Schedule:   0 5 * * 5           (Thursday 12am ET ≈ 5:00 UTC Friday — covers Thursday Night)
Target:     Cloud Run Job nfl-pipeline-gameday
Time zone:  UTC
```

> Note: The gameday schedules are approximate — nflfastR data is typically available within a few hours of game end. The exact times can be tuned post-launch if data arrives later than expected.

---

## Step 5 — Cloud Scheduler for Weekly MODELING Re-run

**Deliverable:** Every Tuesday at 9am ET, any `gate_passed = true` experiment is re-run to generate current-week predictions.

### MODELING Wrapper Script Needed

The experiment runner is designed for a single experiment (one `EXPERIMENT_CONFIG_ID`). A production refresh needs to query for all gate-passed experiments and fire one job execution per experiment. **This wrapper does not exist yet — MODELING must write it.**

File: `02-MODELING/backtests/run_production_refresh.py`

Spec for MODELING (relay this when engaging MODELING agent):
```
Write a script that:
1. Queries platform.experiment_configs WHERE gate_passed = true AND status != 'running'
2. For each result, creates a Cloud Run Job execution for nfl-experiment-runner
   with EXPERIMENT_CONFIG_ID set to that experiment's ID
3. Logs which experiments were triggered, which were skipped (already running)
4. Exits 0 on success; exits 1 if any execution creation fails

The script uses the same google-cloud-run execution API that BACKEND-API uses in
trigger_experiment_runner(). It should be a standalone script, not a FastAPI endpoint.
It will be the CMD of a new Cloud Run Job: nfl-production-refresh.
```

### Cloud Run Job (pending MODELING wrapper)

```
Job name:        nfl-production-refresh
Image:           gcr.io/nfl-model-471509/nfl-experiment-runner:latest
                 (same image — add run_production_refresh.py to 02-MODELING/)
CMD override:    python backtests/run_production_refresh.py
CPU:             1
Memory:          512Mi  (it only triggers jobs, doesn't run the model itself)
Max retries:     1
Timeout:         120s
Service account: nfl-runner-sa@nfl-model-471509.iam.gserviceaccount.com
  (needs roles/run.developer to create job executions)
```

### Cloud Scheduler

```
Job name:   nfl-production-refresh-weekly
Schedule:   0 14 * * 2          (Tuesday 9am ET = 14:00 UTC)
Target:     Cloud Run Job nfl-production-refresh
Time zone:  America/New_York
```

**Sequencing dependency:** This step requires:
1. MODELING to deliver `run_production_refresh.py`
2. At least one experiment with `gate_passed = true` in BigQuery (may not exist until after Step 3 is live and experiments can be run end-to-end)

Deploy the Cloud Scheduler entry now. The job executions will be no-ops (no gate-passed experiments yet) until real experiments clear their gates.

---

## Step 6 — Monitoring and Alerting Baseline

**Deliverable:** The owner (matt.lilley4@gmail.com) receives email alerts for every failure mode defined in `05-DEVOPS/instructions.md`. Every alert has a corresponding runbook entry.

### Notification Channel

Create a Cloud Monitoring email notification channel for `matt.lilley4@gmail.com`. All alert policies below use this channel.

### Alert Policies

Create these in Cloud Monitoring. All thresholds are from `05-DEVOPS/instructions.md`.

**1. Cloud Run 5xx Rate**
```
Metric:      run.googleapis.com/request_count
Filter:      resource.labels.service_name = "nfl-backend-api"
             metric.labels.response_code_class = "5xx"
Condition:   rate > 5% of total requests over 5-minute window
Severity:    Critical
Runbook:     05-DEVOPS/runbooks/api-down.md
```

**2. Scheduled Job Failure — any Cloud Run Job**
```
Metric:      run.googleapis.com/job/completed_execution_count
Filter:      metric.labels.result = "failed"
Condition:   count > 0 in 10-minute window
Severity:    Critical
Runbook:     05-DEVOPS/runbooks/pipeline-failure.md
```

**3. BigQuery Daily Cost**
```
Use Cloud Billing budget alert (not Monitoring) — see Budget section below.
A separate Monitoring alert can be set on the bigquery.googleapis.com/storage/table_count
or on Billing exported to BigQuery, but the billing budget alert is sufficient.
```

**4. Failed CI Deploy**
In `05-DEVOPS/ci/api-deploy.yml` and `frontend-deploy.yml`, add a final step that sends an email via the GCP notification channel (or use GitHub Actions' built-in failure notification to the repo owner) on any job failure.

### Budget Alert

Create a Cloud Billing budget in `05-DEVOPS/infra/terraform/`:

```
Budget name:       nfl-prediction-app-monthly
Scope:             project nfl-model-471509
Amount:            $50/month (hard cap awareness)
Alert thresholds:
  50%  → email notification
  80%  → email notification
  100% → email notification
BigQuery daily:    Set a per-query cost limit of $5 on the nfl-api-sa service account
                   (bigquery.datasets.setIamPolicy or per-project default table expiry)
```

### Runbook Files

Create these stubs in `05-DEVOPS/runbooks/`. Fill in cause/fix sections based on what you know at deploy time:

**`05-DEVOPS/runbooks/api-down.md`**
```markdown
# Runbook: API Down / High 5xx Rate

## Symptoms
Cloud Monitoring alert: nfl-backend-api 5xx rate > 5% over 5 minutes.

## Immediate Actions
1. Check Cloud Run logs: gcloud run services logs read nfl-backend-api --limit=50
2. Check if the last deploy introduced a regression:
   gcloud run services describe nfl-backend-api --format="value(status.latestReadyRevisionName)"
3. Roll back if needed:
   gcloud run services update-traffic nfl-backend-api --to-revisions=PREVIOUS_REVISION=100

## Common Causes
- Bad deploy: rollback via gcloud (see above)
- BigQuery quota exceeded: check https://console.cloud.google.com/bigquery/quotas
- Secret rotation: verify Secret Manager versions are current
- Cold start timeout (rare): check if min-instances=0 is causing timeouts under load

## Escalation
None — solo project. Log in INCIDENTS.md.
```

**`05-DEVOPS/runbooks/pipeline-failure.md`**
```markdown
# Runbook: Pipeline / Job Failure

## Symptoms
Cloud Monitoring alert: Cloud Run Job completed with result=failed.

## Immediate Actions
1. Identify which job failed:
   gcloud run jobs executions list --job=nfl-pipeline-full
   gcloud run jobs executions list --job=nfl-experiment-runner
2. View logs:
   gcloud run jobs executions describe EXECUTION_NAME
   gcloud logging read 'resource.type="cloud_run_job"' --limit=100
3. Check if data source is available (nfl_data_py may fail if nflverse is down)
4. Re-run manually if safe:
   gcloud run jobs execute nfl-pipeline-full

## Common Causes
- nflverse/nflfastR data not available yet (gameday refresh ran too early)
- BigQuery write quota exceeded
- Experiment runner: bad config in platform.experiment_configs (check error_message column)
- OOM: increase Memory in job config if job OOM-killed

## Escalation
None. Log in INCIDENTS.md with date, cause, fix, prevention.
```

**`05-DEVOPS/runbooks/cost-spike.md`**
```markdown
# Runbook: Cost Spike

## Symptoms
Cloud Billing alert: monthly spend at 50%/80%/100% of $50 budget.

## Immediate Actions
1. Open Billing > Cost breakdown in GCP console
2. Identify the top cost driver (likely BigQuery, Cloud Run, or Storage)
3. For BigQuery:
   - Check for full-table scans: SELECT * without WHERE on large tables
   - Check if partition pruning is working on experiments.backtest_predictions
4. For Cloud Run:
   - Check if min-instances was accidentally set > 0

## Prevention
- All BigQuery queries must use season as a partition filter on backtest_predictions
- API queries are reviewed for cost before shipping
```

---

## Step 7 — IaC in Version Control (Continuous)

**Deliverable:** Everything provisioned in Steps 1–6 is declared in `05-DEVOPS/infra/terraform/` and reproducible from a clean checkout.

Per ADR-010: Terraform with GCS backend. See ADR-010 in `docs/DECISIONS.md` for full rationale.

### Bootstrap (one-time manual step, documented in runbook)

These resources must exist before `terraform init` can run — create them once manually:

```bash
# Create Terraform state bucket (versioned, locked to prevent concurrent applies)
gsutil mb -l us-central1 gs://nfl-model-471509-tfstate
gsutil versioning set on gs://nfl-model-471509-tfstate

# Create Terraform service account for CI
gcloud iam service-accounts create terraform-ci \
  --description="Used by GitHub Actions to apply Terraform" \
  --display-name="Terraform CI"

# Grant it the necessary roles (broad for infra management — this SA is CI-only)
gcloud projects add-iam-policy-binding nfl-model-471509 \
  --member="serviceAccount:terraform-ci@nfl-model-471509.iam.gserviceaccount.com" \
  --role="roles/editor"
gcloud projects add-iam-policy-binding nfl-model-471509 \
  --member="serviceAccount:terraform-ci@nfl-model-471509.iam.gserviceaccount.com" \
  --role="roles/iam.securityAdmin"
```

Document this in `05-DEVOPS/runbooks/terraform-bootstrap.md`.

### Terraform File Layout

```
05-DEVOPS/infra/terraform/
├── main.tf          # provider, backend config
├── variables.tf     # project_id, region, alert_email
├── outputs.tf       # api_url, frontend_url
├── iam.tf           # service accounts + role bindings
├── cloud_run.tf     # nfl-backend-api Cloud Run service
├── jobs.tf          # all Cloud Run Jobs
├── scheduler.tf     # all Cloud Scheduler entries
├── storage.tf       # upload bucket + frontend bucket + CDN
├── secrets.tf       # Secret Manager secrets (values managed manually, not in TF)
├── monitoring.tf    # alert policies + notification channels
└── budget.tf        # billing budget
```

### Key Terraform Constraints

- **Secret values are NOT in Terraform.** `secrets.tf` creates the secret resource; values are set via `gcloud secrets versions add` outside of TF. This prevents secrets appearing in `terraform.tfstate`.
- **Container images are NOT pinned in Terraform.** The CI pipeline tags images with git SHA and updates the Cloud Run service. Terraform manages the service config; CI manages the image.
- **`terraform plan` runs on every PR** (via `05-DEVOPS/ci/tf-plan.yml`). `terraform apply` runs on merge to main.

---

## Summary: Agent Deliverables Checklist

Work through these in order. Check each off in `00-PROJECT-LEAD/PHASE3_STATUS.md` as you complete them.

| # | Deliverable | Unblocks |
|---|-------------|---------|
| 1a | `nfl-backend-api` Cloud Run service deployed and healthy | TESTING-QA, BACKEND-API (new endpoint), FRONTEND (type regen) |
| 1b | CI pipeline for API deploys wired | All future API changes |
| 2a | FRONTEND static site deployed, loads at HTTPS URL | FRONTEND QA |
| 2b | CI pipeline for frontend deploys wired | All future frontend changes |
| 3a | Experiment runner packaged as Cloud Run Job | End-to-end experiment runs |
| 3b | BACKEND-API stub replaced with real Cloud Run Job trigger | End-to-end experiment runs |
| 3c | Dataset upload background task swapped (can follow 3b) | Reliable dataset processing |
| 4 | DATA-PIPELINE Cloud Run Jobs + Cloud Scheduler wired | Weekly data refresh |
| 5 | Production refresh Cloud Scheduler wired (pending MODELING wrapper) | Weekly prediction refresh |
| 6 | Monitoring, alerting, budgets, runbooks | Production ops |
| 7 | All of the above in Terraform, `terraform apply` reproducible | IaC compliance |

**Handoff signal:** When Step 1a is complete, post the API URL to `00-PROJECT-LEAD/PHASE3_STATUS.md` and notify PROJECT-LEAD. That is the trigger to engage TESTING-QA and BACKEND-API in parallel.

---

## Open Questions / Dependencies on Other Agents

| Question | Owner | Needed for |
|----------|-------|------------|
| Does `--start-at 1` correctly scope a gameday refresh (schedules + curated.games only)? | DATA-PIPELINE | Step 4 |
| What Python/R dependencies does `run_pipeline.py` need in the container? Confirm `requirements.txt` or `pyproject.toml` is complete | DATA-PIPELINE | Step 4 |
| Write `run_production_refresh.py` wrapper | MODELING | Step 5 |

Raise these with PROJECT-LEAD if the relevant agent is not yet engaged.
