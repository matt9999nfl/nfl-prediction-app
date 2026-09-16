# TASK PROMPT — Carry prior-season data past week 1 (blended team features)

**For:** a new Claude Code session on Matt's Windows PC, repo at
`C:\Users\OEM\OneDrive\Desktop\nfl-prediction-app`
**Written:** 2026-09-15 (NZ) by the PROJECT-LEAD session
**Priority:** top. Matt's view: week-2 picks are useless until this is fixed.
**Hard deadline:** live before the week-2 Thursday game kicks off —
**Fri 18 Sep 12:15 NZST = Fri 18 Sep 00:15 UTC.**

You can run commands yourself. Do so. Matt wants you to run as much as possible
and hand him only the decisions.

---

## 0. Read first

1. `00-PROJECT-LEAD/PROJECT-CHARTER.md`. This is an app-building project. Work
   goes *through* the platform, not around it. There is no project-level 54%
   gate (ADR-006).
2. `00-PROJECT-LEAD/SESSION-HANDOFF-2026-09-14.md` §7, "Known traps". Traps 2, 4
   and 5 bite this task directly.
3. The files in §2 below, read in full before changing anything.

### How Matt wants to be talked to

- **When Matt must act or decide, put that first**, in a fenced block, with the
  stop/check condition directly next to it. Explanation goes after.
- **A hard STOP is its own message.** Don't bury it in a list of steps.
- Windows: `cmd.exe` syntax when you hand him commands.
- Be concrete. Don't pad.

---

## 1. The defect

Every per-team feature is **season-to-date within the current season only**.
Week 1 is filled with the team's full prior-season averages
(`_fill_week1_cold_start`). From week 2 onward the prior season is dropped
entirely:

| Week | What a team's features are built from |
|---|---|
| 1 | prior season, all ~17 games |
| 2 | **week 1 only, one game** |
| 3 | weeks 1–2 |

The result at week 2:

- Rate stats come from one game (~30–40 plays).
- `season_win_pct` is 0 or 1 for almost every team.
- `prior_week_margin` is just the week-1 score difference.
- The `MIN_PLAY_SAMPLE = 20` sufficiency flag never fires.

Live 2026 week-2 picks came out with 8 of 16 "high" confidence, against 1 of 16
in week 1. That is the symptom.

### Matt's decisions (already made — do not re-ask)

| Question | Decision |
|---|---|
| Approach | **Blended features go live.** Also add **separate prior-season features** as selectable catalog entries for future experiments. |
| Scope | **All team stats** (details and exceptions in §3). |
| Prior weight | Prior season counts as **N games' worth**. N is chosen by backtest from **{2, 4, 6, 8}**. |
| Go-live bar | Quick platform backtest against the current setup. **Log loss better in weeks 2–4 AND not worse overall.** ATS % is reported but does not decide. |
| Deadline | Before week-2 TNF, **Fri 00:15 UTC**. |
| Fallback | If the fix misses the deadline or fails the bar, **keep the week-2 picks but show a clear warning** that they rest on one game of 2026 data. |

---

## 2. Code map (verified 2026-09-15 at commit `6c962ac`)

| File | What matters |
|---|---|
| `02-MODELING/features/ol_metrics.py` | `compute_season_to_date_features()`: cumsum within `(team, season)` minus the current week, then rates, then `_fill_week1_cold_start()`, then sufficiency flags. Also has `_full_season_averages()`, `ALL_TEAM_RATE_FEATURES` (12), `GAME_CONTEXT_FEATURES`, and `build_game_feature_matrix()`. |
| `02-MODELING/features/comprehensive.py` | `ALL_ADDITIONAL_TEAM_FEATURES` = QB + NEW_RUN + NEW_DEF + FORM. Cumsum within season. FORM features use `shift(1).rolling(3)` **within the season only**. Has its own `_fill_week1_cold_start()`. |
| `02-MODELING/features/situational.py` | `SITUATIONAL_TEAM_FEATURES` = `rest_days`, `prior_week_margin`, `season_win_pct`. Week-1 defaults are 14, 0 and 0.5. |
| `02-MODELING/backtests/predict_upcoming.py` | Live forward predictions. `ALL_CURATED_TEAM_FEATURES` = the 23 per-team features. `generate_predictions()` builds the matrix, trains on all games before the target week, and predicts. `replace_week_predictions()` is followed by `grade_completed()` (DEFECT-3 fix). |
| `02-MODELING/backtests/run_production_refresh.py` | Cloud Run job `nfl-production-refresh`. Grades finished weeks, then predicts `next_unplayed_week()`. It never rewrites a finished week. |
| `02-MODELING/backtests/run_experiment.py` | Config-driven runner, `EXPERIMENT_CONFIG_ID=<uuid>`. `_build_all_curated_team_features()` computes every curated feature and then selects the columns listed in the config. |
| `02-MODELING/backtests/walk_forward.py` | `build_folds_from_config()` |
| `02-MODELING/backtests/test_predict_upcoming.py` | Existing tests. Follow their pattern. |
| `03-BACKEND-API/app/queries/features.py` | The feature catalog behind `GET /api/v1/features`. Find out where curated features are registered before adding any. |
| `03-BACKEND-API/app/queries/predictions.py` | `confidence_tier` is computed here from `ABS(p − 0.5)`: ≥0.10 high, ≥0.05 medium. |
| `04-FRONTEND/src/components/GameCard.tsx`, `src/pages/DashboardPage.tsx` | Where the fallback warning goes. Vitest is set up and CI now gates the frontend deploy on `npm run typecheck` and `npm test`. |

