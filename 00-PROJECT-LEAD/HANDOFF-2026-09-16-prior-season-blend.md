# HANDOFF — Prior-season blend go-live, 2026-09-16

**For:** whoever picks this up next
**Covers:** PROMPT-PRIOR-SEASON-BLEND.md, start to finish
**Status:** Shipped and verified live.

---

## What shipped

Blended prior-season features (`<feature>_blend`, prior season weighted as
`N=8` pseudo-games) are now what `predict_upcoming.py` and
`run_production_refresh.py` train and predict on, replacing the
current-season-only 23. Plus `<feature>_prev` (unblended prior-season value,
all 23 stats) and `games_played_this_season`, registered in the feature
catalog as selectable-but-not-live. Full definition, per-feature-group
treatment, and the backtest table are in **`docs/DECISIONS.md` ADR-013**.

Commit: `0e1ed14` (feature code, backend catalog, ADR, dashboard wording).
Fallback warning shipped separately and earlier: `dd09e17`.

## Backtest experiment IDs (platform.experiment_configs)

| Config | experiment_id |
|---|---|
| Baseline (fresh, current 23) | `a7918c57-dcd4-42c4-9cf4-90aeed050330` |
| Blend N=2 | `633eb49c-2a8f-4aaa-9871-1e4ab9466328` |
| Blend N=4 | `d11b2b09-5311-4e65-a4ed-aafd6d6757c9` |
| Blend N=6 | `c68e3f28-aeda-4f72-aaf2-fb2976c65aea` |
| Blend N=8 (chosen) | `e9568d66-8b67-47bd-96f7-4446fa34066e` |

All run via `run_experiment.py` locally (the `nfl-experiment-runner` Cloud Run
job still has an old image not worth rebuilding just for this — see below,
we rebuilt it anyway for the *production-refresh* job, which is separate).
Configs and runs are real rows in `platform.experiment_configs` /
`experiments.backtest_runs` / `experiments.backtest_predictions`. Re-run the
tuning/confirmation split with `backtests/report_blend_backtest.py`.

`platform.capability_gaps` gap `efc70d0b-22db-43ee-850b-32af62a1e94e` marked
`resolved` — the lagged-prior-season-aggregate gap from the 2026-09-09
hypothesis run.

## Production job image

| | |
|---|---|
| Before | `gcr.io/nfl-model-471509/nfl-experiment-runner@sha256:269c67d5bf269c9c92d6baf02baad3e615fd1e8d55b8a2778b6f48e62bbbaae1` |
| After | `gcr.io/nfl-model-471509/nfl-experiment-runner@sha256:fff36d01034fefbcfee4a22fa82f40e01643549d67aa95453844f8acb78c24c6` |

Job still runs `python backtests/run_production_refresh.py` — confirmed via
`describe`. Rebuilt via `cloudbuild.yaml` (same command as always;
`cloudbuild.yaml` was not changed).

## Week 2 regenerated — verified against the live API

Executed `nfl-production-refresh-2kg72` at 2026-09-16 10:44 UTC — well inside
the Fri 18 Sep 00:15 UTC deadline.

**Before** (reference point per Matt: the 2026-09-15 14:02:55Z run):
- Week 2: 16 rows, confidence tiers `{high: 9, medium: 1, low: 6}`
- Week 1: 16 rows, `{low: 12, medium: 3, high: 1}`, 15 graded (12-3), NE@SEA push ungraded

**After** (2026-09-16 10:44:14Z):
- Week 2: 16 rows, fresh `generated_at`, confidence tiers `{high: 2, medium: 7, low: 7}` — high-confidence count dropped from 9 to 2, which is the whole point of the fix.
- Week 1: content unchanged — 15 graded, 12 wins, 3 losses, NE@SEA still the sole ungraded (push) game. DEFECT-3's grading-preservation fix held.

**One thing worth knowing, not a defect:** week 1's `generated_at` in the API
response also moved to 10:44:14Z, even though week 1's own prediction rows
were not rewritten. `get_production_experiment()` resolves `generated_at`
from the production experiment's single most-recent run, not per-week — so
regenerating week 2 updates the timestamp shown for every week's response.
Confirmed the underlying week-1 *rows* are untouched (same win/loss/push
pattern); this is a display quirk in how `generated_at` is sourced, pre-existing
and not introduced by this change. Worth fixing at some point (source
`generated_at` from the specific week's own prediction rows instead), but out
of scope here.

Deploys confirmed live:
- API: `commit: 0e1ed14` (`/health`)
- Frontend: bundle `index-BoxvXiZa.js`, contains the reworded "blended with
  last season's numbers" warning text.

## What's left open

1. **The `generated_at`-is-per-experiment-not-per-week quirk** above.
2. **Roster/QB/coaching changes between seasons are not modeled** — documented
   limitation in ADR-013, not fixed here.
3. **Everything in PROMPT-PRIOR-SEASON-BLEND.md §8** (roof bug, weather
   mismatch, uncalibrated confidence tiers, retired `0.54` threshold still
   written by `build_config_payload`) — untouched, as instructed.
4. **29 pre-existing backend test failures**, unrelated to this change
   (auth, datasets, experiments, frameworks, games, predictions routers) —
   none touch `features.py`; all feature-related tests pass. Matches the
   known queue item "backend tests runnable without GCP credentials."
5. **`def_qb_hit_rate` is missing from `_PER_TEAM_FEATURES` in
   `03-BACKEND-API/app/queries/features.py`** (pre-existing catalog gap,
   found while adding the `_blend`/`_prev` entries) — its blend/prev
   variants exist and work in the modeling code and are selectable by
   `run_experiment.py`, but aren't listed in the human-facing
   `GET /api/v1/features` catalog because the base feature itself isn't
   listed there. Small, pre-existing, not introduced by this change.
