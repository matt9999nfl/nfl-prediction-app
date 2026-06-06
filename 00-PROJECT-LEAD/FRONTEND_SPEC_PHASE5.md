# FRONTEND Work Order — Phase 5 Polish Sprint

**Author:** PROJECT-LEAD  
**Date:** 2026-05-23  
**Status:** Ready for implementation  
**Tracking:** `PHASE5_STATUS.md`

---

## Context

This is the frontend work order for the Phase 5 Polish Sprint. Five bugs are assigned to FRONTEND. P5-01 is the most urgent — it is a broken router that means every externally shared link lands on the wrong page. Fix it first, before anything else.

The full issue catalogue is in `ROADMAP.md §Phase 5`. This document is the implementation contract — do not start writing code until you have read it fully.

**Deployment:** Frontend hosted via Cloud CDN + GCS at `http://34.49.20.115`. React + Vite + TypeScript. Backend API at `https://nfl-backend-api-rmaehdhzhq-uc.a.run.app`.

---

## Priority Order

| Priority | Item | Severity |
|----------|------|----------|
| 1 | P5-01 — routes swapped | 🔴 Critical |
| 2 | P5-02 — checkbox triggers back navigation | 🟠 High |
| 3 | P5-06/P5-07 display — per_fold chart + feature importance | *(backend-gated, prep only)* |
| 4 | P5-05 — dashboard 0 completed experiments | 🟡 Medium |
| 5 | P5-04 — end_season default 2024→2025 | 🟡 Medium |
| 6 | P5-08 — feature mirroring note | 🟡 Medium |

P5-05 display will resolve itself once the BACKEND-API fix for P5-05 is deployed. Verify it works after that deploy — do not build special frontend logic to compensate for the broken API.

---

## P5-01 — React Router Routes Swapped (CRITICAL)

### Problem

The route configuration is inverted. Navigating to `/experiments` renders the Dashboard component. The "Experiments" nav link routes to `/model`. Every link shared externally (e.g., the YouTube audience navigating to the app for the first time) lands on the wrong page.

### Fix Required

1. **Find the router config.** Locate the React Router configuration — likely `src/router.tsx`, `src/App.tsx`, or `src/routes/index.tsx`. Look for a `<Routes>` block or `createBrowserRouter(...)` call that maps paths to components.

2. **Audit all route mappings.** List every path-to-component mapping. Confirm the correct mapping:

   | Path | Expected Component |
   |------|--------------------|
   | `/` | Dashboard / Home |
   | `/experiments` | ExperimentsPage (experiment list) |
   | `/experiments/new` | New Experiment Wizard |
   | `/experiments/:id` | Experiment Results / Detail |
   | `/model` | ModelPage |
   | `/datasets` | DatasetsPage |
   | `/games` | GamesPage (if it exists) |
   | `/games/:gameId` | GameDetailPage |
   | `/teams/:team` | TeamPage (added in Phase 4) |
   | `/frameworks` | FrameworksPage |
   | `/about` | AboutPage |

3. **Fix the swapped entries.** Swap `/experiments` and `/model` (and any other routes that are incorrectly mapped). Do not guess — confirm against the actual component files that each path resolves to the correct page component.

4. **Audit the nav links.** Find the navigation component (likely `src/components/Nav.tsx`, `src/components/Sidebar.tsx`, or similar). Confirm each nav link's `to` or `href` prop matches the correct path. If the nav links are also swapped, fix them here too. Do not trust that fixing the router automatically fixes the nav — audit them independently.

5. **Verify by inspection.** After the fix, confirm:
   - `/experiments` → the experiment list page (shows past experiments, "New Experiment" button)
   - `/model` → the model page (shows model information)
   - Direct URL navigation to each route renders the correct page
   - The nav link labelled "Experiments" navigates to `/experiments`
   - The nav link labelled "Model" (or equivalent) navigates to `/model`

6. **Deploy.** Build and deploy the frontend. This is the highest priority fix — do not batch it with other changes. Get it to production as fast as possible.

---

## P5-02 — Checkbox Triggers Backwards Navigation in Features Step

### Problem

