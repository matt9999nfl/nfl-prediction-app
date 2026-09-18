# HANDOFF — Per-game pick explanations (Stage 1), 2026-09-17

**For:** whoever picks this up next
**Covers:** `PROMPT-PICK-EXPLANATIONS-AND-EDGE-LAB.md`, STAGE 1 only
**Status:** Live path, backfill, API, and UI shipped and verified live. Backtest-path
wiring (walk_forward.py / run_experiment.py) is **not done** — see "What's left open".

---

## What shipped

**Explanation engine** (`02-MODELING`):
- `features/families.py` — the one feature→family map, used everywhere. Covers
  the base 23, every `_blend`/`_prev` variant, and the game-context features.
  Families: OL pass protection, OL run blocking, QB, run game, defence pass
  rush, defence run, coverage/defence other, form, record/margin, rest,
  weather, venue/context.
- `models/ol_xgb.py` — `OLXGBModel.explain()` (exact TreeSHAP via
  `booster.predict(..., pred_contribs=True)`, asserted to sum to the model's
  raw log-odds within 1e-4) and `.explain_interactions()` (top-k SHAP
  interaction pairs per row, `pred_interactions=True`).
- `backtests/explanations.py` — enrichment layer: side (home/away/game),
  family, league percentile (rank within the same season/week across all 32
  teams), the pick-direction re-signing, and the family matchup view
  (home/away contribution + net, per family).
- `backtests/explanations_bq.py` — storage for the new table
  `experiments.prediction_explanations` (partitioned by season, clustered by
  `experiment_id, week`). One row per (game, feature).

**Live path**: `predict_upcoming.py` / `run_production_refresh.py` now call
`write_week_explanations()` after writing picks — delete-then-insert, skipping
any game with an already-recorded result (the "kicked off" proxy — see the
function's docstring for its known limitation). Explanations failing does not
roll back or block the predictions themselves.

**Backfill**: `backtests/explain_picks.py` retrains exactly as production did
for a given (season, week), compares against the stored picks, and only
stores explanations on a match (`REPRODUCTION_TOLERANCE = 1e-6`) unless
`--approximate` is passed. **Only runs on Linux** — see "The investigation"
below for why. Every real run writes an environment fingerprint
(`..._env.json`) next to its diff report.

**Storage columns added this session**: `reproduction_max_diff` (FLOAT64,
NULLABLE) and `is_approximate` (BOOL, REQUIRED) — the guard's outcome for a
backfilled week. `clean_forward` is untouched and still means only "not
regenerated after kickoff"; it is never repurposed to mean "approximate."

**API**: `GET /api/v1/predictions/{game_id}/explanation` — top 5 drivers,
family matchup, full feature list, `is_approximate`/`reproduction_max_diff`/
`clean_forward`. No auth, same as `GET /api/v1/predictions`.

**UI**: `WhyThisPick` panel on the game detail page (signed driver bars with
raw value + league percentile, imputed values marked with `*`, family matchup
underneath, an "Approximate" badge + explanatory line when
`is_approximate`). A compact main-driver chip on each dashboard game card,
via `GameCardWithExplanation` — split out as its own component so `GameCard`
itself stays fetch-free and its existing `renderToStaticMarkup` tests needed
no changes to their rendering approach.

**Tests**: 215 modeling tests, 7 new backend tests, 40 frontend tests — all
green. (29 pre-existing backend test failures are unrelated to this work —
already present and documented before this session; see
`SESSION-LOG-2026-09-15-to-17.md`.)

## Commits

| Commit | What |
|---|---|
| `cb9ad34` | Modeling: `explain()`, family map, storage, live-path wiring, `explain_picks.py`, tests |
| `3b38a6f` | API endpoint + `WhyThisPick` panel + main-driver chip, tests |

## The investigation (the bulk of this session)

`explain_picks.py --season 2026 --week 1` and `--week 2` initially failed the
reproduction guard on every game in both weeks. Full trail, in order, is in
**`00-PROJECT-LEAD/QUESTIONS.md`** under the 2026-09-17 pick-explanations
entry — summary:

1. Package versions on the machine that ran the guard matched
   `requirements.txt`'s pins exactly (pandas 1.5.3 / numpy 1.26.4 /
   scikit-learn 1.9.0 / xgboost 3.2.0) — not a version mismatch.
2. `curated.plays` / `curated.games` last-modified timestamps predate the
   week-2 picks — not a data rebuild.
3. **Root cause: Windows vs Linux.** Reproducing week 2 inside the actual
   production Cloud Run image matched the stored picks to within **2.86e-08**
   (later **exactly 0.0** on a second run inside a freshly-built image).
   Reproducing on Windows, same pinned versions, drifted by up to **0.097**
   with side flips. Platform-compiled numpy/BLAS binaries differ between
   Windows and Linux — the same class of issue `ol_xgb.py` already documents
   for core-count (`n_jobs=1`), just triggered by OS instead of thread count.
