# BACKEND-API Work Order — Phase 5 Polish Sprint

**Author:** PROJECT-LEAD  
**Date:** 2026-05-23  
**Status:** Ready for implementation  
**Tracking:** `PHASE5_STATUS.md`

---

## Context

This is the backend work order for the Phase 5 Polish Sprint. Four bugs are assigned to BACKEND-API. Two of them (P5-06 and P5-07) are the highest priority — they are the primary reason the experiment results page looks incomplete after a successful run.

The full issue catalogue is in `ROADMAP.md §Phase 5`. This document is the implementation contract — do not start writing code until you have read it fully.

**Deployment:** GCP project `nfl-model-471509`. Backend API running at `https://nfl-backend-api-rmaehdhzhq-uc.a.run.app`. FastAPI service on Cloud Run. BigQuery as sole data store.

---

## Priority Order

Implement in this order. P5-07 and P5-06 first — they are what the user sees on every completed experiment results page. P5-03 and P5-05 can follow.

| Priority | Item | Severity |
|----------|------|----------|
| 1 | P5-07 — feature-importance 404 | 🟠 High |
| 2 | P5-06 — missing per_fold in latest_run | 🟠 High |
| 3 | P5-03 — stuck dataset + delete endpoint | 🟠 High |
| 4 | P5-05 — dashboard 0 completed experiments | 🟡 Medium |

---

## P5-07 — Feature Importance 404 in Production

### Problem

`GET /api/v1/experiments/:id/feature-importance` returns `{"detail": "Not Found"}` in production. Confirmed via direct API call against `https://nfl-backend-api-rmaehdhzhq-uc.a.run.app`.

Phase 4 Track 3 item 3.2 marks this endpoint as ✅ Complete. The endpoint was built (`app/routers/` + `app/queries/experiments.py`) but is not reachable in the live service. The most likely cause is that the router is not included in `app/main.py`, or the current Cloud Run image predates the endpoint being added.

### Fix Required

1. **Verify router registration.** Open `app/main.py`. Confirm that the experiments router (or whichever router owns the `/experiments/:id/feature-importance` path) is imported and included via `app.include_router(...)`. If it is missing, add it.

2. **Verify the route exists in code.** Find the endpoint handler for `GET /api/v1/experiments/{experiment_id}/feature-importance`. Confirm it is present and returns `FeatureImportanceResponse` as specced in Phase 4. If the file exists but the route registration in `main.py` is missing, the code is fine — just wire it in.

3. **Redeploy.** Build and push the updated image. Redeploy the Cloud Run service. Confirm the endpoint returns HTTP 200 (or an appropriate non-404 response) against the live URL.

4. **Smoke test.** Call `GET /api/v1/experiments/<any_valid_id>/feature-importance` against the live service. Confirm it returns `{"run_id": "...", "features": [...]}` or `{"run_id": null, "features": []}` for an experiment with no run. A 404 after the fix is a regression — do not close this item until it returns a valid schema response.

### Expected Response Schema (from Phase 4 spec)

```json
{
  "run_id": "20260517_020202_0504ff",
  "features": [
    {"feature": "home_rolling_3wk_epa_trend", "importance": 0.0226},
    {"feature": "away_def_qb_hit_rate", "importance": 0.0224}
  ]
}
```

Features sorted descending by importance. `features` may be an empty array if no run exists.

---

## P5-06 — Missing `per_fold` Array in `GET /api/v1/experiments/:id`

### Problem

The `latest_run` object returned by `GET /api/v1/experiments/:id` is missing the `per_fold` array. Confirmed via direct API inspection. The live response for `latest_run` contains only:

```json
{
  "run_id": "...",
  "ats_hit_rate": 0.502,
  "n_games_evaluated": 272,
  "gate_passed": false,
  "notes": "..."
}
```

`per_fold` is absent. This causes the frontend to fall back to fetching `GET /api/v1/predictions?season=2024`, which returns only the most recent fold (272 games, 2024 season), instead of displaying all 7 folds across 1,828 games.

Phase 4 Track 3 item 3.1 marks this as ✅ Complete. As with P5-07, the code was written but is not present in the live deployment.

