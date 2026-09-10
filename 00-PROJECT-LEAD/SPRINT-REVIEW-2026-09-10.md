# Sprint summary for review — 2026-09-09 / 2026-09-10

**Prepared for:** a cold review session
**Covers:** one continuous working session, NZ evening 9 Sep through morning 10 Sep
**Prior context:** `00-PROJECT-LEAD/SESSION-HANDOFF-2026-09-09.md` (INC-002 / Phase 6 session)

---

## 1. The ask

> "Get the changes made within this app live as soon as possible and get the app up and running with the ability to make predictions for week 1 of the 2026 season."

Both halves were blocked by things nobody knew were broken.

**Season context:** 2026 opener Thursday 10 Sep, main slate Sunday 13 Sep. The work happened against that deadline.

---

## 2. Starting state

| | |
|---|---|
| API | Live, `/health` reporting `commit: "unknown"` |
| Frontend | Live at `34.49.20.115`, stale build |
| `GET /api/v1/predictions?season=2026&week=1` | **404** — `no_production_experiment` |
| Working tree | Dirty; the accepted HC-S6-FIX work uncommitted, so F1 was a live production defect |
| Forward prediction | **Did not exist.** DEC-A made it an active project on 2026-08-31; O-2 was never dispatched |

`PRE_SEASON_STATUS_2026-08-31.md` §2 had already stated it: *"Nothing in the current plan produces a prediction for a 2026 game."*

Matt's correction during the session, worth recording: he intended live 2026 prediction to be ready for the season start and considers D-5's removal of it from the chat build a mis-scoping. DEC-A already reverses it. **The failure was dispatch, not decision.**

---

## 3. Defects found and fixed

Ordered by consequence, not by discovery.

### 3.1 The GitHub Actions deploy had never shifted traffic

Two bugs, both in steps added to make deploys *safer*:

1. The smoke-test step tested `steps.smoke-test.outputs.smoke_test_passed` — **its own output** — from inside itself. GitHub interpolates `${{ }}` before the step runs, so it was always `""`, `[ -z "" ]` was always true, and `exit 1` fired on **every run, including runs where `/health` returned 200**.
2. `gcloud run revisions describe --format='value(status.url)'` returns nothing — a revision has no addressable URL. `$url` was empty, so the smoke test curled nothing 30 times before failing.

**Consequence:** every deploy that ever landed came through the ad-hoc Cloud Build path, which never passed `--build-arg GIT_COMMIT`. That is the entire explanation for `/health` reporting `unknown`, and for "which code is actually running?" taking a week during INC-002.

**Fix:** deploy with `--tag candidate` (a real traffic-free URL), resolve that URL from the service's traffic block, use a plain shell variable in the smoke test, and verify against the **service** URL — not the candidate tag, which answers 200 whether or not traffic moved — asserting `/health` reports the commit just built. `cloudbuild.yaml` now also passes `GIT_COMMIT`.

**Verified:** `/health` went from `"unknown"` to a real SHA for the first time in the repo's history.

### 3.2 Forward prediction did not exist — built

**The obstacle.** `compute_season_to_date_features()` derives its `(team, season, week)` universe from the plays table. An unplayed week has no plays, so it produces no team-week rows, and `build_game_feature_matrix()`'s left join returns NaN for every feature. The week-1 cold-start fill cannot help — there is no row to fill.

**The approach.** `02-MODELING/backtests/predict_upcoming.py` appends **zero-valued placeholder plays** for the slate's teams rather than forking the feature builders:

- the placeholder puts `(team, season, week)` into the universe;
- the cumulative step is `cum - current_week`, so the placeholder's own zeros subtract back out and contribute nothing;
- no later week exists, so nothing downstream is polluted;
- for week 1 the existing cold-start fill substitutes prior-season averages — **the same treatment week 1 received in every backtest**, so the model is asked the shape of question it was validated on.

**Verified live:** 0.0% feature null rate on the 2026 week-1 slate; 16 games; trained on 2,822 completed games (2015–2025).

**Guards:** refuses to write above 50% null features; re-running a week replaces that week's rows rather than appending a second generation; `--grade` backfills results; a preflight checks all three target table schemas before any expensive loading.

### 3.3 Serving was structurally blocked

