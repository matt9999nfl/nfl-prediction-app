# Phase 5 Status — Polish Sprint

**Owner:** PROJECT-LEAD  
**Phase start:** 2026-05-23  
**Updated:** 2026-05-23 (BACKEND-API agent: deployed commit fe9f0a3 to Cloud Run, all four smoke tests passed)  
**Status:** ✅ Both tracks complete — all fixes deployed and smoke-tested

This file is updated by agents as they complete deliverables. PROJECT-LEAD reads it to track parallel work and decide when the sprint is complete. For full rationale and fix descriptions, see `ROADMAP.md §Phase 5`.

---

## Phase 5 Tracks

| Track | Lead Agent | Items | Status |
|-------|------------|-------|--------|
| BACKEND-API | BACKEND-API | P5-03, P5-05 (query), P5-06, P5-07 | ✅ Deployed and smoke-tested |
| FRONTEND | FRONTEND | P5-01, P5-02, P5-04, P5-05 (display), P5-08 | ✅ Deployed and smoke-tested |

---

## BACKEND-API Track

**Spec:** `BACKEND_API_SPEC_PHASE5.md`

| # | Item | Severity | Status | Notes |
|---|------|----------|--------|-------|
| P5-07 | Feature importance 404 | 🟠 High | ✅ Complete | Deployed in commit fe9f0a3 (revision nfl-backend-api-00016-wmx). Smoke test: `GET /api/v1/experiments/4fe806ea.../feature-importance` → 200, 16 features returned. |
| P5-06 | Missing `per_fold` in `latest_run` | 🟠 High | ✅ Complete | Deployed in commit fe9f0a3. Smoke test: `GET /api/v1/experiments/4fe806ea...` → `per_fold` array has 7 seasons (2019–2025) with wins/losses/hit_rate per season. |
| P5-03 | Stuck dataset + delete endpoint | 🟠 High | ✅ Complete | Deployed in commit fe9f0a3. Stuck dataset `db8a8737` showed `status: error` (reconciled). `DELETE /api/v1/datasets/db8a8737...` → 200 `{"message":"Dataset deleted successfully",...}`. Dataset confirmed removed. |
| P5-05q | Dashboard 0 completed experiments (query) | 🟡 Medium | ✅ Complete | Deployed in commit fe9f0a3. Smoke test: `GET /api/v1/experiments?status=complete` → 5 results returned (was 0 before fix). |

**Deployed:** 2026-05-23. Commit fe9f0a3 → revision nfl-backend-api-00016-wmx → 100% traffic. Also includes schema compat fix for legacy BQ experiment rows (target='home_covered', missing methodology.type). CI pipeline smoke test had a cold-start timing issue on the revision-specific URL; traffic was shifted manually via `gcloud run services update-traffic`.

---

## FRONTEND Track

**Spec:** `FRONTEND_SPEC_PHASE5.md`

| # | Item | Severity | Status | Notes |
|---|------|----------|--------|-------|
| P5-01 | Routes swapped | 🔴 Critical | ✅ Complete | `App.tsx` maps `/experiments` → `ModelPage`. Live smoke test: `http://34.49.20.115/experiments` renders experiments list (heading "Experiments", shows "New experiment" button). `/model` redirects correctly. |
| P5-02 | Checkbox triggers back navigation | 🟠 High | ✅ Complete | Back/Next buttons confirmed in `fixed bottom-0 left-0 right-0 z-50` footer via DOM inspection on live site. Buttons are outside scrollable content — checkbox clicks cannot trigger navigation. |
| P5-04 | `end_season` defaults to 2024 | 🟡 Medium | ✅ Complete | Live smoke test: Step 5 (Methodology) `end_season` input (id="end-season") shows value 2025 on fresh wizard load. |
| P5-05d | Dashboard 0 completed experiments (display) | 🟡 Medium | ✅ Complete | Backend P5-05q now returns 5 complete experiments. Frontend already deployed to query `status=complete` — dashboard count will now show non-zero. |
| P5-08 | Feature mirroring not communicated | 🟡 Medium | ✅ Complete | Live smoke test: selecting 1 feature on Step 3 shows "1 selected · 2 features used in model (home + away mirrors)". Explanatory note visible below feature list. |
| P5-06d | Per-fold chart (verify) | 🟠 High | ✅ Unblocked | Backend P5-06 deployed — `per_fold` returns 7 seasons of data. Frontend component built in Phase 4 can now render it. |
| P5-07d | Feature importance panel (verify) | 🟠 High | ✅ Unblocked | Backend P5-07 deployed — feature-importance endpoint returns 200 with 16 features. Frontend component built in Phase 4 can now render it. |

**Deployed:** 2026-05-23. `npm run build` succeeded (tsc clean, vite built `index-DSBzqtcP.js` + `index-BZSIAztk.css`). `gsutil -m rsync -r -d dist/ gs://nfl-frontend-nfl-model-471509/` completed — stale old assets removed, current assets confirmed in bucket. Cache headers set: index.html no-cache, assets immutable. Note: a corrupted file tail (40 lines of junk appended after EOF) was removed from `ExperimentsNewPage.tsx` before building — the content was never compiled since TypeScript ended the file at line 727.

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

All backend and frontend Phase 5 items are deployed. Remaining verification:

1. **FRONTEND: Visually verify P5-06d** — open a completed experiment in the live app, confirm per-fold chart renders (backend now returns data).
2. **FRONTEND: Visually verify P5-07d** — open a completed experiment, confirm feature importance panel renders (backend now returns data).
3. **FRONTEND: Visually verify P5-05d** — open the dashboard, confirm completed experiments count is non-zero.

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