In the New Experiment wizard, Step 3 (Features), clicking checkboxes causes the wizard to jump backwards to Step 2. Reproducible when the page is not fully scrolled to show the Next/Back buttons.

### Root Cause Hypothesis

The most likely cause: a `<button>` element (the Back button, or a step indicator) is positioned underneath the feature checkboxes in the DOM stacking context. When the user clicks a checkbox that is partially obscured or at the edge of the visible viewport, the click event falls through to the underlying Back button and triggers backwards navigation.

Alternatively, the Back button or a clickable step indicator has a z-index or hit-target size that extends into the checkbox area.

### Fix Required

1. **Reproduce the bug.** Open the wizard to Step 3. Add enough features to push the list below the fold. Scroll the wizard card so the Next/Back buttons are off-screen. Click a checkbox near the bottom of the list. Confirm backwards navigation occurs.

2. **Inspect the DOM.** Use browser DevTools to identify what element is receiving the click when the issue occurs. Check:
   - Are the Next/Back buttons inside the scrollable card, or outside it (fixed/sticky position)?
   - Is there a transparent overlay or step-progress indicator that extends over the checkbox area?
   - Does the `<label>` for the checkbox have an abnormally large touch/click target?

3. **Apply the fix.** The correct fix depends on root cause:
   - **If the Back button is inside the scrollable card and overlapping the checkbox area:** Move the Next/Back button row outside the scrollable content area, into a fixed footer below the scroll container. The buttons should never scroll out of view and should never be in the same scroll layer as the content.
   - **If a step indicator or progress bar has a large click target overlapping the checkboxes:** Reduce the hit target with `pointer-events: none` on the overlay, or restructure the component so step indicators don't extend over content.
   - **If a `<label>` element has an oversized area:** Constrain its size to its visible content.

4. **Preferred structural fix:** The most robust solution is to ensure the wizard's Next/Back buttons are always rendered in a footer row that is outside the scrollable content area — not part of the scrolled card body. This prevents any future recurrence regardless of content height. If the current wizard puts buttons inside the scroll container, refactor that layout.

5. **Verify.** After the fix, reproduce the original scenario (step 3, buttons off-screen, click checkbox near bottom). Confirm:
   - Clicking checkboxes toggles the feature selection only
   - No backwards navigation occurs
   - Next/Back buttons still function correctly when clicked directly

---

## P5-04 — `end_season` Defaults to 2024 Instead of 2025

### Problem

In the New Experiment wizard Step 5 (Methodology), the `end_season` field defaults to `2024`. The data pipeline has 2025 data. The default should be `2025`.

### Fix Required

1. **Locate the default.** Find the wizard state initialisation for Step 5 — likely in `src/pages/NewExperimentWizard.tsx`, `src/components/wizard/MethodologyStep.tsx`, or a `useWizardState` hook. Look for `end_season: 2024` or `endSeason: 2024`.

2. **Change the default to 2025.** Update the default value. This is a one-line change.

3. **Check for hardcoded ranges.** If the `end_season` field is a `<select>` or slider with a hardcoded max of 2024, update the max to 2025.

4. **Verify.** Open the wizard to Step 5 and confirm `end_season` shows 2025 as the default selection.

This is a trivial change. Do not spend time on it beyond finding and fixing the one constant.

---

## P5-05 — Dashboard Shows 0 Completed Experiments (Display Side)

### Problem

The dashboard stat card for "Completed Experiments" shows 0 despite experiments with completed runs existing in the system.

### Fix Required

This bug has two sides: a backend query bug (owned by BACKEND-API) and a possible frontend rendering bug. The BACKEND-API fix will correct the API response. Your job is to ensure the frontend correctly reads and displays the corrected value.

1. **Locate the dashboard data fetch.** Find the component that renders the "Completed Experiments" stat card — likely `src/pages/Dashboard.tsx` or `src/components/DashboardStats.tsx`. Find the API call that populates it.

2. **Confirm the field name.** Check what field name the component reads from the API response. Confirm it matches the field name documented in `docs/API_CONTRACTS.md` for the dashboard endpoint. If there is a mismatch (e.g., component reads `completedCount` but API returns `completed_experiments`), fix the frontend to use the correct field name.

