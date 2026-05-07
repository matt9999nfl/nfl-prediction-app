# DEVOPS — Phase 3 Infrastructure

This directory contains all infrastructure-as-code, CI/CD pipelines, monitoring, and runbooks for the NFL Prediction App Phase 3 production deployment.

## Structure

```
05-DEVOPS/
├── README.md                      ← You are here
├── instructions.md                ← Role, principles, SOP
├── INCIDENTS.md                   ← Incident log
│
├── infra/
│   └── terraform/
│       ├── main.tf                ← Provider + backend config
│       ├── variables.tf            ← Input variables
│       ├── outputs.tf              ← Outputs (API URL, etc.)
│       ├── iam.tf                  ← Service accounts + role bindings
│       ├── secrets.tf              ← Secret Manager resources
│       ├── cloud_run.tf            ← API Cloud Run service
│       ├── jobs.tf                 ← Cloud Run Jobs (runner, pipeline, refresh)
│       ├── scheduler.tf            ← Cloud Scheduler entries
│       ├── storage.tf              ← Cloud Storage buckets + CDN
│       └── monitoring.tf           ← Alert policies, notification channels
│
├── ci/
│   ├── api-deploy.yml             ← GitHub Actions: deploy BACKEND-API
│   ├── frontend-deploy.yml        ← GitHub Actions: deploy FRONTEND
│   └── tf-plan.yml                ← GitHub Actions: terraform plan on PR
│
├── monitoring/
│   └── [dashboards/]              ← [Future: Cloud Monitoring dashboards]
│
└── runbooks/
    ├── terraform-bootstrap.md      ← One-time GCP setup
    ├── api-down.md                 ← Runbook: API 5xx errors
    ├── pipeline-failure.md         ← Runbook: scheduled job failures
    └── cost-spike.md               ← Runbook: budget alerts
```

## Deployment Readiness

### ✅ Completed (Infrastructure Code)

1. **Terraform modules** — all infrastructure declared, ready to provision:
   - Cloud Run service (nfl-backend-api)
   - Cloud Run Jobs (experiment runner, data pipeline, production refresh)
   - Cloud Scheduler entries (weekly ingest, gameday refresh, production refresh)
   - Cloud Storage buckets (uploads, frontend)
   - Cloud CDN + Load Balancer (frontend)
   - IAM service accounts (api-sa, runner-sa, pipeline-sa, terraform-ci)
   - Secret Manager secrets (ANTHROPIC_API_KEY, OWNER_API_KEY)
   - Cloud Monitoring alerts (API 5xx rate, job failures)

2. **CI/CD pipelines** — GitHub Actions workflows configured:
   - `api-deploy.yml` — build, push, deploy to Cloud Run, smoke test, traffic shift
   - `frontend-deploy.yml` — build, upload to Cloud Storage, cache headers, CDN invalidate
   - `tf-plan.yml` — Terraform plan on PR, comment with changes

3. **Code changes** — BACKEND-API stub replaced with real Cloud Run Job trigger:
   - `03-BACKEND-API/app/queries/experiments.py` — `trigger_experiment_runner()` function
   - `03-BACKEND-API/app/routers/experiments.py` — router call updated to use real function
   - `03-BACKEND-API/pyproject.toml` — added `google-auth`, `requests` dependencies

4. **Container images** — Dockerfiles for batch jobs:
   - `01-DATA-PIPELINE/Dockerfile.job` — data pipeline container
   - `02-MODELING/Dockerfile.job` — experiment runner container
   - `01-DATA-PIPELINE/scripts/run_pipeline_job.py` — wrapper for PIPELINE_MODE env var

5. **Monitoring & runbooks**:
   - 4 runbooks with troubleshooting steps, commands, and escalation paths
   - Alert policies (API 5xx rate, job failures)
   - Email notification channel
   - INCIDENTS.md for tracking

### ⏳ Pending Execution (Manual / Agent Steps)

1. **Bootstrap** (one-time manual):
   ```bash
   # See runbooks/terraform-bootstrap.md for full commands
   gsutil mb -l us-central1 gs://nfl-model-471509-tfstate
   gsutil versioning set on gs://nfl-model-471509-tfstate
   gcloud iam service-accounts create terraform-ci ...
   # [Set up Workload Identity Federation or SA key in GitHub Actions]
   ```

2. **Terraform apply** (CI or local):
   ```bash
   cd 05-DEVOPS/infra/terraform
   terraform init
   terraform plan
   terraform apply
   ```
   This provisions:
   - Service accounts and IAM roles
   - Secret Manager secrets (values must be added manually via gcloud after apply)
   - Cloud Run service + Jobs
   - Cloud Scheduler entries
   - Cloud Storage buckets + CDN
   - Monitoring alerts

