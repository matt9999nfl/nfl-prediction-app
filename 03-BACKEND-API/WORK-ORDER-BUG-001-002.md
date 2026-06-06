# WORK ORDER — BUG-001 & BUG-002
**From:** PROJECT-LEAD  
**Date:** 2026-05-26  
**Priority:** BUG-001 Critical · BUG-002 Medium  

Two bugs were found during the v2-23base-faithful-2015-2024 rerun session. Both are assigned to you. Read the full specs before touching any code:

- `../00-PROJECT-LEAD/BUG-001-CLONE-DROPS-FEATURES.md` — your tasks are B1-A, B1-B, B1-C
- `../00-PROJECT-LEAD/BUG-002-DEPRECATED-FEATURES.md` — your tasks are B2-A, B2-B, B2-C, B2-D, B2-E

## Quick Summary

**BUG-001 (Critical):** Cloning an experiment creates the new one with `features: []`. Verify that `POST /api/v1/experiments` actually accepts a `features` array in its Pydantic schema and writes it to BigQuery. If the field is missing from `ExperimentCreateRequest`, add it. Also determine whether the 405 on PATCH/PUT is intentional or an oversight — document your decision in `BUG-STATUS.md` (create it in `../00-PROJECT-LEAD/` if it doesn't exist). The frontend agent is waiting on this decision.

**BUG-002 (Medium):** `def_qb_hit_rate` and `def_rush_yards_allowed_per_att` are in at least one saved experiment but no longer in the feature catalog. Add a `deprecated` column to the feature catalog table, mark those features deprecated, exclude them from `GET /api/v1/features` by default, and add a `deprecated_features` array to the experiment detail response plus a `has_deprecated_features` bool to the list response.

## Coordination
When you're done, write your completion notes to `../00-PROJECT-LEAD/BUG-STATUS.md`. The FRONTEND agent reads that file — your B1-B PATCH/PUT decision and your B2-E deploy status both gate their work.
