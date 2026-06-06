# BUG-001 — Experiment Cloning Drops All Features

**Author:** PROJECT-LEAD  
**Date:** 2026-05-26  
**Severity:** 🔴 Critical  
**Discovered:** v2-23base-faithful-2015-2024 rerun session  
**Status:** Open — delegated to BACKEND-API and FRONTEND  

---

## Problem Statement

When a user clicks "New experiment from this config" on an existing experiment, the wizard pre-populates Step 3 with a feature count badge (e.g. "23 selected"). After completing the wizard and saving, the experiment is created with `features: []`. The API confirms the empty array. No validation error or warning is shown at save time.

**Effect:** Every cloned experiment silently loses its feature set. The experiment runner executes with an empty feature matrix, producing meaningless results.

---

## BACKEND-API Work Items

### B1-A — Verify POST /api/v1/experiments accepts features on creation

The contract says `POST /api/v1/experiments` must accept a `features` array in the request body. Verify this is actually true in the live service.

**Steps:**

1. Open `app/schemas/experiments.py`. Find the `ExperimentCreateRequest` (or equivalent) Pydantic model. Confirm it includes a `features` field, e.g.:
   ```python
   features: List[str] = []
   ```
   If the field is absent from the schema, add it. An absent `features` field means FastAPI silently drops it before the handler sees it, which would explain the bug.

2. Open `app/routers/experiments.py` (or wherever `POST /api/v1/experiments` is handled). Confirm the handler reads `request.features` and writes it to `platform.experiments`. Trace the BigQuery INSERT — confirm `features` is in the column list.

3. Smoke test against the live API (`https://nfl-backend-api-rmaehdhzhq-uc.a.run.app`):
   ```bash
   curl -X POST https://nfl-backend-api-rmaehdhzhq-uc.a.run.app/api/v1/experiments \
     -H "Content-Type: application/json" \
     -H "X-API-Key: <key>" \
     -d '{"name": "clone-test", "features": ["home_epa", "away_epa"], ...}'
   ```
   Confirm the created experiment's detail response shows `features: ["home_epa", "away_epa"]`.

**If `features` is missing from `ExperimentCreateRequest`:** Add it, redeploy, and document the root cause in the status doc. This is likely the primary backend cause of the bug.

### B1-B — Audit PATCH and PUT on /api/v1/experiments/{experiment_id}

Both `PATCH /api/v1/experiments/{experiment_id}` and `PUT /api/v1/experiments/{experiment_id}` currently return 405. Determine whether this is intentional or an oversight.

**Decision to make (binary choice):**

**Option A — No update path is intentional.** Experiments are immutable after creation. This is a valid design — if features must be set at creation time, the frontend fix (B1-A above) is sufficient. Document this explicitly in `docs/API_CONTRACTS.md` with a note: "Experiments are immutable after creation. Features must be supplied in the initial POST." Add an ADR if this constraint isn't already recorded.

**Option B — An update path should exist.** If there are other legitimate reasons to update experiment fields after creation (e.g. adding a description, updating notes), implement a `PATCH /api/v1/experiments/{experiment_id}` endpoint. For features specifically, allow updating `features: List[str]` via PATCH only if no runs have been completed for the experiment (runs make the feature set part of the historical record — it shouldn't be mutable).

**How to decide:** Check `docs/DECISIONS.md` for any ADR that addresses experiment mutability. If none exists, default to **Option A** (immutability). Immutability is simpler, reduces audit surface, and is consistent with the existing 405 behaviour. The frontend fix is the correct path.

**Regardless of which option is chosen:** Document the decision in this bug's status entry in `BUG-STATUS.md` (or create that file if it doesn't exist). The frontend agent needs to know the answer before they can close this bug — communicate clearly.

### B1-C — Redeploy if schema fix was needed

If B1-A required a schema or handler fix:
1. Rebuild and redeploy the Cloud Run service (same process as Phase 5 deploys).
2. Smoke test `POST /api/v1/experiments` with a non-empty `features` array against the live URL.
3. Confirm the returned experiment detail has matching features.

---

## FRONTEND Work Items

### F1-A — Trace wizard state: why do features disappear from the POST payload?

The wizard correctly shows "23 selected" in Step 3 but submits `features: []`. This is a state management bug. The cloned config is loaded into the wizard UI but not properly threaded into the state that is serialised on submit.

**Steps:**

