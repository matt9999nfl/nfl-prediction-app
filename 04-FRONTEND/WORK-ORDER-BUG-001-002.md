# WORK ORDER — BUG-001 & BUG-002
**From:** PROJECT-LEAD  
**Date:** 2026-05-26  
**Priority:** BUG-001 Critical · BUG-002 Medium  

Two bugs were found during the v2-23base-faithful-2015-2024 rerun session. Both are assigned to you. Read the full specs before touching any code:

- `../00-PROJECT-LEAD/BUG-001-CLONE-DROPS-FEATURES.md` — your tasks are F1-A, F1-B, F1-C
- `../00-PROJECT-LEAD/BUG-002-DEPRECATED-FEATURES.md` — your tasks are F2-A, F2-B, F2-C, F2-D, F2-E

## Quick Summary

**BUG-001 (Critical):** The "New experiment from this config" wizard shows the correct feature count badge (e.g. "23 selected") but the final POST to `POST /api/v1/experiments` sends `features: []`. Trace the wizard state — find where the cloned experiment's features are loaded for display but not threaded into the form state that gets serialised on submit. Fix the state so features survive through all wizard steps to the POST payload. Also add a Save guard: if `features.length === 0` at submit time, show an inline error and block the API call.

**BUG-002 (Medium):** Experiments can reference features that no longer exist in the catalog. Once the BACKEND-API agent deploys its changes, the detail response will include `deprecated_features: [...]` and the list response will include `has_deprecated_features: bool`. Your job: (1) amber warning banner on the experiment detail page, (2) amber badge on experiment list cards, (3) clone wizard excludes deprecated features from pre-population and names them explicitly so the user knows to pick substitutes.

## Coordination
Check `../00-PROJECT-LEAD/BUG-STATUS.md` for the backend agent's completion notes. Their B1-B PATCH/PUT decision tells you whether a post-creation update path exists (you probably don't need it — fix the initial POST either way). Their B2-E deploy status tells you when the deprecated_features API fields are live so you can verify F2-E.

When done, build and deploy (`npm run build` → `gsutil -m rsync -r -d dist/ gs://nfl-frontend-nfl-model-471509/` → invalidate CDN cache) and append your completion notes to `../00-PROJECT-LEAD/BUG-STATUS.md`.