### Fix Required

1. **Verify the schema.** Open `app/schemas/experiments.py`. Confirm that `ExperimentDetailResponse` (or the equivalent) includes a `per_fold: List[FoldResult]` field where `FoldResult` has `season`, `wins`, `losses`, `pushes`, `hit_rate`, `n_games`. If the `FoldResult` schema is present but not wired into the response, wire it in.

2. **Verify the query.** Open `app/queries/experiments.py`. Confirm that `get_per_fold_results(experiment_id, run_id)` (or equivalent) exists and queries `experiments.backtest_predictions` grouped by season for `latest_run_id`. The grouping must produce per-season aggregates: `COUNT(*) AS n_games`, correct W/L/P tallies, and `hit_rate` computed as wins / (wins + losses).

3. **Verify the endpoint handler.** In the experiments router, confirm the `GET /api/v1/experiments/{experiment_id}` handler fetches `per_fold` results and populates the field. If the code is correct but the deployed image is stale, redeploy.

4. **Redeploy and smoke test.** After deploy, call `GET /api/v1/experiments/<id>` for an experiment with a completed run (use one of the Phase 4 validated experiments, e.g. run_id `20260517_020202_0504ff`). Confirm `latest_run.per_fold` is an array with ≥1 entry. Confirm each entry has all six fields. A response with `per_fold` missing or empty when predictions exist is a regression — do not close this item until fold-level data appears.

### Expected Response Fragment

```json
{
  "experiment_id": "...",
  "latest_run": {
    "run_id": "20260517_020202_0504ff",
    "ats_hit_rate": 0.502,
    "n_games_evaluated": 1582,
    "gate_passed": false,
    "notes": "...",
    "per_fold": [
      {"season": 2019, "wins": 120, "losses": 135, "pushes": 1, "hit_rate": 0.471, "n_games": 256},
      {"season": 2020, "wins": 118, "losses": 138, "pushes": 0, "hit_rate": 0.461, "n_games": 256}
    ]
  }
}
```

Folds must be sorted by `season` ascending.

---

## P5-03 — Dataset Stuck in `uploading` / No Delete Endpoint

### Problem

A dataset has been stuck in `uploading` status since May 9 because the Cloud Run processing job (`nfl-dataset-processor`) failed silently without updating `platform.datasets.status` to `error`. The frontend shows a permanent loading spinner with no error message, no retry option, and no way to remove the entry. There is no `DELETE /api/v1/datasets/:id` endpoint.

Two changes are required: (a) lazy timeout reconciliation in the GET endpoint, and (b) a DELETE endpoint.

### Fix Required — Part A: Lazy Timeout Reconciliation

In `GET /api/v1/datasets/:id` (and also in `GET /api/v1/datasets` list endpoint), add a pre-read reconciliation step:

1. Before returning a dataset whose `status == 'uploading'`, check whether `updated_at` (or `created_at` if no updated_at column exists) is more than **30 minutes** ago.
2. If so, update the row in `platform.datasets`:
   - Set `status = 'error'`
   - Set `error_message = 'Processing job did not complete within 30 minutes. The upload may have failed. Please delete this entry and try again.'`
   - Set `updated_at = CURRENT_TIMESTAMP()`
3. Return the updated record (with `status = 'error'`) in the response.

This is a lazy reconciliation — it fires on the next read request, not on a schedule. It is intentionally simple: no background job, no Cloud Scheduler dependency.

**BigQuery note:** BigQuery DML within a request handler requires a client call and may be slow. Keep the UPDATE query simple. Use `google.cloud.bigquery` directly (same pattern as other queries in `app/queries/`). Do not add a Pub/Sub dependency for this fix.

**Apply to both endpoints:** `GET /api/v1/datasets` (list) and `GET /api/v1/datasets/:id` (detail). The list endpoint should reconcile any stuck `uploading` datasets in the result set, not just the one being fetched.

### Fix Required — Part B: DELETE Endpoint

Add `DELETE /api/v1/datasets/{dataset_id}` with the following behaviour:

**Request:** `DELETE /api/v1/datasets/{dataset_id}`  
**Auth:** none required (same auth model as existing dataset endpoints)