3. **Do not add compensating logic.** Do not add a local count of experiments from a separate list API call as a workaround for the broken dashboard API. The correct fix is for the backend to return the right number and for the frontend to display it. If the backend fix is not yet deployed, leave the card showing what the API returns and coordinate timing with BACKEND-API.

4. **Verify.** Once the BACKEND-API fix is deployed, open the dashboard and confirm the completed experiments count is non-zero and matches reality.

---

## P5-08 — Feature Wizard Doesn't Communicate Home/Away Mirroring

### Problem

The experiment wizard Step 3 (Features) shows "5 selected" but the runner automatically mirrors each selected feature to its away-team counterpart, using 10 features in the actual model run. Users are surprised when results show double the features they expected.

### Fix Required

1. **Locate the feature count display.** Find the element in Step 3 that shows the selected feature count — something like `<span>{selectedCount} selected</span>`.

2. **Update the copy.** Change the display to communicate mirroring. The exact wording:

   - When 0 features are selected: show nothing, or "0 selected"
   - When ≥1 features are selected: show `"{n} selected · {n * 2} features used in model (home + away mirrors)"`
   
   Example: `"5 selected · 10 features used in model (home + away mirrors)"`

3. **Add a helper note below the feature list.** Below the feature checkbox list (or below the selected count), add a static explanatory note in muted/secondary text:

   > "Each selected feature is automatically mirrored to its away-team counterpart. Selecting 5 home features adds 5 matching away features — 10 total."

   This note should be visible regardless of selection count, so users understand the behaviour before they select anything.

4. **Do not change the selection logic.** This is a UI copy change only — no changes to how features are submitted to the backend or stored in the experiment config.

5. **Verify.** Open Step 3, select 5 features. Confirm the display reads "5 selected · 10 features used in model (home + away mirrors)". Confirm the explanatory note is visible.

---

## Backend-Gated Items (P5-06 and P5-07 Display)

The per-fold chart and feature importance panel were built in Phase 4 (FRONTEND Track 3 items 3.3 and 3.4) and are already in the codebase. They show empty states when the backend data is absent. These items are gated on BACKEND-API deploying the P5-06 and P5-07 fixes.

**Your action:** After BACKEND-API deploys, navigate to a completed experiment results page and confirm:
- The per-fold chart populates with all folds (not just the 2024 season)
- The feature importance panel renders with feature bars (not an empty state)

If either panel still shows an empty state after the backend fix is deployed, investigate whether the component is reading the correct field names from the updated API response. Coordinate with BACKEND-API if there is a field name mismatch.

Do not rebuild these components — they already exist. This is a verification step only.

---

## Deployment Checklist

After implementing all items, before marking Phase 5 FRONTEND work complete:

- [ ] `/experiments` renders the experiment list page
- [ ] `/model` renders the model page
- [ ] All nav links route to correct pages
- [ ] Direct URL navigation to every route renders the correct component
- [ ] Clicking checkboxes in Step 3 (Features) does not trigger backwards navigation
- [ ] `end_season` defaults to 2025 in Step 5 (Methodology)
- [ ] Dashboard completed experiments count is non-zero (requires BACKEND-API P5-05 deploy)
- [ ] Wizard Step 3 shows "N selected · 2N features used in model (home + away mirrors)"
- [ ] Per-fold chart shows all folds (requires BACKEND-API P5-06 deploy)
- [ ] Feature importance panel renders (requires BACKEND-API P5-07 deploy)
- [ ] Frontend built and deployed to production
- [ ] `PHASE5_STATUS.md` updated with completion notes for each item

---

## What Not to Do

- Do not add compensating frontend logic to work around a broken backend API — coordinate timing with BACKEND-API instead.
- Do not change feature selection logic or experiment config submission in P5-08 — copy change only.
- Do not rebuild the per-fold chart or feature importance panel — they already exist from Phase 4.
- Do not deploy the P5-01 router fix bundled with other changes — it is critical and should go out first, fast.
- Do not add `end_season` a validation rule or warning — it is a default change, not a validation change.