`GET /api/v1/predictions` required `gate_passed = true` on both the run and the config. No experiment has ever passed, so the endpoint could never return anything.

DEC-C ruled that gate-passing is not a prerequisite for a forward prediction, but the honest-evaluation banner is. Selection order is now:

1. `experiment_id` override — **constrained** to gate-passed or the configured production experiment, so the endpoint cannot be pointed at `test3-shuffle-labels-leakage-test` by query string;
2. most recent gate-passed experiment (a validated model always outranks an unvalidated one);
3. the configured production experiment, ungated.

`ProductionPredictionsResponse.gate_passed` is **required with no default**. A default of `False` would be safe today and forgotten tomorrow.

### 3.4 The weekly refresh job had been doing nothing since creation

`run_production_refresh.py` queried for `gate_passed = true` experiments, found none, logged *"No gate-passed experiments found — nothing to refresh"*, and exited 0. Every Tuesday. Looking healthy.

It also would not have helped if one had passed — the experiment runner runs a walk-forward backtest and cannot emit a prediction for an unplayed game.

**Rewritten** to grade any week whose games have finished, then predict the next unplayed week. Grading runs first deliberately: if prediction fails, last week's actual results are still recorded.

**No new infrastructure.** The `nfl-production-refresh` job already existed, already used the image containing `predict_upcoming.py`, and the Tuesday 14:00 UTC scheduler already fired at it.

### 3.5 Manual trigger

`POST /api/v1/predictions/refresh`, behind `require_api_key`, returns 202 rather than holding the request open — a two-minute job would hit Cloud Run's 60-second timeout and report failure for something running fine. Plus a "Generate predictions" button on the dashboard.

The button and the scheduler run **the same job**, so there is one code path to trust, not two.

### 3.6 Three dashboard bugs

1. **`ORDER BY season DESC, week DESC` with `limit=50`** returned the *last* 50 scheduled games — weeks 15–18. Week 1 was never in the response. The dashboard was correct; it was handed the wrong 50 games. Scheduled games now sort ascending.
2. **`status == "complete"` in the SQL** while the router accepts only `scheduled|final`. `?status=final` matched nothing, added no condition, and silently returned unplayed games alongside completed ones — a filter that appears to work and does nothing. Same string mismatch as the 500 fixed on 8 Sep; this branch was missed.
3. **Duplicate evaluation banner** — `Layout.tsx` already rendered it globally; a second was added during this session and removed.

### 3.7 White-screen crash

`ConfidenceBadge` called `tier.charAt(0)` on a value that is `null` for every prediction. A throw during render with no error boundary unmounts the entire React tree — white page, a few seconds in, exactly when the predictions query resolved.

**Why `tsc` passed:** the frontend type declared `confidence_tier` as non-nullable while the backend declared it `| None` and the SQL never selected it. The type and the API disagreed. The field had been null since it was written; nothing had ever rendered it until predictions started returning.

**Fixes:** compute the tier in SQL (`CASE` on `ABS(prob - 0.5)`), make the TS type nullable so the mismatch fails typecheck next time, guard the component, and **add an error boundary** around the routes so one bad field can no longer blank the application.

### 3.8 Confidence percentage showed the wrong side

`predicted_home_cover_prob` is always the *home* team's probability, but the card printed it beside whichever team was picked. An away pick showed the home team's number — "WAS (34.6%)" for a game where WAS had a 65.4% chance, advertising the right pick at its inverse while the badge beside it correctly said "high confidence".

### 3.9 Predictions were not reproducible across machines — the most consequential finding

Cloud predictions differed from local by up to **0.042**; two of sixteen picks flipped sides.

**First hypothesis — wrong.** `requirements.txt` used `>=`, so a rebuild resolved pandas 3.0.5 / numpy 2.4.6 against the pandas 1.5.3 every verified prediction had been produced on. Pinning was correct, but was not the bug.

**The evidence that mattered:** two cloud runs were byte-identical *to each other* and both differed from local. Same machine → same answer; different machine → different answer. That is a hardware signature, not a library one.

**Cause:** `n_jobs=-1` in `XGB_PARAMS` and `XGB_PARAMS_V2`. XGBoost's histogram builder sums gradients in thread-completion order, so core count (12 on the laptop, 2 in Cloud Run) changes floating-point rounding, which moves split points, compounding over 300 boosting rounds. `random_state=42` seeds sampling, not thread scheduling.