**Success response (200):**
```json
{"message": "Dataset deleted successfully", "dataset_id": "<uuid>"}
```

**Not found response (404):**
```json
{"detail": "Dataset not found"}
```

**Implementation steps:**

1. Check that `dataset_id` exists in `platform.datasets`. Return 404 if not.
2. Delete the row from `platform.datasets`.
3. Optionally attempt to delete the source file from GCS (`uploads` bucket, path pattern `datasets/{dataset_id}.*`). If the GCS delete fails (e.g. file was never uploaded or was already cleaned up), log the error but do not fail the HTTP response — the database row is the canonical state.
4. Return 200 with the success message.

**Schema addition** (`app/schemas/datasets.py`):
```python
class DatasetDeleteResponse(BaseModel):
    message: str
    dataset_id: str
```

**Route registration:** add to the datasets router. Verify the router is included in `app/main.py` (same verification as P5-07).

**Do not** add cascading deletes of BigQuery user dataset tables in this sprint — that is scope creep. The delete removes the registry entry and the upload file only.

---

## P5-05 — Dashboard Shows 0 Completed Experiments

### Problem

The dashboard stat card showing "Completed Experiments" displays 0, despite multiple completed experiments existing in `experiments.backtest_runs` from Phase 4 work.

### Fix Required

1. **Locate the dashboard query.** Find the handler for `GET /api/v1/dashboard` (or whatever endpoint serves dashboard summary stats). If no dedicated dashboard endpoint exists and the frontend calls individual list endpoints, audit the experiments list query instead.

2. **Audit the completeness count.** The count of "completed" experiments must reflect experiments that have at least one run in `experiments.backtest_runs`. The likely bug is one of:
   - The query filters by `status = 'completed'` on `platform.experiments` but `status` is not being set when a run completes.
   - The query counts `backtest_runs` rows but joins incorrectly (e.g., on `experiment_id` but with a mismatched column name).
   - The query returns a correct number but it is being serialised under a field name the frontend doesn't expect.

3. **Fix the query.** The correct logic: count distinct `experiment_id` values in `experiments.backtest_runs` (or count experiments in `platform.experiments` where at least one run exists). Do not require `gate_passed = true` — a completed run with `gate_passed = false` is still a completed experiment.

4. **Confirm the API contract.** Check `docs/API_CONTRACTS.md` for the dashboard endpoint response shape. If the field name in the response doesn't match what the frontend expects, that is the bug — fix the response field name or update the contract and coordinate with FRONTEND. Do not silently rename fields.

5. **Redeploy and smoke test.** After deploy, call the dashboard endpoint directly. Confirm the completed experiments count is non-zero and matches the actual count of experiments with runs in BigQuery.

---

## Deployment Checklist

After implementing all four items, before marking Phase 5 BACKEND-API work complete:

- [ ] `GET /api/v1/experiments/:id/feature-importance` returns 200 with valid schema (not 404)
- [ ] `GET /api/v1/experiments/:id` includes `latest_run.per_fold` array with fold-level data
- [ ] `GET /api/v1/datasets/:id` for a dataset stuck in `uploading` >30 min returns `status: error`
- [ ] `DELETE /api/v1/datasets/:id` returns 200 for valid ID, 404 for missing ID
- [ ] Dashboard endpoint returns non-zero completed experiments count
- [ ] All new/changed routes are registered in `app/main.py`
- [ ] Unit/integration tests updated or added for each change
- [ ] Cloud Run service redeployed and smoke-tested against live URL
- [ ] `PHASE5_STATUS.md` updated with completion notes for each item

---

## What Not to Do

- Do not add new BigQuery tables or change existing table schemas — all data needed for these fixes already exists.
- Do not add a Cloud Scheduler job for dataset timeout reconciliation — lazy reconciliation in the GET handler is sufficient for this sprint.
- Do not implement cascading dataset deletes that remove user dataset BigQuery tables — delete the registry row and GCS file only.
- Do not rename existing response fields without coordinating with FRONTEND.
- Do not block on a full test suite rerun — smoke tests against the live URL are the acceptance criterion for this sprint.
