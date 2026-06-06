# BUG-002 — Deprecated Features Referenced in Experiments With No Warning

**Author:** PROJECT-LEAD  
**Date:** 2026-05-26  
**Severity:** 🟡 Medium  
**Discovered:** v2-23base-faithful-2015-2024 rerun session  
**Status:** Open — delegated to BACKEND-API and FRONTEND  

---

## Problem Statement

Two features — `def_qb_hit_rate` and `def_rush_yards_allowed_per_att` — exist in the saved experiment `v2-23base-faithful-2015-2024` but are no longer present in the platform's feature catalog. When a user searches for them in the feature selection UI, they return no results. The platform shows no indication that the experiment references invalid features.

**Effects:**
1. Users have no way to know which features in an experiment are still valid vs. gone.
2. When cloning, the pre-populated feature count includes deprecated features — the clone silently starts with fewer valid features than the count suggests.
3. If the experiment runner still runs those features, results are unpredictable. If the runner skips them silently, the experiment ran on fewer features than intended with no audit trail.

---

## Deprecation Policy Decision

Before implementing, PROJECT-LEAD is setting this policy explicitly so both agents implement consistently:

**Policy: Tombstoning (soft deprecation)**

Deprecated features are kept as catalog entries with a `deprecated: true` flag and a `deprecated_at` timestamp. They are **not** permanently deleted. Reasons:

1. **Interpretability of historical experiments.** An experiment that ran with `def_qb_hit_rate` must remain interpretable. If the feature is purged from the catalog, there is no record of what it measured.
2. **Auditable deprecation.** Tombstoned entries can carry a `deprecated_reason` field explaining what replaced the feature or why it was removed.
3. **No silent data loss.** Permanently deleting features from the catalog would make it impossible to distinguish "this feature never existed" from "this feature existed and was deprecated."

**Implementation implication for BACKEND-API:** The feature catalog table (`platform.features` or equivalent) needs a `deprecated` boolean column (and optionally `deprecated_at TIMESTAMP`, `deprecated_reason STRING`). If this column doesn't exist, add it via a BigQuery DDL migration. Mark `def_qb_hit_rate` and `def_rush_yards_allowed_per_att` as `deprecated = true`.

**Implementation implication for FRONTEND:** Deprecated features should not appear in the feature search/selection UI for new experiments. They must only appear in the context of explaining what an existing experiment referenced.

---

## BACKEND-API Work Items

### B2-A — Audit all saved experiments against the current feature catalog

Write a query that compares every feature referenced in `platform.experiments` against the current feature catalog.

**Steps:**

1. Identify the column in `platform.experiments` that stores features. It is likely a REPEATED STRING field (BigQuery array) or a JSON string. Check the schema.

2. Identify the feature catalog table. It is likely `platform.features` or `curated.features`. Find the column that stores the canonical feature name (the same string used as feature identifiers in experiment configs).

3. Run an audit query to find all features referenced in any experiment that do not appear in the catalog:
   ```sql
   -- Example structure (adjust table/column names to match actual schema)
   SELECT DISTINCT feature
   FROM platform.experiments,
   UNNEST(features) AS feature
   WHERE feature NOT IN (
     SELECT name FROM platform.features WHERE deprecated IS NOT TRUE
   )
   ORDER BY feature
   ```

4. Document the results in `BUG-STATUS.md` (or append to it): which experiments reference which deprecated/missing features.

5. Specifically confirm: does `v2-23base-faithful-2015-2024` reference `def_qb_hit_rate` and `def_rush_yards_allowed_per_att`? Are there other experiments with other deprecated features?

### B2-B — Add deprecated column to feature catalog

If `platform.features` (or equivalent) does not have a `deprecated` boolean column:

1. Add it via BigQuery DDL:
   ```sql
   ALTER TABLE platform.features
   ADD COLUMN IF NOT EXISTS deprecated BOOL DEFAULT FALSE,
   ADD COLUMN IF NOT EXISTS deprecated_at TIMESTAMP,
   ADD COLUMN IF NOT EXISTS deprecated_reason STRING;
   ```