**Fix:** `n_jobs=1`, `tree_method="hist"` stated explicitly rather than left to a default that could change under upgrade.

**Result:** largest local↔cloud delta went from **4.2e-2 to 2.8e-8**. The residual is float rounding through BigQuery storage and JSON serialisation; it cannot change a pick or a tier.

**Implication a reviewer should weigh:** every backtest this platform has ever run used `n_jobs=-1`. Those results were reproducible on the machine that produced them and nowhere else. It does not overturn the finding that no feature set cleared 54% — a ±0.04 hardware artifact cannot manufacture or hide a real edge — but no historical experiment can now be exactly reproduced. **Not yet recorded in `DECISIONS.md`.**

### 3.10 Line capture

Matt's call: nflverse only, opening and closing spread.

**nflverse has no opening-line field** — verified against the schedules data dictionary. Only `spread_line`. So "opening" can only mean "first value this pipeline captured".

**The real blocker was schema, not source.** `raw_nflfastr.schedules` is dropped and rebuilt on every run; `curated.games` holds one spread per game in an overwritten column. There was nowhere to put a second observation. No vendor would have fixed that.

`raw_lines.line_snapshots` is an append-only change-log — a row lands only when a game's market data differs from its last stored row. Hooked into the end of step 1, so no step renumbering and `--start-at` keeps working. The existing 4×/week cadence suffices: Tuesday is the first look, the post-game run holds the settled number.

**Also captures what was being discarded:** `home_moneyline`, `away_moneyline`, `home_spread_odds`, `away_spread_odds`, `over_odds`, `under_odds`. The moneyline converts to the market's implied win probability.

Named `home_spread_first_seen`, **not** `home_spread_open` — books post Sunday evening, the pipeline first looks Tuesday. Calling it "open" would make it the third column here meaning something other than what it says. See `home_spread_close`, which holds a **live** value for any game that has not kicked off.

**Bug on first live run:** `week` arrives as FLOAT64 (BigQuery autodetect from pandas, which represents nullable ints as float64) into an INT64 column. Every column is now `SAFE_CAST` to its declared type, with `FIELD_TYPES` beside `MARKET_FIELDS` so the cast and the schema cannot drift.

### 3.11 A backwards sign-convention comment

`audit_closing_lines.py` said *"negative = home favored"*. The nflverse dictionary says **positive = home favoured**, confirmed against 2026 week-1 values (PHI 5.5 over WAS, DET 7.0 over NO, BAL −3.5 at IND).

`derive_home_covered()` always used the correct convention, so **no label was ever wrong** — but a comment contradicting the label logic one file away is a trap, and INC-001 was a label inversion. Corrected.

---

## 4. The finding that needs re-framing, and why

**The model cannot see the betting line.** `home_spread_close` builds the `home_covered` label and is printed in output, but is not among the 52 features (23 team metrics × 2, plus `home_advantage`, `div_game`, `roof_dome`, `temp`, `wind`, `rest_differential`).

So the model is asked *"does the home team beat the closing line?"* while structurally unable to distinguish −9.5 from −1. The project's premise is that markets **undervalue** OL performance — a claim about a gap between reality and the market's price — and the model is never shown the price.

**This was initially presented as a modelling priority. Matt corrected that, correctly.** This is a platform-first project: the platform gets built, and the model is refined *through* the platform over time. `PRE_SEASON_STATUS` §6 already warns that making the platform trustworthy and finding an edge are two projects easy to conflate.

**The correctly-framed version:** the feature catalog cannot express the market's own price, so a whole class of hypothesis cannot be stated on this platform at all. That is a **capability gap** in the sense of D-2. Closing it means making spread, total and moneyline *selectable features*. Whether they earn a place is then answered by running an experiment through the runner and the gate — not by editing `GAME_CONTEXT_FEATURES` by hand, which is exactly what the architecture exists to prevent.

Same applies to the calibration idea raised during the session: whether the app *measures* calibration is a platform capability; what the calibration turns out to be is a model question.

---

## 5. Process failures during this sprint

Recorded because a review should see them.