4. **Week 1 still does not reproduce, even inside the correct Linux image** —
   diffs 0.007–0.037, 3 side flips (a different trio than seen on Windows:
   ATL_PIT, GB_MIN, NYJ_TEN). This is a genuine, unresolved data-provenance
   question, not a platform artifact — root cause not found this session.
   **Week 1's stored explanations are `is_approximate=True`** as a result
   (`--approximate` used, `reproduction_max_diff=0.0370355`).

**Consequence for all later stages** (per Matt's standing instruction): any
run whose numbers are evidence or must match production — reproductions,
backtests, grids — runs in the production Linux image, not on Windows.
`explain_picks.py` now enforces this itself (`_check_linux`, no CLI bypass).
Stage 3 grids default to `--remote`.

## Image / infra

| | |
|---|---|
| New image | `gcr.io/nfl-model-471509/nfl-experiment-runner@sha256:219c721fcee4c3b079afbac687b77cc62ed0787adf14f78a9236802bf2c5739b` |
| Built from | `main` @ `cb9ad34`, via `gcloud builds submit --config cloudbuild.yaml .` |
| Caveat | Build context also included uncommitted local files present at build time (a modified `instructions.md`, an untracked `archive/` dir, 3 report CSVs — none affect the Python code; `Dockerfile.job` does `COPY . .`) |
| `nfl-production-refresh` job | Repointed from `fff36d0…c24c6` to `219c721…5739b`. **Not executed** this session. |

Explanations were written via one-off Cloud Build steps against the new
image (not the job) — `explain_picks.py --season 2026 --week 2` (exact) then
`--week 1` (failed, then `--approximate`). No Cloud Run job, scheduler, or
IAM change made; no BigQuery write outside `prediction_explanations`.

## Verified live

- `experiments.prediction_explanations`: 16 games × 54 features = 864 rows
  for week 2 (`is_approximate=0` for all), 16 games × 52 features = 832 rows
  for week 1 (`is_approximate` for all — unblended feature set, hence 52 not
  54), `clean_forward=False` correctly only on `2026_01_SF_LA` and
  `2026_01_NE_SEA`.
- Contribution + bias reconstructs each stored pick's log-odds within **2.49e-07**
  across all 32 games (both weeks) — well inside the 1e-4 requirement.
- API: `/health` reports `commit: 3b38a6f`. Live `GET
  /api/v1/predictions/2026_01_SF_LA/explanation` and
  `.../2026_02_IND_KC/explanation` both return correct, well-formed data
  (verified the approximate flag, `reproduction_max_diff`, `clean_forward`,
  top drivers, and family matchup on both).
- Frontend: deployed bundle confirmed by content (not just filename — the
  hash was coincidentally stable across the prior deploy, so filename alone
  wasn't proof) to contain `"Why this pick"`, `"Family matchup"`, and the
  exact endpoint path template `/api/v1/predictions/${e}/explanation`.
- **Not verified visually** — no browser/screenshot tool was available in
  this environment. Verification is: the bundle contains the exact panel
  code, the live API returns correct data for both example game_ids, and
  `tsc`/`vitest`/`vite build` all pass clean. That is strong but not the same
  as having looked at the rendered page.

## What's left open

1. **STAGE 1.2 item 5 — backtest-path wiring, not done.** `walk_forward.py` /
   `run_experiment.py` do not yet compute or store explanations for backtest
   folds. This was the highest-value remaining Stage-1 item cut for time —
   next session should do this before calling Stage 1 complete.
2. **`explain_interactions()` exists but is unused.** No caller (API or
   script) invokes it yet. STAGE 1.1 scoped this to the week-1 slate and
   backtest summaries only (never every live row).
3. **Week 1's genuine reproduction mismatch is unresolved.** Its stored
   explanations are labelled approximate, correctly, but nobody has found
   *why* week 1 (and only week 1) still doesn't reproduce inside the correct
   Linux image. Worth a dedicated look before trusting week-1's explanation
   numbers for anything beyond "roughly plausible."
4. **`league_pctile` is sometimes null for `_blend` features** (observed live
   on `home_qb_epa_under_pressure_blend` for a week-2 game) — the percentile
   rank computation in `backtests/explanations.py` doesn't handle NaN-heavy
   blend columns as gracefully as the base 23. Cosmetic, not a correctness
   bug (contribution/bias numbers are unaffected), but worth a look.
5. **ROADMAP.md and an ADR for the explanation method/table were not
   written this session** — the original prompt's standing instruction asked
   for both after each stage; this handoff exists per the explicit
   instruction to write it, but the other two were not requested in the same
   message and were not done. Flagging so they aren't silently skipped.
6. **The 29 pre-existing backend test failures** and the leftover
   `.git/worktrees/` Windows file-lock quirk (harmless, worked around) are
   unrelated pre-existing items, unchanged by this work.

## Standing instruction going forward

Any run whose numbers are evidence or must match production (reproductions,
backtests, grids) runs in the production Linux image, not on Windows. Stage 3
grids default to `--remote`.
