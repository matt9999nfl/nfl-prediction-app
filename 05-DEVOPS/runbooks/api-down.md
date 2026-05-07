# Runbook: API Down / High 5xx Rate

## Symptoms

Cloud Monitoring alert: `nfl-backend-api` 5xx rate > 5% over 5 minutes, OR manual reports of API errors.

## Immediate Actions

1. **Check API health:**
   ```bash
   gcloud run services logs read nfl-backend-api --region=us-central1 --limit=50
   ```

2. **Identify the current deployed revision:**
   ```bash
   gcloud run services describe nfl-backend-api --region=us-central1 --format="value(status.latestReadyRevisionName)"
   ```

3. **Check for recent deployments:**
   ```bash
   gcloud run revisions list --service=nfl-backend-api --region=us-central1 --limit=5
   ```

4. **Verify the service is receiving traffic:**
   ```bash
   gcloud run services describe nfl-backend-api --region=us-central1 --format="value(status.traffic[0].percent)"
   ```

## Common Causes & Fixes

### Bad Deploy (Most Common)

If the 5xx rate started immediately after a deployment:

```bash
# Get the previous revision name
prev_revision=$(gcloud run revisions list --service=nfl-backend-api --region=us-central1 --format='value(name)' | head -2 | tail -1)

# Roll back traffic to the previous revision
gcloud run services update-traffic nfl-backend-api --region=us-central1 --to-revisions=$prev_revision=100
```

### BigQuery Quota Exceeded

Check BigQuery quotas:
- https://console.cloud.google.com/bigquery/quotas

If slot quota is exceeded, the nfl-api-sa service account cannot execute queries. Contact the project owner to increase BigQuery slots.

### Secret Rotation or Expired Keys

Verify Secret Manager versions are current:

```bash
gcloud secrets versions list ANTHROPIC_API_KEY
gcloud secrets versions list OWNER_API_KEY
```

If versions are very old or secret values have changed, update them:

```bash
gcloud secrets versions add ANTHROPIC_API_KEY --data-file=-  # Enter new key, then Ctrl+D
gcloud secrets versions add OWNER_API_KEY --data-file=-
```

Then redeploy the API:

```bash
gcloud run deploy nfl-backend-api --region=us-central1 --no-traffic
# Run smoke tests, then shift traffic
gcloud run services update-traffic nfl-backend-api --region=us-central1 --to-latest
```

### Cold Start Timeout (Rare)

If the error logs show timeouts during the startup phase, and `min-instances` is 0 (scale-to-zero), increase min-instances temporarily:

```bash
gcloud run services update nfl-backend-api --region=us-central1 --min-instances=1
```

Monitor for a few minutes. If errors continue, rollback as above.

## Verification

After any fix, verify:

1. Smoke test the API:
   ```bash
   url=$(gcloud run services describe nfl-backend-api --region=us-central1 --format='value(status.url)')
   curl "$url/health"
   ```

2. Check 5xx rate in Cloud Monitoring:
   - https://console.cloud.google.com/monitoring/dashboards

3. Watch logs for continued errors:
   ```bash
   gcloud run services logs read nfl-backend-api --region=us-central1 --limit=20 --follow
   ```

## Escalation

This is a solo project. Log the incident in `05-DEVOPS/INCIDENTS.md` with:
- Date and duration
- Root cause
- Fix applied
- Prevention steps

No external escalation needed unless the issue persists > 30 minutes.

## Metrics to Monitor Post-Fix

- **5xx rate** (should drop to < 1% immediately)
- **Request latency** (p50, p99 should be stable)
- **Cold start rate** (if previously spiked)

Track in the incident log.