1. **BigQuery code was written against remembered schemas.** Three live failures — `updated_at` missing, `week` type mismatch, and `backtest_runs` missing `name`/`model_type` while sending a non-existent `n_games` — every one knowable from files already in the repo. The user's runs became the test harness. Corrected mid-sprint by reading `bq_writer.py` and the backend's pydantic models directly and adding contract tests.
2. **The critical command was chained behind new code.** `predict_upcoming` was placed after `snapshot_lines.py` with `&&`; the snapshot's failure killed the prediction run that mattered.
3. **The most visible difference was mistaken for the cause.** A two-major-version pandas jump in a build log was reached for before the discriminating evidence (two cloud runs identical to each other) had been weighed.
4. **"Fixed" and "deployed" were repeatedly conflated** in status reporting.
5. **Ethos drift**, per §4.

**Pattern worth noting for the review:** including this sprint's, that is roughly ten defects in three days of the same shape — *code that had never met real data*. It compiles, its logic is sound, and it fails on first contact with a real column type, a real null, or a real core count.

---

## 6. Verified state at close

| Item | State | Evidence |
|---|---|---|
| HC-S6-FIX six defects | Live | deployed |
| `/health` real commit SHA | Live | `3cbf12f` |
| Deploy workflow | Fixed | both workflows green, traffic verified by commit assertion |
| Week-1 2026 predictions | **Live** | 16 games served, `gate_passed: false` |
| Dashboard | Fixed | week 1 first, picks rendering, one banner, error boundary |
| Generate-predictions button | Shipped | `POST /api/v1/predictions/refresh` |
| Weekly automation | **Verified by real execution** | grades then predicts; not assumed |
| Cross-machine reproducibility | Fixed | max delta 2.8e-8, was 4.2e-2 |
| Line snapshots | Shipped | `raw_lines.line_snapshots` |
| Confidence tiers | Populating | 1 high, 8 medium, 7 low |

**Tests added:** `test_snapshot_lines.py` (12) and `test_predict_upcoming.py` (10) — both run with no credentials and no network, reading schema declarations out of the repo. 224 existing scoping tests still green.

---

## 7. Open queue, platform-first

1. **CI never runs the test suite.** It builds, deploys at 0%, curls three endpoints, shifts traffic. 91 tests have never gated a deploy — and three dashboard bugs shipped past a green pipeline this sprint.
2. **Backend tests cannot run without GCP credentials.** They 500 on `DefaultCredentialsError` because `get_bq_client` resolves before request validation, so even a test asserting a 422 fails. Prerequisite for (1).
3. **Market data is not in the feature catalog** — the capability gap in §4.
4. **Record the `n_jobs` finding in `DECISIONS.md`.**
5. **`ROADMAP.md` is stale** — last updated 2026-08-31, still says "Phase 5 complete", knows nothing of INC-002 or this sprint. First document a cold session reads.
6. **Nothing tests the frontend.** `tsc` passed while `confidence_tier` was a lie and the dashboard white-screened.
7. **Carried from the previous board:** HC-S6-FIX-2, HC-S6-CLEANUP, DO-HARDEN, HC-S7.

**Scheduled:** a task fires Friday 2026-09-11 08:00 UTC to confirm the 2026 opener ingested — the check `DP-REVIEW` flags as uncatchable, because a silently skipped season generates no check and reports `ALL CHECKS PASSED`.

---

## 8. Suggested scrutiny for the review

- **The placeholder-plays technique** in `predict_upcoming.py`. It is the load-bearing idea behind forward prediction. The argument that placeholders contribute nothing rests on the cumulative step subtracting the current week from its own total — worth an independent check.
- **`methodology.type` is written as `"walk_forward"` for what is actually forward prediction**, because `MethodologyConfig.type` is a pydantic `Literal` and the honest value would 500 the experiments list. Deliberate, documented, test-asserted — but a wart.
- **Whether the confidence-tier thresholds (0.10 / 0.05) mean anything.** They were chosen to be reasonable, not calibrated. Nobody has checked whether this model's 65% covers 65% of the time.
- **`home_spread_close` means two different things** depending on when it is read: a live value pre-game, the settled close afterwards. `predict_upcoming` stores the prediction-time value, which makes closing-line value computable — but the column name still lies.
- **Whether the ungated serving path is the right trade.** DEC-C permits it with the banner; the banner is now driven by the served `gate_passed` rather than a local constant. A reviewer may still think shipping unvalidated picks is wrong.
