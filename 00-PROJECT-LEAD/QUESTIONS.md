# QUESTIONS — escalations from worker sessions

Claude Code sessions write here when a kill-switch fires or they are stuck. PROJECT-LEAD reads this at every session start and takes open items to Matt.

Format for each entry:

```
## <date> — <prompt slug> — OPEN
Question:
What I was doing:
What I tried:
```

Change `OPEN` to `ANSWERED <date>` with the answer underneath once Matt decides.

---

## 2026-09-17 — pick-explanations (Stage 1.6, explain_picks.py) — ANSWERED 2026-09-17 (cause found)
Question: The stored 2026 week-1 and week-2 picks can't be reproduced. Should the explanations be stored as approximations, or should we find the cause first?
What I was doing: `explain_picks.py --season 2026 --week 1` and `--week 2`. The reproduction check failed on every game in both weeks (week 1: 3 side flips, week 2: 1). Nothing was written.
What I tried: rebuilt week 1 on the un-blended 23 features, which still mismatched. Ran it twice back-to-back on the same machine and got a max difference of 0.0.
PROJECT-LEAD note: the worker's data-change conclusion is not confirmed. The stored picks came from Cloud Run (`python:3.11-slim`, pinned pandas 1.5.3 / numpy 1.26.4 / scikit-learn 1.9.0 / xgboost 3.2.0), and the reproduction ran on Windows. No scheduled data job ran between the week-2 picks (2026-09-16 10:44 UTC) and the reproduction. Pending checks: local package versions against the pins, and BigQuery last-modified times.

Findings (2026-09-17, same session, before taking either option):
1. **Package versions on the Windows machine that ran `explain_picks.py` match `02-MODELING/requirements.txt` exactly**: Python 3.11.9, pandas 1.5.3, numpy 1.26.4, scikit-learn 1.9.0, xgboost 3.2.0. No version mismatch with the pins, so step 3 (separate pinned venv) was not run — nothing to test there.
2. **`curated.plays`** — created 2026-09-15 11:09:49 UTC, **last modified 2026-09-15 11:12:53 UTC**, 484,490 rows.
   **`curated.games`** — created 2026-09-15 11:08:52 UTC, **last modified 2026-09-15 11:09:38 UTC**, 3,167 rows.
   These are the only two tables `generate_predictions()` reads (via `load_plays`/`load_games` in `features/ol_metrics.py`). Neither has a `modified` timestamp after 2026-09-16 10:44 UTC — both predate it by roughly a day. No table-level change since the week-2 picks were made.
3. Both checks came back clean (versions match, no table changed since 2026-09-16 10:44 UTC) — this is the "stop and tell me" branch. Nothing further attempted; nothing written to BigQuery; no Cloud Run job touched.

Noted but not investigated further (Matt did not ask for this): the two games that flipped in week 1 (ATL@PIT, BAL@IND) are the identical pair named in `requirements.txt`'s comment about the 2026-09-10 pandas-3.0-vs-1.5.3 incident. Games sitting near the p=0.5 boundary are the ones most exposed to any small numerical difference, so this may just be that — flagging only because Matt may want it checked before ruling out an environment-shaped cause entirely.

Still open: whether the reproduction runs correctly *inside the actual production image* (not just with matching pinned versions on a different OS/architecture). Matt is deciding how to run that test next.

