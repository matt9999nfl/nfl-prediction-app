# Runbook: Pipeline / Job Failure

## Symptoms

Cloud Monitoring alert: Cloud Run Job completed with `result=failed`, OR scheduled job did not complete as expected.

## Immediate Actions

1. **Identify which job failed:**
   ```bash
   # List recent executions across all jobs
   gcloud run jobs executions list --region=us-central1 --limit=10 --filter="status:FAILED"
   
   # Or check a specific job:
   gcloud run jobs executions list --job=nfl-pipeline-full --region=us-central1
   gcloud run jobs executions list --job=nfl-experiment-runner --region=us-central1
   ```

2. **Inspect the failed execution:**
   ```bash
   # Replace EXECUTION_NAME with the actual execution ID
   gcloud run jobs executions describe EXECUTION_NAME --region=us-central1
   ```

3. **View detailed logs:**
   ```bash
   gcloud run jobs executions logs read EXECUTION_NAME --region=us-central1 --limit=100
   
   # Or use Cloud Logging directly:
   gcloud logging read 'resource.type="cloud_run_job" AND severity>=ERROR' --limit=50 --format=json
   ```

## Common Causes & Fixes

### Data Source Unavailable (Most Common)

If the error mentions `nflverse`, `nflfastR`, or external API failures:

```bash
# Check if nflverse data is available
curl -s https://api.github.com/repos/nflverse/nflfastR-data/contents | head -20
```

The nflfastR data may not be available yet on gameday. Check the release schedule:
- nflfastR typically publishes data within a few hours of game end
- Gameday jobs may run too early and find no new games

**Fix:** Adjust the Cloud Scheduler timing if gameday refresh is consistently running before data is available.

### BigQuery Write Quota Exceeded

Error messages like "Quota exceeded for quota metric 'BigQuery Write Throughput'":

```bash
# Check BigQuery quotas
gcloud beta bq show --project_id=nfl-model-471509 | grep -i quota

# Or check the project's quota page:
# https://console.cloud.google.com/bigquery/quotas
```

**Fix:** Wait for the quota to reset (typically hourly), or contact the project owner to increase quotas.

### Experiment Runner: Invalid Config

If the `nfl-experiment-runner` job fails with config-related errors:

```bash
# Check platform.experiment_configs for the failing experiment
gcloud bq query --use_legacy_sql=false <<EOF
SELECT experiment_id, status, error_message FROM \`nfl-model-471509.platform.experiment_configs\`
WHERE status = 'failed'
ORDER BY created_at DESC
LIMIT 5
EOF
```

**Fix:** Review the config in the dashboard or BigQuery, fix the invalid features/target, and re-run.

### Out of Memory (OOM)

Error logs show the task was killed due to memory limits:

```bash
# Check the current resource allocation
gcloud run jobs describe nfl-pipeline-full --region=us-central1 --format='value(template.spec.containers[0].resources)'
```

The job template specifies memory. If OOM is happening consistently:

```bash
# Update the job resource limits (e.g., increase from 4Gi to 8Gi)
gcloud run jobs update nfl-pipeline-full \
  --region=us-central1 \
  --memory=8Gi
```

Or update via Terraform in `05-DEVOPS/infra/terraform/jobs.tf` and reapply.

### Timeout

If the job takes longer than its configured timeout:

```bash
# Check the timeout for a job
gcloud run jobs describe nfl-pipeline-full --region=us-central1 --format='value(template.task_timeout)'
```

For the data pipeline, timeouts are:
- `nfl-pipeline-full`: 7200s (2 hours) — full season ingest
- `nfl-pipeline-gameday`: 1800s (30 min) — gameday refresh

If a job consistently times out, increase the timeout via Terraform or:

```bash
gcloud run jobs update nfl-pipeline-full \
  --region=us-central1 \
  --task-timeout=10800s
```

## Manual Re-run

If the failure is transient and the fix is identified, re-run manually:

```bash
# Trigger a job execution immediately
gcloud run jobs execute nfl-pipeline-full --region=us-central1

# Monitor the execution
gcloud run jobs executions list --job=nfl-pipeline-full --region=us-central1 --limit=1
```

## Verification

After a fix:

1. Check the re-run succeeded:
   ```bash
   gcloud run jobs executions describe EXECUTION_NAME --region=us-central1
   ```

2. Verify data was written to BigQuery:
   ```bash
   gcloud bq query --use_legacy_sql=false <<EOF
   SELECT COUNT(*) as row_count FROM \`nfl-model-471509.curated.games\`
   WHERE DATE(season_start) >= CURRENT_DATE() - 1
   EOF
   ```

## Escalation

This is a solo project. Log the incident in `05-DEVOPS/INCIDENTS.md` with:
- Date, time, and duration
- Which job failed
- Root cause
- Fix applied
- Whether manual re-run was needed

No external escalation unless:
- The external data source (nflverse) is permanently down (unlikely)
- GCP quotas need immediate increase

## Prevention

- **Gameday refresh timing:** Adjust Cloud Scheduler times if data arrives later than expected
- **Resource monitoring:** Watch pipeline job durations to predict future timeout needs
- **Error logging:** MODELING should ensure configs are validated before being saved to platform.experiment_configs