**Read `backtests/bq_writer.py` and the pydantic schemas before writing any
BigQuery code.** Writing against a schema remembered instead of read has caused
about four live failures (trap 5). Copy the `preflight()` pattern.

---

## 3. What to build

### 3a. Blended features (the live fix) — as NEW columns

**Do not change the meaning of any existing feature column.** The runner
computes every curated feature and selects by name, so redefining an existing
column silently changes every past and future experiment. Add new columns
alongside the old ones, e.g. `ol_sack_rate_blend`. The name is your choice;
keep it consistent and document it.

**Definition.** Prior season `S−1` enters as **N pseudo-games**, scaled from
that season's full-season totals:

```
prior_scaled_num = prior_season_total_num * N / prior_season_games
prior_scaled_den = prior_season_total_den * N / prior_season_games
blend_rate(W)    = (cum_num_through_W−1 + prior_scaled_num)
                 / (cum_den_through_W−1 + prior_scaled_den)
```

- **Week 1** has an empty current window, so the blend equals the prior-season
  rate. **Week-1 blended values must equal today's cold-start values.** Assert
  this in a test.
- As 2026 games accumulate, the prior's share fades (N=4: 80% at week 2, 50% at
  week 5).
- **No prior season** (2015, or a team with no prior row): use the same
  league-average fallback the cold-start uses today.
- Implement N as a **parameter**, not a constant. Four hard-coded copies is
  wrong.

**Per feature group:**

| Group | Treatment |
|---|---|
| 12 rate features (`ol_metrics`) | Count-based blend as above. |
| QB / NEW_RUN / NEW_DEF (`comprehensive`) | Count-based blend wherever the feature is a ratio of sums. If a feature is not a ratio of sums, blend its per-game mean with the prior-season per-game mean, weighted `games_played : N`. |
| FORM (rolling-3) | Let the window reach back into the prior season's final games, so week 2 uses week 1 plus the last 2 games of `S−1`. Document the choice. |
| `season_win_pct` | `(W + N * prior_win_pct) / (games_played + N)` |
| `prior_week_margin` | This is a last-game stat, not an aggregate. Keep the original, and add a blended **average point margin** as its counterpart. |
| `rest_days` | Schedule-derived, not performance. **No blend.** |

**Leakage rule, non-negotiable:** a feature for `(team, S, W)` may use only
season `S` weeks `< W` and season `S−1` (any week). Nothing from week `W`
onward.

**Out of scope:** roster, QB and coaching changes between seasons. Note this in
the ADR as a known limitation of the prior.

### 3b. Separate prior-season features (selectable, not live)

Add the prior season's full-season value of each of the 23 stats as its own
columns (e.g. `ol_sack_rate_prev`), plus a `games_played_this_season` column.
Register them in the feature catalog so the hypothesis chat can select them.

This also closes the capability gap from the 2026-09-09 hypothesis run: the
catalog could not express a lagged prior-season aggregate. Record it in
`platform.capability_gaps` as resolved, or add it and resolve it in the same
change.

### 3c. Tests — before any backtest

Add unit tests with small synthetic frames (no BigQuery) covering:

1. **Week-1 unchanged:** blended week-1 values equal current cold-start values.
2. **Fade:** week 2 with N=4 is 4/5 prior and 1/5 current, and so on.
3. **Leakage:** changing any week-`W` or later play does not change the
   week-`W` features.
4. **No-prior fallback:** a team with no prior season gets the league average.
5. **Old columns untouched:** existing features are byte-identical before and
   after your change on the same input.
6. **Win pct:** a 1–0 team at week 2 with a 0.25 prior and N=4 gives
   `(1 + 1.0) / 5 = 0.40`.

Run the existing modeling tests too. All must pass.

---

## 4. Backtest — through the platform

**Baseline:** create a **fresh** experiment config with the current 23 features
and run it now.

**Do NOT use any May-2026 experiment as a baseline, comparison or evidence.**
Matt considers every May run completely flawed and unreliable. The experiments
list still shows them (for example `v2-23base-faithful-2015-2024-rerun`).
Ignore them.

**Variants:** the same config with the blended features at N = 2, 4, 6 and 8.
Everything else is identical: model, seed, folds, seasons, and `n_jobs=1` for
reproducibility. Game-context features stay as they are. **Do not fold the roof
bug fix into this change** (see §8), so the comparison isolates one change.

**Folds:** walk-forward, 4 training seasons, 1-season test folds, test seasons
**2019–2025**. If the runner's end season stops at 2024, extend it to 2025 and
say so.

**Selecting N without fooling ourselves:**

1. **Tuning seasons 2019–2022:** pick the N with the lowest log loss in
   **weeks 2–4**.
