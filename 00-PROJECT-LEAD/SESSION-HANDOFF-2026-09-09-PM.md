# Session handoff — 2026-09-09 (afternoon/evening)

**Written by:** Cowork session with Matt · **Covers:** deploy unblocking, forward prediction, line capture
**Previous:** `SESSION-HANDOFF-2026-09-09.md` (the INC-002 / Phase 6 session)

---

## What this session was for

Matt's ask: *"get the changes made within this app live as soon as possible and get the app up and running with the ability to make predictions for week 1 of the 2026 season."*

Both halves turned out to be blocked by things nobody knew were broken.

---

## Part 1 — the deploy had never worked

`/health` had reported `"commit":"unknown"` for as long as anyone could check, and
`DELEGATIONS.md` recorded the live API as arriving via *"an unrelated API rebuild
on 2026-09-08"*. Those two facts were the same fact.

**The GitHub Actions deploy workflow could never shift traffic.** Two bugs, both
in steps added to make the deploy *safer*:

| # | Bug | Effect |
|---|---|---|
| 1 | The smoke-test step tested `steps.smoke-test.outputs.smoke_test_passed` — **its own output** — from inside itself | GitHub interpolates `${{ }}` before the step runs, so it was always `""`, `[ -z "" ]` was always true, and `exit 1` fired on every run **including runs where `/health` returned 200** |
| 2 | `gcloud run revisions describe --format='value(status.url)'` | A revision has no addressable URL. `$url` was empty, so the smoke test curled nothing 30 times before failing |

So every deploy that ever *landed* came through the ad-hoc Cloud Build path —
which passed no `--build-arg GIT_COMMIT`, baking `unknown` into the image. That
is the whole explanation for "which code is running?" taking a week during
INC-002.

**Fixed:** the new revision deploys with `--tag candidate` (a real traffic-free
URL), the smoke test uses a plain shell variable, and verification hits the
*service* URL — not the candidate tag, which would answer 200 whether or not
traffic moved — and asserts `/health` reports the commit just built.

`cloudbuild.yaml` now passes `GIT_COMMIT` too, so the ad-hoc path cannot
reintroduce `unknown`.

**Verified:** `/health` returned `{"status":"ok","version":"0.1.0","commit":"c4b4dd7"}`.
First time this repo has been able to answer that question.

### Also shipped in the same push

- The six accepted **HC-S6-FIX** defects, which had been sitting uncommitted
  while F1 (`update_answers` never clearing `approved_hash` in SQL) ran live in
  production.
- Frontend: the dashboard now calls `/api/v1/predictions` and renders
  `EvaluationBanner`. Confirmed in the deployed bundle at `34.49.20.115`.

### Standing gap, not fixed

**CI does not run the test suite.** It builds, deploys at 0%, curls three
endpoints, shifts traffic. The 91 backend tests have never gated a deploy.

Related: **the backend tests cannot run without GCP credentials.** They 500 on
`DefaultCredentialsError` because `get_bq_client` resolves before request
validation — so even `test_get_predictions_missing_season`, which only asserts a
422, fails outside a credentialed environment. Fixing that is a prerequisite for
CI running them at all.

---

## Part 2 — forward prediction (O-2 / DEC-A), now built

`PRE_SEASON_STATUS_2026-08-31.md` §2 said it plainly: *"Nothing in the current
plan produces a prediction for a 2026 game."* DEC-A made it an active project
the same day. It was never dispatched, and INC-002 consumed the nine days after.

**Matt's correction, recorded:** he intended live 2026 prediction to be ready for
the season start, and considers D-5's removal of it from the chat build a
mis-scoping. DEC-A already reverses it; the failure was dispatch, not decision.

### The obstacle

`compute_season_to_date_features()` derives its `(team, season, week)` universe
**from the plays table**. An unplayed week has no plays, so it produces no
team-week rows, and `build_game_feature_matrix()`'s left join returns NaN for
every feature. The week-1 cold-start fill cannot help — there is no row to fill.

### The approach

`02-MODELING/backtests/predict_upcoming.py` appends **zero-valued placeholder
plays** for the slate's teams rather than forking the feature builders:

- the placeholder puts `(team, season, week)` into the universe;
- the cumulative step is `cum - current_week`, so the placeholder's own zeros
  subtract straight back out and contribute nothing;
- no later week exists, so nothing downstream is polluted;
- for week 1 the existing cold-start fill then substitutes prior-season
  averages — **the same treatment week 1 received in every backtest**, so the
  model is asked the shape of question it was validated on.

**Verified live: 0.0% feature null rate on the 2026 week-1 slate**, trained on
2,822 completed games (2015–2025), 16 games predicted.

Guards: refuses to write above 50% null features; re-running a week replaces
that week's rows rather than leaving two generations; `--grade` backfills results.

### Serving

`GET /api/v1/predictions` required `gate_passed = true` and no experiment has
ever passed, so it could never return anything. Per DEC-C, gate-passing is not a
prerequisite for a forward prediction but the honest-evaluation banner is.

Selection order is now: override (constrained to gate-passed **or** the
configured production experiment, so the endpoint cannot be pointed at
`test3-shuffle-labels-leakage-test` via query string) → most recent gate-passed →
configured production experiment, ungated.

`ProductionPredictionsResponse.gate_passed` is **required with no default**. A
default of `False` would be safe today and forgotten tomorrow.

---

## Part 3 — the finding that matters most

**The model never sees the betting line.**

`home_spread_close` builds the `home_covered` label and is printed in output. It
is **not** in the feature set. The 52 features are 23 team metrics × 2, plus
`home_advantage`, `div_game`, `roof_dome`, `temp`, `wind`, `rest_differential`.

So the model is asked *"does the home team beat the closing line?"* while
structurally unable to distinguish −9.5 from −1.