2. Mark the two known deprecated features:
   ```sql
   UPDATE platform.features
   SET deprecated = TRUE,
       deprecated_at = CURRENT_TIMESTAMP(),
       deprecated_reason = 'Feature removed from curated catalog during v2 rebuild'
   WHERE name IN ('def_qb_hit_rate', 'def_rush_yards_allowed_per_att');
   ```

3. Mark any other features identified in B2-A as deprecated similarly.

4. Update `GET /api/v1/features` to exclude deprecated features from the default response. Add an optional `?include_deprecated=true` query param that returns them with their deprecation metadata (useful for admin/debug views).

### B2-C — Add deprecated_features to experiment detail response

Update `GET /api/v1/experiments/{experiment_id}` to include a `deprecated_features` field in the response. This field lists any features referenced by the experiment that are no longer in the active catalog (i.e., are tombstoned or absent).

**Schema addition** in `app/schemas/experiments.py`:
```python
class DeprecatedFeatureInfo(BaseModel):
    name: str
    deprecated_reason: Optional[str] = None

class ExperimentDetailResponse(BaseModel):
    # ... existing fields ...
    deprecated_features: List[DeprecatedFeatureInfo] = []
```

**Query logic:** For each experiment, cross-reference its `features` array against `platform.features WHERE deprecated = TRUE OR name NOT IN (SELECT name FROM platform.features)`. Return the matching feature names (with reason if available) in `deprecated_features`.

**If the experiment has no deprecated features**, return `deprecated_features: []` — do not omit the field. The frontend uses field presence to decide whether to render the warning banner.

**Smoke test:** Call `GET /api/v1/experiments/<id_for_v2-23base-faithful-2015-2024>`. Confirm the response includes:
```json
{
  "deprecated_features": [
    {"name": "def_qb_hit_rate", "deprecated_reason": "Feature removed from curated catalog during v2 rebuild"},
    {"name": "def_rush_yards_allowed_per_att", "deprecated_reason": "Feature removed from curated catalog during v2 rebuild"}
  ]
}
```

### B2-D — Update GET /api/v1/experiments list endpoint

The experiment list response (`GET /api/v1/experiments`) should include a `has_deprecated_features: bool` flag per experiment — a lightweight indicator so the frontend can show a warning badge on list cards without fetching full experiment detail.

```json
{
  "experiments": [
    {
      "experiment_id": "...",
      "name": "v2-23base-faithful-2015-2024",
      "has_deprecated_features": true,
      ...
    }
  ]
}
```

This is a boolean only (not the full list) — the detail endpoint carries the full `deprecated_features` array.

### B2-E — Redeploy and smoke test

After all backend changes:
1. Redeploy the Cloud Run service.
2. Smoke test `GET /api/v1/features` — confirm deprecated features are excluded from the default response.
3. Smoke test `GET /api/v1/experiments/<v2-23base-faithful-2015-2024-id>` — confirm `deprecated_features` is non-empty and correctly populated.
4. Smoke test `GET /api/v1/experiments` list — confirm `has_deprecated_features: true` appears for the affected experiment.

---

## FRONTEND Work Items

### F2-A — Warning banner on experiment detail page

On the experiment detail page (`src/pages/ExperimentDetailPage.tsx` or equivalent), add a warning banner when `deprecated_features.length > 0`.

**Design:**
- Render the banner prominently at the top of the page, below the experiment name/header but above the results panels.
- Style as a warning (amber/yellow, not red — the experiment ran successfully, the features are just stale).
- Content: `"N feature(s) in this experiment are no longer available: [comma-separated list]. Results from this run remain valid, but these features cannot be selected in new experiments."`
- Example: `"2 features in this experiment are no longer available: def_qb_hit_rate, def_rush_yards_allowed_per_att. Results from this run remain valid, but these features cannot be selected in new experiments."`
- The banner should be dismissable per session (i.e., if the user closes it, it stays closed for the duration of the browser session, but re-appears on next visit). Use React state — no localStorage.
- If `deprecated_features` is empty or absent, do not render the banner.

**Data source:** Read `deprecated_features` from the experiment detail API response (added in B2-C above). Do not compute this client-side by comparing against the features list.

### F2-B — Warning badge on experiment list cards

