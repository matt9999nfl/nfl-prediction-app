# Pipeline Remediation — PR-001: home_covered Sign Inversion

**Owner:** PROJECT-LEAD
**Assigned to:** DATA-PIPELINE
**Date:** 2026-05-03
**Priority:** Blocking — Phase 1 backtest cannot be evaluated until resolved
**Status:** ✅ RESOLVED — 2026-05-03
**Root cause confirmed:** nflverse `spread_line` uses positive = home favored (non-standard convention). Fix: removed negation of `spread_line` before comparison in `build_curated_games.py`. All 71 validation checks pass. Spread-bin diagnostic confirmed 45–55% coverage rate across all bins.

---

## What Happened

MODELING ran the Phase 1 backtest and flagged a data integrity issue before reporting results. The `curated.games.home_covered` label is inverted — a correctly-derived home_covered column should be approximately 50% in every spread bin (that is what a closing line is, by definition). Instead, the diagnostic shows a perfect monotonic inversion:

| Spread bin | Actual home cover rate | Expected |
|---|---|---|
| Home favored by 10+ | 7.5% | ~50% |
| Home favored by 6–10 | 5.3% | ~50% |
| Home favored by 3–6 | 24.9% | ~50% |
| Near pick 'em | ~50% | ~50% |
| Home underdog by 3–6 | 76.9% | ~50% |
| Home underdog by 6–10 | 91.8% | ~50% |
| Home underdog by 10+ | 98.4% | ~50% |

The near-pick'em bucket is correct (~50%), which tells us the data itself is fine — only the sign convention is wrong.

---

## Root Cause Hypothesis

The `curated.games` build currently derives `home_covered` as:

```python
margin = home_score - away_score
required_margin = -home_spread_close
covered = margin > required_margin
```

This formula is correct **if** `home_spread_close` is stored as: negative = home favored (standard betting convention, e.g., home -7 → stored as -7.0).

The diagnostic pattern is consistent with `spread_line` from nflfastR/nflverse being stored from the **away team's perspective** or the **favorite's perspective** — not from the home team's perspective. If a game where the away team is favored by 7 is stored as `spread_line = -7`, and DATA-PIPELINE mapped this directly to `home_spread_close = -7`, then home_covered would be derived as though the home team needs to win by 7 when in fact they are a 7-point underdog. This produces the observed near-zero coverage rate for "home favorites."

---

## Required Investigation

Before rebuilding, confirm the actual sign convention of `spread_line` in `raw_nflfastr.schedules` with a spot-check:

**Step 1 — Pull 5–10 known games and verify manually.**
Pick games from 2019–2024 where the outcome is publicly known (e.g., Super Bowl games, well-known upsets). Query `raw_nflfastr.schedules` for those game_ids and check:
- What is `spread_line` for each game?
- Who was actually favored?
- What was the final margin?
- Does the stored `spread_line` represent the home team's line or the away team's line?

**Step 2 — Check the nflverse documentation.**
`nfl_data_py.import_schedules()` field descriptions. Confirm what perspective `spread_line` uses and what sign convention (negative = favored, or positive = favored).

**Step 3 — Derive the correct formula.**
Based on your investigation, determine the correct derivation of `home_covered`. The formula must produce ~50% coverage rate in every spread bin when checked against the full 2015–2025 dataset.

---

## Required Fix

Once the sign convention is confirmed, rebuild `curated.games` with the corrected derivation and re-validate.

**Validation gate for the fix** — run the same spread-bin diagnostic and confirm:

| Spread bin | Required home cover rate |
|---|---|
| Home favored by 10+ | 45–55% |
| Home favored by 6–10 | 45–55% |
| Home favored by 3–6 | 45–55% |
| Near pick 'em | 45–55% |
| Home underdog by 3–6 | 45–55% |
| Home underdog by 6–10 | 45–55% |
| Home underdog by 10+ | 45–55% |

All bins must fall within 45–55%. If any bin falls outside this range, the formula is still wrong. Do not hand off until all bins pass.

**Also re-run the full validation checklist from `PIPELINE_SPEC_PHASE1.md`** — confirm `home_covered` null rate is still ≤ 5% and no other fields were affected.

---

## Handoff Back to MODELING

Once the fix is validated:
1. Notify PROJECT-LEAD with the corrected spread-bin diagnostic (the table above, filled in)
2. PROJECT-LEAD will confirm and clear MODELING to re-run
3. MODELING re-runs `python backtests/run_phase1_backtest.py` — no other changes needed

The modeling pipeline, feature code, walk-forward harness, and OL mismatch logic are all correct. This is the only outstanding issue.

---

## What Is NOT in Scope for This Fix

- No other schema changes to `curated.games` or `curated.plays`
- No re-ingestion of raw tables (raw data is correct — this is a transformation error only)
- No changes to the MODELING codebase