The consequence for the project's premise is direct. The hypothesis is that
**markets undervalue OL performance**. "Undervalued" is a claim about a gap
between reality and the market's price — and the model is never shown the price.
It can only say "this team looks strong", which is a different claim from "this
team is underpriced". A discrepancy with an unseen number is not detectable.

This is the most plausible single explanation for every experiment landing at
48–51% regardless of feature set. Rush features, situational slices, 23 or 52
features — all flat, which is what you would expect if the target is defined
relative to information the model does not have.

**Caveats, stated honestly:** it may be deliberate (feeding the spread risks the
model learning "favourites cover half the time"), and no ADR records either
choice. Adding it is an experiment, not a fix — it may well come back flat, but
flat for a reason that was actually tested.

**Recommended as the first experiment after week 1 ships.** It needs no new data:
every game since 1999 already carries the column.

---

## Part 4 — line capture

Matt's call: nflverse only, opening and closing spread.

**nflverse has no opening-line field.** One `spread_line`, verified against the
schedules data dictionary. So "opening" can only mean "first value we captured".

**The blocker was the schema, not the source.** `raw_nflfastr.schedules` is
DROPPED and rebuilt every run; `curated.games` holds one spread per game in an
overwritten column. There was nowhere to put a second observation. No vendor
would have fixed that.

`raw_lines.line_snapshots` is an append-only change-log — a row lands only when a
game's market data differs from its last stored row. First row = first line seen,
last row = last. Hooked into the end of step 1, so no step renumbering and
`--start-at` keeps working. Existing 4×/week cadence (Tue 11:00, Fri 05:00,
Mon 05:00, Tue 07:00 UTC) is enough: Tuesday is the first look, and the post-game
run holds the settled number.

**Also captures what was being thrown away:** `home_moneyline`, `away_moneyline`,
`home_spread_odds`, `away_spread_odds`, `over_odds`, `under_odds`. The moneyline
converts to the market's implied win probability — the honest baseline any model
here should be measured against.

Naming: the derived column is `home_spread_first_seen`, **not**
`home_spread_open`. Books post Sunday evening; the pipeline first looks Tuesday.
Calling it "open" would make it the third column here meaning something other
than what it says — see `home_spread_close`, which holds a **live** value for any
game that has not kicked off.

### Two sign-convention notes

1. `audit_closing_lines.py` said *"negative = home favored"*. **That is
   backwards.** nflverse: positive = home favoured. Verified against 2026 week 1
   (PHI 5.5 over WAS, DET 7.0 over NO, BAL −3.5 at IND). Corrected.
   `derive_home_covered()` always used the correct convention, so **no label was
   ever wrong** — but a comment contradicting the label logic one file away is a
   trap, and INC-001 was a label inversion.

2. `home_spread_close` for an unplayed game is **not** a closing line. It is
   whatever nflverse held at last run, and it changes before kickoff. The column
   means two different things depending on when it is read.
   `predict_upcoming.py` stores the spread **as it stood at prediction time**,
   which combined with the settled close gives closing-line value for free — a
   far better measure than ATS hit rate over 16 games.

---

## State at handoff

| Item | State |
|---|---|
| HC-S6-FIX six defects | ✅ Live |
| `/health` real commit SHA | ✅ Live (`c4b4dd7`) |
| Deploy workflow | ✅ Fixed, both workflows green |
| Dashboard + banner | ✅ Live in the deployed bundle |
| Ungated prediction serving | ✅ Live |
| `predict_upcoming.py` | ✅ Verified — 16 games, 0.0% null |
| **Week 1 predictions written** | ❌ **Not done** |
| `snapshot_lines.py` | ⚠️ Fixed after a live failure; **not committed** |

### Immediate next step

```
cd 02-MODELING
python backtests\predict_upcoming.py --season 2026 --week 1
```

Then confirm `/api/v1/predictions?season=2026&week=1` returns games, not a 404.

The first attempt at this was chained behind `snapshot_lines.py` with `&&`, and
the snapshot failed, so the predictions never ran. **Run the prediction command
on its own.**

### Uncommitted on the machine

`01-DATA-PIPELINE/scripts/snapshot_lines.py` (fixed) and
`01-DATA-PIPELINE/scripts/test_snapshot_lines.py` (new, 12 tests, all pass).

The live failure was:

```
400 Query column 3 has type FLOAT64 which cannot be inserted into column week,
which has type INT64
```

`raw_nflfastr.schedules` is loaded with schema autodetect from pandas, and pandas
represents a nullable integer column as float64 — so `week` and every moneyline
and odds field arrive as `FLOAT64`. Every column is now `SAFE_CAST` to its
declared target type, and `FIELD_TYPES` sits beside `MARKET_FIELDS` so the cast
and the table schema cannot drift.

Worth noting for the pattern file: **this is the seventh defect in three days of
the same shape — code that had never met real data.** It compiled, its logic was
sound, and it failed on the first contact with a real column type.

### Queue

1. Write week 1 predictions (above)
2. Commit + push the snapshot fix
3. `--grade` week 1 after Sunday
4. Spread + moneyline as features — Part 3
5. Make backend tests runnable without credentials, then have CI run them
6. Derive `home_spread_first_seen` into `curated.games`; add closing-line value
7. `ROADMAP.md` still stale — last updated 2026-08-31, still says "Phase 5
   complete", knows nothing of INC-002 or any of the above. It is the first
   document a cold session reads.

### Scheduled

A task fires **Friday 2026-09-11 08:00 UTC** (20:00 NZ) to run the pbp
season-count query, confirm a 2026 row near ~2,700 plays, and report back — the
check `DP-REVIEW` flags as the one thing no alert can catch, because a silently
skipped season generates no check and reports `ALL CHECKS PASSED`.