On the experiments list page, if a list item has `has_deprecated_features: true` (added in B2-D), render a small warning indicator on the experiment card.

**Design:**
- A small amber badge or icon (e.g., ⚠️ or an amber dot) next to the experiment name.
- Tooltip or aria-label: `"This experiment references features that are no longer available"`.
- Keep it subtle — the experiment is still valid, this is informational.

### F2-C — Clone wizard: exclude deprecated features from pre-populated count and flag them

When the clone wizard pre-populates Step 3 from a source experiment, deprecated features must be handled explicitly.

**Steps:**

1. When loading the source experiment for cloning, read both `features` (the full list) and `deprecated_features` (the subset that is no longer valid).

2. In the wizard state initialisation, **exclude deprecated features from the pre-selected set**:
   ```tsx
   const activeFeatures = sourceExperiment.features.filter(
     f => !sourceExperiment.deprecated_features.map(d => d.name).includes(f)
   )
   setSelectedFeatures(activeFeatures)
   ```
   The badge should show the count of active (non-deprecated) features only.

3. **Flag the excluded features explicitly in the wizard UI.** In Step 3 (Features), below the search bar or at the top of the feature list, show an informational alert when deprecated features were excluded:
   - `"N feature(s) from the original experiment are no longer available and were not pre-selected: [list]. Please select substitutes."`
   - Example: `"2 features from the original experiment are no longer available and were not pre-selected: def_qb_hit_rate, def_rush_yards_allowed_per_att. Please select substitutes."`
   - This alert should be static (not dismissable) — the user must acknowledge they need to pick replacements.

4. **Do not pre-select deprecated features.** They do not appear in the feature catalog search results and cannot be selected, so silently pre-selecting them would produce the same empty-result problem that BUG-001 causes.

### F2-D — Feature search: do not surface deprecated features

Confirm that the feature search/selection UI in Step 3 does not return deprecated features in search results. This should be automatic if `GET /api/v1/features` excludes them by default (B2-B above). Verify after the backend deploys.

If the feature list is fetched once and cached client-side, confirm the cache is populated from the non-deprecated response. If the frontend was previously caching deprecated features in local state, clear that cache.

### F2-E — Verify end-to-end

After backend B2-C and B2-D are deployed:

1. Open `v2-23base-faithful-2015-2024` experiment detail page. Confirm the amber warning banner appears listing the two deprecated features.
2. Open the experiments list. Confirm the experiment card shows a warning badge.
3. Click "New experiment from this config" on the affected experiment. Confirm:
   - The feature count in Step 3 shows `(total - 2)` features pre-selected (not the full 23).
   - An alert in Step 3 names the 2 excluded features and asks the user to select substitutes.
   - The deprecated features do not appear in the search results if searched for by name.
4. Complete the wizard and save. Confirm the new experiment has `deprecated_features: []` in its detail response.

---

## Acceptance Criteria

- [ ] `GET /api/v1/features` excludes deprecated features by default
- [ ] `GET /api/v1/experiments/{id}` includes `deprecated_features: [...]` for affected experiments
- [ ] `GET /api/v1/experiments` list includes `has_deprecated_features: bool` per experiment
- [ ] `platform.features` has a `deprecated` column; `def_qb_hit_rate` and `def_rush_yards_allowed_per_att` are marked deprecated
- [ ] Experiment detail page shows an amber warning banner when deprecated features are present
- [ ] Experiment list cards show a warning badge for affected experiments
- [ ] Clone wizard excludes deprecated features from pre-populated selection and names them explicitly
- [ ] Clone wizard feature count reflects only active (non-deprecated) features
- [ ] Both agents update `BUG-STATUS.md` with their completion notes

---

## What Not To Do

- Do not permanently delete deprecated features from the catalog — tombstone them (soft deprecation).
- Do not show a red error state on the experiment detail page — the run results are valid; this is an informational warning.
- Do not attempt to re-run the experiment with substitute features automatically — the user chooses substitutes via the clone wizard.
- Do not add deprecated features to the feature search UI — they are excluded from `GET /api/v1/features` responses.
- Do not add `deprecated_reason` logic to the experiment runner — runner behaviour for deprecated features is out of scope for this bug fix.
