# Runbook: Cost Spike

## Symptoms

Cloud Billing alert: Monthly spend at 50%, 80%, or 100% of the $50 budget.

## Immediate Actions

1. **Open the cost breakdown:**
   - Go to: https://console.cloud.google.com/billing/nfl-model-471509
   - Click "Costs by SKU" or "Cost Analysis"

2. **Identify the top cost driver(s):**
   ```bash
   gcloud billing accounts list
   # Note the ACCOUNT_ID, then:
   gcloud beta billing projects link nfl-model-471509 --billing-account=<ACCOUNT_ID>
   ```

3. **Check the project's monthly forecast:**
   - https://console.cloud.google.com/billing/nfl-model-471509/cost-analysis

## Common Causes & Fixes

### BigQuery Query Costs (Usual Suspect #1)

BigQuery charges per TB of data scanned (not queried).

#### Identify expensive queries:

```bash
# Check for recent high-cost queries
gcloud bq query --use_legacy_sql=false <<EOF
SELECT
  user_email,
  query,
  total_bytes_processed / 1e12 as TB_scanned,
  total_slot_ms,
  creation_time
FROM \`nfl-model-471509.region-us.INFORMATION_SCHEMA.JOBS_BY_PROJECT\`
WHERE creation_time >= CURRENT_TIMESTAMP() - INTERVAL 7 DAY
  AND total_bytes_processed > 1e11  -- > 100GB
ORDER BY total_bytes_processed DESC
LIMIT 20
EOF
```

#### Common issues:

- **Full-table scan without partition filter:**
  - ❌ Bad: `SELECT * FROM experiments.backtest_predictions`
  - ✅ Good: `SELECT * FROM experiments.backtest_predictions WHERE season = 2024`

- **Missing partition filters on large tables:**
  - `experiments.backtest_predictions` is partitioned on `season`
  - Always include `season = <year>` in WHERE clause

- **Inefficient joins:**
  - Joining a small table to a large table can trigger full table scans
  - Use `CROSS JOIN` only when necessary

#### Cost limit per service account:

Set a per-query cost limit on the nfl-api-sa service account:

```bash
# Get the nfl-api-sa service account email
api_sa="nfl-api-sa@nfl-model-471509.iam.gserviceaccount.com"

# Set a per-query cost limit (this is advisory, not enforced by BigQuery)
# Limits must be set via the Google Cloud Console or Terraform
# See: https://cloud.google.com/bigquery/quotas
```

### Cloud Run Costs (If min-instances > 0)

Cloud Run charges per vCPU-second when a service is running. If min-instances is > 0, the service is always on.

#### Check resource allocation:

```bash
gcloud run services describe nfl-backend-api --region=us-central1 --format='value(template.spec.containers[0].resources)'
```

#### Fix:

- Ensure min-instances is 0 (scale-to-zero) for solo projects:
  ```bash
  gcloud run services update nfl-backend-api \
    --region=us-central1 \
    --min-instances=0
  ```

- Or check Terraform configuration in `05-DEVOPS/infra/terraform/cloud_run.tf`:
  ```hcl
  annotations = {
    "autoscaling.knative.dev/min-scale" = "0"  # ← should be 0
  }
  ```

### Cloud Storage Costs (Unlikely)

Cloud Storage is cheap ($0.02/GB/month in us-central1 for STANDARD class), but check for:

1. **Excessive egress:** If data is being served to the internet, check bandwidth logs
2. **Unnecessary versioning:** Check if bucket versioning is enabled and keeping old versions

```bash
# Check bucket size
gsutil du -s gs://nfl-model-471509-uploads
gsutil du -s gs://nfl-frontend-nfl-model-471509

# Check lifecycle policies
gsutil lifecycle get gs://nfl-model-471509-uploads
```

### Scheduled Cloud Run Job Costs

Cloud Run Jobs charge per vCPU-second of runtime. Check:

1. **Job frequency:** Is a job running too often?
   - Data pipeline should run weekly, not daily
   - Check Cloud Scheduler:
     ```bash
     gcloud scheduler jobs list --location=us-central1
     ```

2. **Job resource allocation:** Is a job using more resources than needed?
   ```bash
   gcloud run jobs describe nfl-pipeline-full --region=us-central1
   ```

## Prevention

### 1. API Queries

Always use partition filters on `experiments.backtest_predictions`:

```sql
-- ✅ Good
SELECT * FROM experiments.backtest_predictions
WHERE season = 2024
  AND home_team = 'Kansas City Chiefs'

-- ❌ Bad
SELECT * FROM experiments.backtest_predictions
WHERE home_team = 'Kansas City Chiefs'  -- No partition filter = full table scan
```

### 2. Cost Monitoring

Enable detailed cost breakdown:

- https://console.cloud.google.com/billing/nfl-model-471509/exports
- Set up BigQuery export of billing data for custom analysis

### 3. Quota Alerts

Check current quota usage:

```bash
# BigQuery query quota
gcloud beta bq show --project_id=nfl-model-471509 | grep quota

# Or review in the console:
# https://console.cloud.google.com/bigquery/quotas
```

### 4. Budget Tracking

The Terraform configuration includes a $50/month budget with alerts at 50%, 80%, and 100%. Review budget status:

- https://console.cloud.google.com/billing/nfl-model-471509/budgets

## Cost Breakdown Targets (for reference)

A healthy monthly breakdown (at $20/month):

| Service | Cost | Notes |
|---------|------|-------|
| BigQuery | $15 | ~50 GB scanned at $6.25/TB |
| Cloud Run | $3 | ~100K requests, cold starts |
| Cloud Storage | <$1 | Uploads + frontend static files |
| Cloud Scheduler | <$1 | ~4 scheduled jobs |
| Other (Cloud Monitoring, etc.) | <$1 | |

If costs exceed these targets, investigate the anomaly.

## Escalation

Solo project. Document the cause and fix in `05-DEVOPS/INCIDENTS.md`:

- Date and spike amount
- Root cause (query cost, misconfigured job, etc.)
- Fix applied
- Prevention steps

No external escalation unless:
- A legitimate feature or scaling need justifies the cost increase (and budget should be raised)
- An attacker has gained access and is burning budget (unlikely for a GCP project with service account protections)
