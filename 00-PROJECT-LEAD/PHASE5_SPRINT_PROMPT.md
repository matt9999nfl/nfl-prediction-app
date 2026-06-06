# Phase 5 Polish Sprint — Agent Kickoff Prompt

---

You are the PROJECT-LEAD agent for the NFL Prediction App. Read this brief fully before doing anything.

**Project overview**

GCP project `nfl-model-471509`. This is a self-service NFL prediction experimentation platform — users configure walk-forward backtest experiments through a React dashboard, run them via Cloud Run Jobs, and view results. The app is live and deployed:

- Frontend: http://34.49.20.115
- Backend API: https://nfl-backend-api-rmaehdhzhq-uc.a.run.app

The full architecture is in `docs/ARCHITECTURE.md`. Agent instructions are in each agent's folder.

**Why this sprint exists**

The app was walked through end-to-end by a real user on 2026-05-23 — create an experiment from scratch, run it, and navigate every page. Eight bugs were found across the frontend and backend. This sprint fixes them before the app is shown publicly as part of a YouTube series. The full plan is in `00-PROJECT-LEAD/ROADMAP.md §Phase 5`.

**The eight bugs to fix**

P5-01 (🔴 Critical — FRONTEND): React Router routes are swapped. Navigating directly to `/experiments` renders the Dashboard instead. Clicking the "Experiments" nav link routes to `/model`. Every shared link to the app lands on the wrong page.

P5-02 (🟠 High — FRONTEND): In the New Experiment wizard, Step 3 (Features), clicking checkboxes causes the wizard to jump backwards to Step 2. Reproducible when the page is not fully scrolled to show the Next/Back buttons. Likely a hit-target overlap between checkboxes and an underlying navigation element.

P5-03 (🟠 High — BACKEND-API + FRONTEND): A dataset has been stuck in `uploading` status since May 9 because its Cloud Run processing job failed silently without updating the status to `error`. The user sees a permanent loading spinner with no error message, no retry, and no way to delete the dataset. Two fixes needed: (a) lazy timeout reconciliation — any dataset in `uploading` for more than 30 minutes should flip to `error` on the next GET request, and (b) a `DELETE /api/v1/datasets/:id` endpoint so users can remove failed entries. Frontend needs to display the error state and a delete button.

P5-04 (🟡 Medium — FRONTEND): The Methodology step (Step 5) of the New Experiment wizard defaults `end_season` to 2024. The data pipeline has 2025 data. Default should be 2025.

P5-05 (🟡 Medium — FRONTEND + BACKEND-API): The dashboard shows 0 completed experiments despite experiments existing in the system. Audit the dashboard query and ensure the stat card renders the correct count.

P5-06 (🟠 High — BACKEND-API): The `latest_run` object in `GET /api/v1/experiments/:id` is missing the `per_fold` array. Confirmed via direct API inspection — `latest_run` only contains `run_id`, `ats_hit_rate`, `n_games_evaluated`, `gate_passed`, and `notes`. The frontend compensates by fetching `predictions?season=2024`, showing only the most recent fold (F6, 272 games) instead of all 7 folds across 1,828 games. Fix: add `per_fold: [{season, wins, losses, pushes, hit_rate, n_games}]` sourced from `experiments.backtest_predictions` grouped by season for `latest_run_id`. This was specced in Phase 4 Track 3 item 3.1 but is absent from the live deployment.

P5-07 (🟠 High — BACKEND-API): `GET /api/v1/experiments/:id/feature-importance` returns `{"detail": "Not Found"}` in production. Confirmed via direct API call. The endpoint was built in Phase 4 but is either not registered in `app/main.py` or not included in the current Cloud Run image. Feature importance panel never renders as a result. Fix: verify router registration and redeploy.

P5-08 (🟡 Medium — FRONTEND): The experiment wizard shows "5 selected" in Step 3 (Features), but the runner automatically mirrors each selected feature to its away-team counterpart — the actual run used 10 features. Users are surprised when results show double the features they thought they picked. Fix: add a note in the features step explaining the mirroring behaviour, e.g. "5 selected · 10 features used in model (home + away mirrors)".

**What to do**

Read `00-PROJECT-LEAD/ROADMAP.md` and `00-PROJECT-LEAD/PHASE4_STATUS.md` for full project context, then:

1. Write a spec for BACKEND-API covering P5-03, P5-05 (query), P5-06, and P5-07.
2. Write a spec for FRONTEND covering P5-01, P5-02, P5-04, P5-05 (display), and P5-08.
3. Engage both agents in parallel — the backend and frontend fixes are independent.
4. Create `00-PROJECT-LEAD/PHASE5_STATUS.md` to track progress, following the same format as `PHASE4_STATUS.md`.

P5-01 is the most urgent item within the FRONTEND spec — a broken router means every link shared with an audience lands on the wrong page. P5-06 and P5-07 are the most urgent for BACKEND-API — they're the reason the results page looks incomplete after a successful run.

Do not start writing code. Write the specs first, then hand to the agents.