3. **Populate secrets** (manual):
   ```bash
   gcloud secrets versions add ANTHROPIC_API_KEY --data-file=-  # Paste key, Ctrl+D
   gcloud secrets versions add OWNER_API_KEY --data-file=-      # Paste key, Ctrl+D
   ```

4. **Build and push container images** (CI will do this on push):
   ```bash
   docker build --build-arg GIT_COMMIT=$(git rev-parse --short HEAD) \
     -t gcr.io/nfl-model-471509/nfl-backend-api:latest \
     03-BACKEND-API/
   docker push gcr.io/nfl-model-471509/nfl-backend-api:latest
   # [Similar for nfl-data-pipeline and nfl-experiment-runner]
   ```

5. **Deploy API** (CI will do this when 03-BACKEND-API/* changes):
   - GitHub Actions pushes image to GCR
   - Deploys to Cloud Run with traffic=0%
   - Smoke tests
   - Shifts traffic to 100%

6. **MODELING deliverable** (needed for Step 5 to work):
   - Implement `02-MODELING/backtests/run_production_refresh.py`
   - Must query `platform.experiment_configs WHERE gate_passed = true`
   - Fire Cloud Run Job executions for each experiment

## Next Steps for PROJECT-LEAD

### Immediate (to unblock TESTING-QA, BACKEND-API, FRONTEND)

1. **Bootstrap infrastructure** — run the commands in `05-DEVOPS/runbooks/terraform-bootstrap.md`
2. **Run terraform apply** — provisions all GCP resources
3. **Set secrets** — add ANTHROPIC_API_KEY and OWNER_API_KEY to Secret Manager
4. **Test deployment** — verify Cloud Run service is healthy:
   ```bash
   gcloud run services logs read nfl-backend-api --limit=20
   curl https://<api-url>/health
   ```
5. **Update PHASE3_STATUS.md** — post the deployed API URL when ready

### Short-term (after Step 1 is live)

1. **MODELING** — implement `run_production_refresh.py` (stub is in place)
2. **DATA-PIPELINE** — confirm `--start-at 1` syntax for gameday refresh
3. **TESTING-QA** — integration tests using deployed API URL
4. **FRONTEND** — type generation against live API, test deployment

### Long-term (operational)

1. **Monitor alerts** — watch for 5xx errors, job failures, cost spikes
2. **Follow runbooks** — use the incident response steps documented
3. **Track incidents** — log in `05-DEVOPS/INCIDENTS.md` for postmortems
4. **Iterate on Terraform** — all changes through version control and CI

## Important Notes

### Principle: Everything in Terraform

- No manual `gcloud` commands in production (except secrets setup)
- All resource changes must go through `05-DEVOPS/infra/terraform/`
- Every PR triggers `terraform plan`, every merge triggers `terraform apply`
- Document manual changes in INCIDENTS.md with a note to fix in Terraform

### Principle: Scale-to-Zero

- Cloud Run service: `min-instances=0` (no idle cost)
- No persistent VMs or dedicated resources
- Cloud Run Jobs scale to zero between runs

### Principle: Least-Privilege IAM

- Each service account has only the roles it needs
- API can read BigQuery; cannot write datasets
- Pipeline can write raw/curated; cannot read experiments
- Runner can trigger jobs and write experiments

### Principle: Secrets in Secret Manager

- Never in `.env`, `terraform.tfvars`, or git
- Terraform creates the secret resources; values added manually
- Service accounts granted `secretmanager.secretAccessor` only

## Monitoring & Alerting

All alerts go to `matt.lilley4@gmail.com`. Runbooks provide step-by-step incident response.

**Active alerts:**
- Cloud Run API 5xx rate > 5% over 5 minutes → api-down.md
- Cloud Run Job execution failed → pipeline-failure.md
- Monthly budget at 50%, 80%, 100% → cost-spike.md

**Dashboard:** https://console.cloud.google.com/monitoring/dashboards

## Rollback

Any service change can be rolled back in seconds:

```bash
# Get previous revision
prev=$(gcloud run revisions list --service=nfl-backend-api --limit=2 --format='value(name)' | tail -1)

# Shift traffic back
gcloud run services update-traffic nfl-backend-api --to-revisions=$prev=100
```

For infrastructure, revert the Terraform PR and reapply.

## Questions / Blockers

If you encounter issues:

1. Check the relevant runbook (`05-DEVOPS/runbooks/*.md`)
2. Review logs in Cloud Logging
3. Verify IAM permissions for the service account
4. Check Terraform state: `terraform show`

Log any blockers in GitHub issues or INCIDENTS.md.
