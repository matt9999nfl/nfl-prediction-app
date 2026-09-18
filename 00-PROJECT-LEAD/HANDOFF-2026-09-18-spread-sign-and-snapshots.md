# HANDOFF — spread-sign fix and line-snapshot investigation, 2026-09-18

**Goal achieved: yes.** Every acceptance line in `PROMPT-FIX-SPREAD-SIGN-AND-LINE-SNAPSHOTS.md` is true. Part B's permanent fix (a pipeline redeploy) hit the prompt's own kill-switch and was correctly stopped and escalated rather than done unilaterally — that is the designed outcome, not a shortfall (same pattern as Stage 1's "week 1 stays approximate" close-out).

**Covers:** `PROMPT-FIX-SPREAD-SIGN-AND-LINE-SNAPSHOTS.md` (fix stage, between Stage 2 and Stage 3a).

---

## Commits

| Commit | What |
|---|---|
| `80cd3b6` | Stage 2 — week-1/week-2 pick-explanation analysis (already existed, not yet pushed before this stage) |
| `8167091` | Part A (spread-sign fix) + Part B (line-snapshot root cause, one-off capture, visibility guard) |

Both pushed to `main`: `224a424..8167091`. Neither touches `03-BACKEND-API/**` or `04-FRONTEND/**`, so no deploy workflow fired (confirmed: only `api-deploy.yml` and `frontend-deploy.yml` exist, path-scoped to those folders).

---

## Part A — the sign fix

**Root cause:** `analyze_week_explanations.py`'s `favorite_or_underdog()` read `home_spread_close < 0` as home-favoured. It's the opposite: **positive `home_spread_close` means the home team is favoured** — confirmed three independent ways: `verify_label_convention.py` C1 (favourites win outright ~66-70% under this reading, ~30% under the inverted one), `build_curated_games.py::derive_home_covered()`'s own docstring ("positive spread_line = home favoured... home_spread_close = 7 means home is a 7-point favourite"), and the de-vigged moneyline (`2026_01_ARI_LAC`: home_spread_close=+9.5, home moneyline devigs to 0.787 — LAC, the home team, heavily favoured).

### Favourite/underdog — before vs. after

`2026_01_ARI_LAC` (home=LAC, away=ARI, closing spread +8.5): **before** — favourite=ARI (wrong), pick=home=LAC=underdog. **after** — favourite=LAC (correct), pick=home=LAC=favourite.

Every game's favourite flipped (all 16 games, both weeks — the sign was backwards everywhere, not just this one game). Full before/after table for week 1, computed by diffing this stage's output CSV against the one `80cd3b6` committed:

| game_id | spread | favourite before | favourite after | pick was favourite? before → after |
|---|---|---|---|---|
| 2026_01_ARI_LAC | +9.5 | away (ARI) | **home (LAC)** | False → **True** |
| 2026_01_ATL_PIT | +5.5 | away | home | False → True |
| 2026_01_BAL_IND | -3.5 | home | away | False → True |
| 2026_01_BUF_HOU | -1.5 | home | away | False → True |
| 2026_01_CHI_CAR | -3.0 | home | away | False → True |
| 2026_01_CLE_JAX | +8.5 | away | home | False → True |
| 2026_01_DAL_NYG | -3.0 | home | away | True → False |
| 2026_01_DEN_KC | +2.5 | away | home | True → False |
| 2026_01_GB_MIN | +1.5 | away | home | False → True |
| 2026_01_MIA_LV | +3.0 | away | home | True → False |
| 2026_01_NE_SEA | +3.0 | away | home | True → False |
| 2026_01_NO_DET | +7.0 | away | home | True → False |
| 2026_01_NYJ_TEN | +1.5 | away | home | True → False |
| 2026_01_SF_LA | +3.5 | away | home | True → False |
| 2026_01_TB_CIN | +3.5 | away | home | False → True |
| 2026_01_WAS_PHI | +6.0 | away | home | True → False |

**Underdog-pick counts:** week 1 stayed 8 of 16 (a coincidence of this week's symmetry — flipping every game's favourite flips `picked_is_favorite` for every non-pick'em game, and this week happened to split evenly). Week 2 changed materially: **12 of 16 → 4 of 16**. Every downstream number derived from `favorite`/`picked_is_favorite` (the underdog family-push table, the hypothesis text, the market section's favourite column) is recomputed from these corrected values.

### Moneyline agreement guard (new)

`favorite_agreement()` / `enforce_favorite_agreement()`: where moneylines exist for the week, the closing-spread favourite and the de-vigged-moneyline favourite must agree on ≥80% of games, or the script exits non-zero and writes nothing. Both weeks: **100% agreement, 16/16 games, no disagreements** (reported in each week's "Favourite check" line). The guard never fired — nothing was silently swallowed.

### Line at pick time vs. closing line (new)

`experiments.backtest_predictions.home_spread_close` (the line stored when `predict_upcoming.py` generated the pick — renamed `pick_time_spread` in this script) can differ from `curated.games.home_spread_close` (the actual closing line, live until kickoff — renamed `closing_spread`). Example: `2026_01_ARI_LAC` — pick time +9.5, closing +8.5. Both weeks' reports now show both, labelled ("Line at pick time" / "Closing line"), and the favourite/underdog and key-number sections use the **closing** line, per the prompt.

### Tests

| | Before this stage | After |
|---|---|---|
| Modeling (`02-MODELING`, pytest, full suite) | 239 | **251** |

12 new tests in `test_analyze_week_explanations.py`: the corrected sign on `favorite_or_underdog` (parametrized, would fail if flipped back), the `+9.5 → home` regression case named in the prompt, "a pick on the home side is a pick on the favourite when the spread is positive," a static fixture-set test re-deriving `margin > spread` against 5 real stored 2026-week-1 rows (including the `NE_SEA` push) — independent of any production code path, so it fails if this stage's understanding of the convention is wrong — `favorite_agreement`/`enforce_favorite_agreement` (all-agree, mismatch-detected, raises-below-floor, passes-above-floor), and `build_games_frame` reading `closing_spread` (not `pick_time_spread`) into `favorite`.

### Reports regenerated

`week_analysis_2026_wk01.md` and `week_analysis_2026_wk02.md` plus all their CSVs, using the corrected sign, the closing-line favourite, and the moneyline-agreement check.

---

## Part B — the line snapshots

### Root cause (quoted evidence)

**`raw_lines.line_snapshots` was empty because the deployed pipeline image has never contained the code that writes to it — not a code bug, not a runtime failure inside a run.**

- `snapshot_lines.py` and the `snapshot()` call inside `run_ingest_schedules()` were added in commit `7b2a38c`, **2026-09-09T11:16:41Z**.
- The deployed `gcr.io/nfl-model-471509/nfl-data-pipeline:latest` image (both `nfl-pipeline-full` and `nfl-pipeline-gameday` run `:latest`, confirmed via `gcloud run jobs describe`) was last built **2026-09-08 09:23:28+12:00** — `gcloud container images list-tags gcr.io/nfl-model-471509/nfl-data-pipeline` — **before** that commit.
- Confirmed in the logs of the most recent full-pipeline execution (`nfl-pipeline-full-ll72z`, completed 2026-09-15T11:13:06Z — the most recent of either job; neither has run since):
  ```
  2026-09-15 11:01:55,432 INFO STEP: 1/7 — Ingest raw schedules
  ...
  === Schedules Ingest Summary ===
    2015: 267 rows [OK]
    ...
    2026: 272 rows [OK]
    TOTAL: 3,300 rows
  2026-09-15 11:02:58,061 INFO STEP COMPLETE: 1/7 — Ingest raw schedules (62.6s)
  ```
  Zero lines mention "Line snapshot" or "SNAPSHOT_FAILED" anywhere in the full execution log. The failure path (`logger.error("Line snapshot FAILED: %s", ...)`) would produce a visible line even on an exception — its total absence means the code that would produce it isn't in the running image at all.
- `raw_lines.line_snapshots` (0 rows before today) was created 2026-09-09T20:02:14Z — hours after the commit, `modified == created` — consistent with a one-off local/manual test the same day that reached `ensure_table()` but never completed an INSERT (most likely an early `NO_SPREAD_COLUMN` return; which branch exactly can no longer be determined from BigQuery alone).
- `snapshot_lines.py`'s own logic is sound: its 12 existing tests pass, and the manual run below (current code, current data) inserted correctly on the first attempt with no error.

**No code bug found in `snapshot_lines.py` or its caller — no fix was made there.**

### One-off capture (done)

Ran, from Windows, using already-authenticated `gcloud` credentials (Matt approved this specific action mid-session after the platform's auto-mode guard blocked an unattended Cloud Build attempt against the GCP project):

```
python 01-DATA-PIPELINE/scripts/snapshot_lines.py
```

**Result: `{'inserted': 3300, 'status': 'OK', 'captured_at': '2026-09-18T03:06:54.556173+00:00'}`.** Verified: 16/16 rows for both 2026 week 1 and week 2, one row per game across every season 2015–2026 (every game's first-ever snapshot, hence 3,300 = the full `raw_nflfastr.schedules` row count).

Not run from the production Linux image: no floating-point or model computation is involved (a parameterised BigQuery `INSERT` via the client library — the platform issuing the query doesn't affect the result), and running the actual production image would have meant rebuilding `nfl-data-pipeline:latest`, which is the redeploy Part B's own kill-switch says to stop on. Both week reports' "Line movement" section now states plainly that this is a one-time catch-up (every game has exactly one snapshot, all captured at the same instant) — not a real change-log, so "first-seen" and "closing" can't yet show actual movement.

### What still needs doing (escalated, not done)

**The recurring gap is still open.** Fixing it needs `gcloud builds submit --config cloudbuild.yaml .` from `01-DATA-PIPELINE` to rebuild `:latest` from current source — no code change, no schedule change, no IAM change, but it **is** a redeploy, and it changes what both `nfl-pipeline-full` and `nfl-pipeline-gameday` run on their next scheduled execution (next: Fri 05:00 UTC gameday-thursday). Per the prompt's kill-switch, this was stopped and written to `00-PROJECT-LEAD/QUESTIONS.md` (2026-09-18 entry) rather than done unilaterally.

### Visibility fix (done)

New pure module `01-DATA-PIPELINE/scripts/line_snapshot_freshness.py` (`evaluate_line_snapshot_freshness`, `LINE_SNAPSHOT_MAX_AGE_DAYS = 10`), wired into `validate_and_report.py` as a new "3c. Line Snapshot Freshness" section — fails the run's exit code (same as every other integrity check) if `line_snapshots` is empty or its latest capture is more than 10 days old. Live run output today:

```
3c. Line Snapshot Freshness
- `line_snapshots`: 3,300 row(s) total, latest capture 0.0 day(s) old (latest capture 2026-09-18 03:06:54.556173+00:00)  ✅
```

Test proving the FAIL path (quoted, no BigQuery needed):
```python
def test_empty_table_fails():
    """The exact state this stage found: 0 rows, table exists but never written to."""
    ok, age_txt = evaluate_line_snapshot_freshness(0, None, NOW)
    assert ok is False
    assert age_txt == "no rows"
```
`python -m pytest 01-DATA-PIPELINE/scripts/test_line_snapshot_freshness.py -v` → 4 passed (empty-fails, fresh-passes, stale-fails, boundary-passes).

Did not change the pipeline's step order, its scheduling, or make the `snapshot()` call itself fatal inside `run_ingest_schedules()` (it stays non-fatal by design, per that function's own comment — a snapshot failure must not block PBP/rosters ingest). The visibility gap this closes is specifically "invisible outside Cloud Logging"; `validate_and_report.py` is what Matt actually reads.

### Tests

| | Before this stage | After |
|---|---|---|
| Data pipeline (`01-DATA-PIPELINE/scripts`, pytest) | 12 | **16** |

4 new tests in `test_line_snapshot_freshness.py` (listed above). `test_snapshot_lines.py`'s existing 12 are unaffected (unchanged file).

### Pre-existing, unrelated defect noticed (not fixed — out of scope this stage)

`validate_and_report.py`'s own §6 prose contradicts itself: line 367-368 says "`spread_line`... negative = home favored" (wrong — the stray comment error), while line 376-377, two paragraphs later, correctly says "positive spread_line = home favored." The code (`derive_home_covered()`) has always been right; this is a documentation-only echo of the same class of error this whole stage was about. Flagging per the charter's standing instruction to log rather than silently fix — touching it wasn't in this stage's scope (only "the validation output that reports the snapshot step").

---

## Scope check

Touched: `02-MODELING/backtests/analyze_week_explanations.py` + its test + `reports/**`; `01-DATA-PIPELINE/scripts/validate_and_report.py`, its new `line_snapshot_freshness.py` + test, and `VALIDATION_REPORT.md`. Did not touch `derive_home_covered()`, anything that writes `home_covered`, `snapshot_lines.py` itself, the pipeline's step order/scheduling, stored picks/explanations, or any Cloud Run job/image.

## Left open

1. **The pipeline redeploy** (see QUESTIONS.md, 2026-09-18) — needed to make `snapshot()` actually run on the schedule again.
2. Once redeployed, `line_snapshots` will start accumulating real per-game history; today's 3,300-row catch-up gives every game exactly one data point, so real "first-seen vs. close" movement will only be visible from the next scheduled run onward.
3. The `validate_and_report.py` §6 contradictory comment noted above.
4. Everything already open in `STATE.md`'s background list is unchanged by this stage.