2. **Confirmation seasons 2023–2025**, chosen N only: apply the bar.

**The bar**, applied on 2023–2025 and decided in advance:

- Log loss in **weeks 2–4** is **lower** than baseline, **AND**
- Log loss over **all weeks** is **not higher** than baseline.

Log loss must come from the stored per-game probabilities in
`experiments.backtest_predictions`. Compute it yourself if the runner doesn't.
Pushes and games with a null label are excluded.

**Report to Matt as a table**, with the numbers for each of the three seasons
2023–2025 as well as combined:

- log loss for weeks 2–4 and for all weeks;
- ATS % for weeks 2–4 and for all weeks;
- the share of picks at ≥0.10 from 50% in week 2;
- games counted.

ATS is context only. State plainly whether the bar was met.

**Running experiments:** the Cloud Run job `nfl-experiment-runner` still runs an
**older image** that doesn't contain your code. Either run
`run_experiment.py` locally with the config IDs (it still writes the platform
records), or rebuild that job's image. Check the timing before you choose.
Either way, the runs must exist as experiment records.

**STOP after the report.** Matt decides go or no-go. Put the decision request
first, on its own.

---

## 5. Go-live (only after Matt says go)

1. Switch `predict_upcoming.py`'s live feature list to the blended columns at
   the chosen N. Keep everything else the same.
2. Update `build_config_payload()` so the production config row records the new
   feature list and N.
3. Run the tests, commit and push. **Committing does not deploy modeling code**
   (trap 2).
4. Rebuild and repoint the live job:
   ```
   cd 02-MODELING
   gcloud builds submit --config cloudbuild.yaml .
   gcloud run jobs update nfl-production-refresh --region us-central1 --image gcr.io/nfl-model-471509/nfl-experiment-runner@sha256:<digest from the build>
   gcloud run jobs describe nfl-production-refresh --region us-central1 --format=yaml
   ```
   Pin the **digest** and confirm it in `describe`. The job must still run
   `python backtests/run_production_refresh.py`.
5. **Regenerate week 2:**
   `gcloud run jobs execute nfl-production-refresh --region us-central1 --wait`
6. Verify against the live API, not the logs:
   - `/api/v1/predictions?season=2026&week=2` has 16 rows with a fresh
     `generated_at`, and the confidence spread has come down.
   - `/api/v1/predictions?season=2026&week=1` is unchanged: 15 graded, 12 wins,
     3 losses, the NE@SEA push ungraded.

### Hard timing rule

**Never regenerate week 2 after Fri 00:15 UTC (Fri 12:15 NZ).**

- `next_unplayed_week()` still returns 2 after the Thursday game finishes.
- A regeneration after kickoff rewrites a played game's pick using hindsight.

If go-live isn't finished by then, stop and tell Matt. Do not execute the job.
The only exception is if Matt explicitly accepts that the TNF pick changes. If
he does, the TNF game's pick must be excluded or flagged in the record.

---

## 6. Fallback warning — build this FIRST, as insurance

Build it before the backtest work, so it's ready either way.

On the dashboard, when the week shown is **week 2 or earlier in a season**,
show a clear note next to the picks along these lines:

> "These picks are built on one game of 2026 data per team. Treat them as
> low-information."

- Wording is flexible. Keep it honest and short.
- Add a vitest test for when the note appears.
- **Ship it now.** It's true today regardless of the fix.
- Once blended features are live, change it to say what the picks are built on
  (for example "blended with last season"), or remove it. Tell Matt which you
  did.

---

## 7. Paperwork, in the same change set

- **New ADR in `docs/DECISIONS.md`:**
  - the defect;
  - the blend definition and the chosen N;
  - the pre-declared bar and its result;
  - the roster-change limitation;
  - that old feature columns are unchanged.
- **`platform.capability_gaps`:** the prior-season gap (see §3b).
- **Short handoff note in `00-PROJECT-LEAD/`:** what shipped, the image digest,
  the experiment IDs, and anything left open.

---

## 8. Out of scope — note these, don't fix them here

- **Roof bug:** `roof_dome` checks for `retractable`, but the data uses
  `closed` or `open`, so closed-roof games are treated as outdoor. It's a
  separate change.
- **Weather mismatch:** `temp` and `wind` are blank for unplayed games and get
  the median and 0 at prediction time, while training used actual game-day
  weather.
- **Confidence tiers are uncalibrated.** They're a fixed distance from 50%.
- **Retired framing:** `success_threshold: 0.54` is still written by
  `predict_upcoming.py` (charter A-1). Don't touch it unless you're already
  editing that function, and if you do, say so.

---

## 9. Checkpoints to Matt

1. **Plan confirmed:** new column names, the treatment per feature group, and
   how N is plumbed through. Short, then proceed unless something in §3 turns
   out to be wrong in the code.
2. **Fallback warning live.**
3. **Tests green.**
4. **Backtest report**, then a **hard STOP** for go or no-go.
5. **Go-live verified**, with the API checks from §5.6.

If anything in this prompt contradicts the code, the code wins. Tell Matt
what's different before you act on it.