1. Find the wizard component — likely `src/pages/ExperimentsNewPage.tsx` or `src/components/wizard/`. Find where "New experiment from this config" loads the source experiment data. This is likely an effect that runs when a `cloneFromId` or `sourceExperimentId` query param is present.

2. Find where the cloned experiment's features are pre-populated into the wizard's Step 3 state. Look for something like:
   ```tsx
   setSelectedFeatures(sourceExperiment.features)
   // or
   setState(prev => ({ ...prev, features: sourceExperiment.features }))
   ```
   If this population step exists, confirm the setter is actually updating the state object that gets serialised on the final submit — not a local display-only state.

3. Find the submit handler (called when the user clicks Save in the final wizard step). Trace what it sends as the `features` field in the POST body. Add a `console.log('Submitting features:', payload.features)` temporarily if needed to confirm the value at submit time.

4. **Common failure patterns to look for:**
   - The wizard uses a multi-step state object initialised as `{ features: [] }`. The clone populates a *display* state (e.g. a `featuresForDisplay` derived value) but never updates the *form* state. On submit, the form state's `features: []` is used.
   - The clone populates the state correctly, but Step 3's `onChange` handler overwrites the loaded features with an empty array when the step is first rendered.
   - The features are stored as a `Set` or object internally but serialised incorrectly to the POST body (e.g. `Array.from(features)` is missing).

5. **Fix the bug:** Once the root cause is identified, fix the state threading so that:
   - When cloning, `selectedFeatures` (or the equivalent field) in the wizard's form state is initialised from `sourceExperiment.features`.
   - The features remain in state across all subsequent wizard steps.
   - The submit handler reads from the same state object and includes features in the POST payload.

### F1-B — Add Save guard: block submission if features.length === 0

In the wizard's final step (or in the submit handler), add a validation check:

```tsx
if (payload.features.length === 0) {
  // Show an inline error — do not call the API
  setError('At least one feature must be selected before saving. Go back to Step 3 to add features.')
  return
}
```

**Requirements:**
- The error must be visible to the user in the UI — do not silently swallow the submit.
- The user must be able to navigate back to Step 3 from the error state.
- This guard applies to all experiment creation paths (new and cloned). A blank feature set is never valid.
- Do not block the wizard's individual step navigation — only block the final Save action.

### F1-C — Verify fix end-to-end

After both the state fix (F1-A) and the guard (F1-B) are in place:

1. Open an existing experiment with ≥1 feature.
2. Click "New experiment from this config".
3. Advance through the wizard to Step 3. Confirm the feature selection shows the source experiment's features pre-selected.
4. Complete the wizard and click Save.
5. Navigate to the new experiment's detail page. Confirm `features` is non-empty and matches what was selected.
6. Also test: open the wizard fresh (no clone source) and attempt to Save with 0 features selected. Confirm the error message appears and the API is not called.

---

## Integration Note

The backend and frontend fixes for this bug are **independent but both required**:

- If only the backend is fixed (POST schema accepts features) but the frontend still sends `features: []`, the bug persists.
- If only the frontend is fixed (wizard threads features into state) but the backend schema drops them, the bug persists.
- If PATCH/PUT is added (Option B above), the frontend does **not** need to use it for this bug — the initial POST fix is the correct path. PATCH/PUT would be additive.

**Coordination point:** The BACKEND-API agent must document its B1-B decision (Option A or Option B) clearly. The FRONTEND agent can proceed with F1-A and F1-B regardless of that decision, since both fix paths require the initial POST to carry features.

---

## Acceptance Criteria

- [ ] `POST /api/v1/experiments` with `features: ["home_epa", "away_epa"]` creates an experiment with those features (not `[]`) — confirmed against live API
- [ ] Cloning an existing experiment and completing the wizard results in the new experiment having the source's features in its detail response
- [ ] Attempting to Save the wizard with 0 features selected shows a validation error and does not call the API
- [ ] BACKEND-API documents the PATCH/PUT decision (Option A or B) in the API contracts or ADR log
- [ ] Both agents update `BUG-STATUS.md` (create if needed) with their completion notes

---

## What Not To Do

- Do not add a secondary PATCH call after experiment creation as a workaround for the missing features — fix the POST payload.
- Do not add a "fix features" button on the experiment detail page — the create path must be correct.
- Do not silently swallow the empty-features case — surface it to the user.
- Do not change the experiment runner or BigQuery schema — all needed columns exist.