Production-image test (2026-09-17, same session, per Matt's ordered instructions — no Docker installed locally, so B and C used one-off `gcloud builds submit --no-source` with the target image as the build step; configs kept outside the repo, in the session scratchpad; nothing written to BigQuery, no Cloud Run/scheduler/IAM changes, no push):

**A. Code check (local, no cloud).** `git worktree add` of commit `0accc22` to `C:\Users\OEM\nfl-repro-0accc22`. Ran `python backtests/predict_upcoming.py --season 2026 --week 2 --dry-run` there and in the main working tree (which carries the uncommitted Stage 1 explanation-feature changes), same machine, same installed packages. Diffed the two output CSVs: **max abs diff in `predicted_home_cover_prob` = 0.0, no side differs, every other column identical.** The uncommitted Stage 1 changes do not alter predictions. (Worktree directory removed after; `.git/worktrees/nfl-repro-0accc22`'s metadata folder failed to delete — Windows file-lock, `Permission denied` — harmless leftover, `git worktree list` confirms the main worktree is unaffected and still on `main`.)

**B. Image contents.** `pip freeze` run inside both images via a one-off Cloud Build step (`entrypoint: sh`, `args: ['-c', 'python --version && pip freeze']`):

| | `269c67d…` (made week-1 picks) | `fff36d0…` (made week-2 picks) |
|---|---|---|
| Python | 3.11.16 | 3.11.16 |
| pandas | 1.5.3 | 1.5.3 |
| numpy | 1.26.4 | 1.26.4 |
| scikit-learn | 1.9.0 | 1.9.0 |
| xgboost | 3.2.0 | 3.2.0 |
| threadpoolctl | 3.6.0 | 3.7.0 |
| urllib3 | 2.7.0 | 2.8.0 |

Every numerically-relevant package is identical between the two images, and identical to `requirements.txt`'s pins and to the Windows machine's installed versions (see the earlier finding above). Only two unrelated transitive packages differ by patch version. This rules out a version-pin mismatch anywhere in the chain.

**C. Week-2 reproduction inside `fff36d0` (the image that made the stored week-2 picks).** Checked first whether the build could reach BigQuery at all, since I don't have local Docker and can't mount my personal ADC into a remote Cloud Build worker — I did not upload any personal credentials or change any IAM bindings; I only checked what the Cloud Build default service account (`578855090704@cloudbuild.gserviceaccount.com`, role `roles/cloudbuild.builds.builder` only, no BigQuery role) could already do. A trivial `SELECT 1` inside the image succeeded, so it already has read access via ambient project credentials — no permission change was needed or made. Then ran the real command as instructed: `cd /app && python backtests/predict_upcoming.py --season 2026 --week 2 --dry-run` (the image already has the source baked in at `/app`; `--dry-run` means nothing was written).

**Result: this matches the stored week-2 picks almost exactly.** Max abs diff across all 16 games: **2.86e-08** (comfortably inside the 1e-6 reproduction-guard tolerance). Zero side flips.

| game_id | stored | reproduced (in `fff36d0`) | diff |
|---|---|---|---|
| 2026_02_CAR_ATL | 0.431852 | 0.431852 | 4.1e-09 |
| 2026_02_CIN_HOU | 0.398261 | 0.398261 | 3.8e-09 |
| 2026_02_CLE_TB | 0.537903 | 0.537903 | 5.4e-11 |
| 2026_02_DET_BUF | 0.489037 | 0.489037 | 3.5e-09 |
| 2026_02_GB_NYJ | 0.499867 | 0.499867 | 5.0e-09 |
| 2026_02_IND_KC | 0.559942 | 0.559942 | 7.1e-09 |
| 2026_02_JAX_DEN | 0.571938 | 0.571938 | 2.0e-08 |
| 2026_02_LV_LAC | 0.592223 | 0.592223 | 2.9e-08 |
| 2026_02_MIA_SF | 0.585004 | 0.585004 | 8.7e-09 |
| 2026_02_MIN_CHI | 0.751606 | 0.751606 | 3.6e-09 |
| 2026_02_NO_BAL | 0.547786 | 0.547786 | 2.2e-08 |
| 2026_02_NYG_LA | 0.586187 | 0.586187 | 5.0e-09 |
| 2026_02_PHI_TEN | 0.503177 | 0.503177 | 2.8e-08 |
| 2026_02_PIT_NE | 0.523771 | 0.523771 | 1.2e-08 |
| 2026_02_SEA_ARI | 0.554022 | 0.554022 | 1.4e-08 |
| 2026_02_WAS_DAL | 0.520283 | 0.520283 | 1.8e-08 |

**Conclusion this session is confident in:** the stored week-2 picks ARE faithfully reproducible — but only inside the actual Linux production image, not on the Windows dev machine, despite byte-identical pinned package versions on both. Since code (A), data (prior check), and package versions (B) are all now ruled out, and the model itself is deterministic given identical inputs (earlier back-to-back check, and xgboost's own determinism guarantee), the remaining variable is the OS/platform itself: numpy/pandas/scikit-learn ship different compiled binaries per platform (different BLAS backend, different compiler, different SIMD codepaths), which can produce tiny floating-point differences in aggregation order that are invisible at the `pip freeze` version level. This is the same class of problem `ol_xgb.py`'s `n_jobs=1` comment already documents for core-count — this session's evidence says the same kind of drift also happens across Windows-vs-Linux, not just across thread counts. Week 1 was not re-tested inside `269c67d` this session (not asked for); given B shows its package set is equally pinned, the same explanation likely applies, but that's inference, not something this session verified directly.

**Practical implication for Stage 1, flagged but not acted on:** `explain_picks.py`'s reproduction guard is sound in design, but running it on a Windows dev machine will produce false STOPs even when the pick is perfectly reproducible. It needs to run in a Linux environment matching (or ideally *being*) the production image for the guard to mean anything. That's a decision for Matt, not taken here.
PROJECT-LEAD review (2026-09-17, after the worker's checks):
- On Matt's PC the package versions match the pins, and `curated.plays` and `curated.games` were last modified on 2026-09-15, before the week-2 picks. So neither explains the week-2 gap.
- Week 1 has changed on every recorded run. The 5 local runs from 09-09/09-10 in `02-MODELING/backtests/reports/forward_2026_wk01_*.csv` match neither the stored picks nor today's reproduction. On 09-09 ATL@PIT was an away pick, today's reproduction picks away, and the stored pick is home. The stored week-1 picks came from Cloud Run image `269c67d…`, which was probably built before the 09-10 version pins. Its package versions are not recorded anywhere.
- Platform gap: runs don't record the image digest or package versions that produced them.
- Next (sent to the worker): A) run the committed code at 0accc22 locally to check whether the Stage 1 changes alter output; B) list installed packages inside images 269c67d and fff36d0; C) reproduce week 2 inside fff36d0 with a dry run, using local Docker or a one-off Cloud Build. No Cloud Run, IAM or BigQuery changes.
ANSWER (PROJECT-LEAD, 2026-09-17 ~09:05 UTC): Windows and Linux give different numbers even with identical library versions.
- Evidence: step A showed the Stage 1 changes don't alter output (max diff 0.0). In step B, images 269c67d and fff36d0 had the same pins as the PC. In step C, week 2 run inside fff36d0 through Cloud Build reproduced the stored picks to 2.86e-08.
- Rule that follows: any run whose numbers must match production (reproductions, the guard, backtests used as evidence) runs in the production Linux image, not on Windows.
- Still open: week 1 hasn't been tested in Linux. Its picks predate the 2026-09-15 curated rebuild, so the guard may still fail there. If it does, Matt decides whether to store approximate explanations (tracked in STATE.md, "Waiting on Matt").

## 2026-09-18 — pick-explanations (Stage 1b, PROMPT-STAGE1-FINISH-EXPLANATIONS.md §1) — ANSWERED 2026-09-18 (recovery done, guard still fails — kept approximate)

Question: Can BigQuery time travel recover the pre-2026-09-15 `curated.games`/`curated.plays`, and does reproducing week 1 against that recovered data pass the guard?

What I did:
1. `region-us.INFORMATION_SCHEMA.SCHEMATA_OPTIONS` confirms `curated`'s `max_time_travel_hours = 168` (7 days). `curated.games` was created 2026-09-15 11:08:52.365 UTC, `curated.plays` 11:09:49.977 UTC (confirmed via `bq show`, matching the handoff's claimed timestamps exactly) — so time travel on the pre-rebuild versions expires ~2026-09-22 11:08 UTC.
2. The stored week-1 picks (`experiments.backtest_runs`, run `afa6e00d-3d40-4d96-9ffd-b03d0e264a7f`) were written 2026-09-13 09:51:46 UTC — before the rebuild, as suspected.
3. `bq cp` (not a plain `SELECT ... FOR SYSTEM_TIME AS OF` — that failed with "table not found," `bq cp` with the `@<epoch ms>` decorator worked) recovered both tables as they stood just before the rebuild into a new dataset `scratch_timetravel` (30-day default table expiration set), renamed `games`/`plays` to match `curated`'s layout. Row counts: 3,167 games / 484,490 plays — identical to current.
4. Compared old vs. current for every column `generate_predictions()` reads (`features/ol_metrics.py::load_plays`/`load_games`), per season, 2015–2025, via `BIT_XOR(FARM_FINGERPRINT(...))` checksums: **every season's games and plays checksum matches exactly, both tables.** 2015–2025 data was not changed by the 09-15 rebuild.
5. For 2026 specifically, checked week-by-week: **only `curated.games` week 1 differs**, and only one game — `2026_01_DEN_KC`: `temp`/`wind` were `NULL` in the pre-rebuild snapshot, now `91.0`/`13.0` (a weather backfill, not a rebuild-introduced error). No other 2026 games or weeks differ, and `curated.plays` week 1 is byte-identical.
6. Added `--curated-dataset` to `explain_picks.py` (default `curated`), threaded through `generate_predictions`/`load_plays`/`load_games`. Ran `--season 2026 --week 1 --curated-dataset scratch_timetravel` inside a one-off Cloud Build step (`python:3.11-slim`, pinned requirements.txt — the same Linux/pin combination confirmed correct for week 2 on 09-17).

