# Phase 5 Status — Polish Sprint

**Owner:** PROJECT-LEAD  
**Phase start:** 2026-05-23  
**Updated:** 2026-05-23 (Agent run complete — code changes written, deployment pending)  
**Status:** 🟡 Code complete — awaiting deployment and smoke tests

This file is updated by agents as they complete deliverables. PROJECT-LEAD reads it to track parallel work and decide when the sprint is complete. For full rationale and fix descriptions, see `ROADMAP.md §Phase 5`.

---

## Phase 5 Tracks

| Track | Lead Agent | Items | Status |
|-------|------------|-------|--------|
| BACKEND-API | BACKEND-API | P5-03, P5-05 (query), P5-06, P5-07 | 🟡 Code written — not deployed |
| FRONTEND | FRONTEND | P5-01, P5-02, P5-04, P5-05 (display), P5-08 | 🟡 Code written — not deployed |

---

## BACKEND-API Track

**Spec:** `BACKEND_API_SPEC_PHASE5.md`

| # | Item | Severity | Status | Notes |
|---|------|----------|--------|-------|
| P5-07 | Feature importance 404 | 🟠 High | 🟡 Code done | Route handler exists in `app/routers/experiments.py` (line 499). Router registered in `app/main.py`. Not yet deployed — live endpoint still returns 404. |
| P5-06 | Missing `per_fold` in `latest_run` | 🟠 High | 🟡 Code done | `get_per_fold_results()` added to `app/queries/experiments.py`. Wired into experiment detail handler — fetches latest_run_id then per-season fold aggregates. Not yet deployed. |
| P5-03 | Stuck dataset + delete endpoint | 🟠 High | 🟡 Code done | `_reconcile_stuck_uploading()` added to `app/queries/datasets.py` — flips status to error for datasets in `uploading` >30 min. Called in both `list_datasets()` and `get_dataset()`. `DELETE /api/v1/datasets/{id}` endpoint added to `app/routers/datasets.py` with `delete_dataset_registry_only()` + GCS file delete. Not yet deployed. |
| P5-05q | Dashboard 0 completed experiments (query) | 🟡 Medium | 🟡 Code done | `list_experiments()` in `app/queries/experiments.py` now treats `status='complete'` as "has at least one run in backtest_runs" rather than requiring the status column to match. Smart fix — accounts for cases where runner doesn't update status. Not yet deployed. |

**Deployment required:** `gcloud run deploy` (or CI/CD pipeline) to push updated image to `nfl-backend-api-rmaehdhzhq-uc.a.run.app`. After deploy, smoke test all four endpoints against live URL.

---

## FRONTEND Track

**Spec:** `FRONTEND_SPEC_PHASE5.md`

| # | Item | Severity | Status | Notes |
|---|------|----------|--------|-------|
| P5-01 | Routes swapped | 🔴 Critical | 🟡 Code done | `App.tsx` now maps `/experiments` → `ModelPage` (the experiments list, formerly at `/model`). `/model` redirects to `/experiments`. Nav link `to="/experiments"` with label "Experiments" is correct. `dist-new/` built but not deployed to CDN. |
| P5-02 | Checkbox triggers back navigation | 🟠 High | 🟡 Code done | Back/Next buttons moved to a `fixed bottom-0 left-0 right-0 z-50` footer outside the scrollable card. `pb-20` added to content area to prevent overlap. Not deployed. |
| P5-04 | `end_season` defaults to 2024 | 🟡 Medium | 🟡 Code done | `useState(2025)` in `ExperimentsNewPage.tsx` line 92. One-line fix, correct. Not deployed. |
| P5-05d | Dashboard 0 completed experiments (display) | 🟡 Medium | 🟡 Code done | `DashboardPage.tsx` fetches `useExperiments({ status: 'complete' })` and displays `.length`. Pairs correctly with backend P5-05q fix. Gated on backend deploy. |
| P5-08 | Feature mirroring not communicated | 🟡 Medium | 🟡 Code done | Count display updated to `"N selected · 2N features used in model (home + away mirrors)"`. Static explanatory note added below feature list. Not deployed. |
| P5-06d | Per-fold chart (verify) | 🟠 High | ⏳ Blocked | Pending BACKEND-API P5-06 deploy. Component already built in Phase 4. Verification step only. |
| P5-07d | Feature importance panel (verify) | 🟠 High | ⏳ Blocked | Pending BACKEND-API P5-07 deploy. Component already built in Phase 4. Verification step only. |

**Deployment required:** `npm run build` → push `dist/` to GCS bucket → invalidate CDN cache. `dist-new/` was built by the agent but is separate from the live `dist/` — need to confirm which is deployed.

---

## Integration Dependencies

| Frontend item | Blocked on |
|---------------|-----------|
| P5-05d (display) | BACKEND-API P5-05q deployed |
| P5-06d (verify) | BACKEND-API P5-06 deployed |
| P5-07d (verify) | BACKEND-API P5-07 deployed |

P5-01, P5-02, P5-04, and P5-08 have no backend dependencies — can deploy frontend independently now.

---

## Outstanding Work (Next Session)

1. **BACKEND-API: Deploy to Cloud Run.** All four code changes are complete. Single deploy unblocks P5-07, P5-06, P5-03, P5-05q simultaneously.
2. **FRONTEND: Resolve dist-new vs dist confusion, deploy to CDN.** Agent built to `dist-new/` but live site serves from `dist/`. Confirm correct directory and deploy.
3. **FRONTEND: Smoke test P5-01 at live URL.** Navigate to `http://34.49.20.115/experiments` and confirm experiments list renders (not the dashboard).
4. **FRONTEND: Verify P5-06d and P5-07d** after backend deploy — confirm per-fold chart and feature importance panel render.

---

## Phase 5 Complete When

- [ ] All routes work: `/experiments` → experiment list, `/model` → redirects correctly, direct URL nav for all routes
- [ ] A new user can complete the full experiment wizard without being kicked back to a previous step
- [ ] Stuck datasets (uploading > 30 min) show error state with a delete button
- [ ] `DELETE /api/v1/datasets/:id` works in production
- [ ] `end_season` defaults to 2025 in the wizard
- [ ] Dashboard completed experiments count reflects reality (non-zero)
- [ ] Per-fold chart shows all folds across all seasons (not just most recent fold)
- [ ] Feature importance panel renders on completed experiment results pages
- [ ] Wizard Step 3 communicates home/away feature mirroring
- [ ] All changes deployed and smoke-tested against live URLs

---

## Incidents

*None open.*