Result: **the guard still fails against the recovered pre-rebuild data.** Max diff dropped from 0.037 (against current data) to **0.0242** (TB_CIN), and side flips dropped from 3 (ATL_PIT, GB_MIN, NYJ_TEN) to **1 (NYJ_TEN only)** — recovery measurably narrowed the gap (ATL_PIT and GB_MIN now match or nearly match), but did not close it. `2026_01_DEN_KC` — the one game that actually changed — reproduces exactly (diff 0.0000) in both the pre- and post-rebuild runs, so its weather backfill is not what's driving the remaining mismatch. The genuine cause of week 1's non-reproduction is still unknown; it is not the 09-15 `curated` rebuild.

Decision (per the prompt's own step 6): recovery done, guard still fails → **week 1 stays approximate.** No new run was written for week 1 (the existing approximate rows from 09-17, `reproduction_max_diff=0.0370355`, are unchanged — append-only, nothing deleted). `scratch_timetravel` is kept (30-day expiry) in case someone wants to dig further before ~2026-09-22 11:08 UTC.

Week 2 (QB-percentile fix, §3): re-ran `explain_picks.py --season 2026 --week 2` (default `curated`, unaffected by the recovery question) in the same Linux one-off build — reproduced exactly (`reproduction_max_diff=0`) — and appended a new exact run (`run_id=82abf4e0-bab6-47ea-b5a9-4d1e6abc6e46`, 864 rows, `is_approximate=False`) with the `league_pctile` fix from `explanations.py`. Verified live: 0 nulls across all 4 QB-blend feature/side combinations on this run, vs. 16 nulls each before. The API's "exact over approximate, then newest" rule picks this new run automatically.
