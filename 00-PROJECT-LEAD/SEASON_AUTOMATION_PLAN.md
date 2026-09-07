# Season Automation Plan — 2026 Season

**Owner:** PROJECT-LEAD / DEVOPS / DATA-PIPELINE
**Context:** Season starts ~2026-09-10. This plan fixes the broken ingest automation found in `docs/DATA_STOCKTAKE_2026-08-31.md` and extends it so data is captured as close to real time as the underlying sources actually allow during the season.
**Read first:** `docs/DATA_STOCKTAKE_2026-08-31.md` §4 — the current automation has been failing on every run for 115 days. **Updated 2026-08-31 evening:** the scheduler/auth bug is now fixed and verified live; a second bug (Priority 0b below) was uncovered by that fix and is fixed in source but not yet redeployed.

---

## Scope note — what "real-time" can mean here

`ARCHITECTURE.md`'s own Non-Goals list says: *"Real-time / streaming predictions, Live in-game updates"* are explicitly out of scope for v1. That's a real tension with "scraped as close to real-time as possible" — worth resolving explicitly rather than quietly picking one side.

- **nflverse/`nfl_data_py`** (the project's entire data spine) is **not a live feed**. Its play-by-play is typically posted within a couple of hours after a game ends, sometimes the next morning; it is not updated pitch-by-pitch during a live game. So for everything this pipeline already produces — PBP, EPA, snap counts, injuries, depth charts, closing lines — "real-time" realistically means **"pulled promptly after each data-availability window closes,"** not "updating during the game."
- **True in-game data** (live score, live win probability) would need a genuinely different, additional source (e.g., an odds/scores API or a scoreboard feed), a different ingestion pattern (short-interval polling instead of scheduled batch jobs), and its own ToS/rate-limit review — the same care this project already applies to scraped sources in `docs/DATA_SOURCES.md`.

This plan is built around the first definition (fast, well-timed post-window pulls) as Priorities 0–4, since that's what the existing architecture is designed for and what's actually broken today. Priority 5 sketches what true in-game live data would additionally take, flagged as a scope decision rather than assumed.

---

## Priority 0 — Fix the broken scheduler (do this before anything else)

**Status: fixed in source, applied to live GCP, and verified live 2026-08-31. See Priority 0b below for a second bug this uncovered.**

Nothing downstream matters if the trigger chain doesn't fire. I found a second bug beyond the one in the stocktake doc §4 while fixing this, so there were two things wrong, both fixed in the Terraform source and applied via `terraform apply` by Matt on 2026-08-31 (`Apply complete! Resources: 1 added, 6 changed, 0 destroyed.`):

1. **Wrong auth mechanism (the 401s).** `scheduler.tf`'s 5 `http_target.oidc_token { ... }` blocks are now `http_target.oauth_token { service_account_email = ... }` — Cloud Scheduler → Cloud Run **Jobs Admin API** needs an OAuth2 token, not an OIDC identity token, which is why every attempt got a 401 regardless of which service account was used. **Done and applied.**
2. **Missing role (would have been 403 next).** `nfl-pipeline-sa` — used by 4 of the 5 jobs — had *no* Cloud Run role at all in `iam.tf` (only `bigquery.jobUser`), unlike `nfl-runner-sa` which already has `roles/run.developer`. Fixing #1 alone would have traded a 401 for a 403 on those 4 jobs. Added `google_project_iam_member.pipeline_invoke_jobs` granting `nfl-pipeline-sa` `roles/run.developer`. **Done and applied.**

**Live verification (2026-08-31, done in-browser):** Force-ran `nfl-pipeline-full-weekly` and `nfl-pipeline-gameday-sunday` from the Cloud Scheduler console. Both now show **Success** at the scheduler level (previously 100% failure for 115 days), and — more importantly — both **created real Cloud Run Job executions** for the first time: `nfl-pipeline-gameday` had **never** created a single execution before today (the stocktake's "No executions" finding); it now has one. This confirms the auth + IAM fix genuinely works end-to-end, not just that the scheduler's HTTP call returns 200.

`raw_nflfastr.schedules` also actually refreshed as a result — first time in 115 days — and now holds the full 2026 season (3,300 rows, up from 3,028; the +272 is the entire 2026 REG schedule). That's real, new, live 2026 data in BigQuery for the first time.

However: both forced executions ultimately ended **Failed with errors** after exhausting retries — not because of the auth bug, but because of a second, separate, previously-latent bug. See Priority 0b.

---

## Priority 0b — New finding: the pipeline's own data-quality gate now blocks every run (found + fixed in source 2026-08-31, needs redeploy)

**Status: root-caused and fixed in source per Matt's direction ("make it a warning, not a stop"). Not yet live — needs an image rebuild + redeploy, see below.**

With the scheduler bug fixed, both forced runs got much further than ever before — actually reaching real pipeline code — and then both died at the identical spot: **Step 2/7 — Audit closing lines**, exit code 1, after 3 retries each.

**Root cause:** `01-DATA-PIPELINE/scripts/run_pipeline.py` runs `audit_closing_lines`'s null-rate check inline as a hard gate every single run (`if null_pct > 5.0: sys.exit(1)`), aborting steps 3–7 (PBP/rosters ingest, `curated.games`/`curated.plays` rebuild, validation) — even though the file's own docstring already claims step 2 just "prints report; continues automatically," which the `sys.exit(1)` contradicted. This audit was designed as a **one-time decision** ("is nflverse a reliable historical closing-line source, checked 2015–present?" — see `scripts/audit_closing_lines.py`'s docstring), not a per-run production gate.

It only started firing now because the audit's season range (`CURRENT_SEASON = this year, or last year if before July`) flipped to include 2026 in July 2026. The 2026 season's future weeks don't have sportsbook closing lines posted yet (160 of 272 games null, 58.8%), which — blended into the ~2,900 historical rows that are 0% null — pushes the aggregate to 5.1%, just over the hardcoded 5% threshold. **This would have hard-failed every single scheduled run for the rest of the season** (steps 3–7 never running, so PBP/rosters/curated tables would never refresh in-season), since sportsbooks don't post a full season's lines this far ahead — only step 1 (raw schedule ingest) would have kept working.

**Fix applied (per Matt's choice — "make it a warning, not a stop"):** Edited `01-DATA-PIPELINE/scripts/run_pipeline.py` so the null-rate check logs a `logger.warning(...)` instead of calling `sys.exit(1)`. The audit still runs and prints its report every time (useful signal if the null rate looks unexpectedly bad even for historical seasons); it just no longer blocks steps 3–7. Verified the file still compiles (`python3 -m py_compile`).

**This is not live yet.** Both `nfl-pipeline-full` and `nfl-pipeline-gameday` run from the same container image, `gcr.io/nfl-model-471509/nfl-data-pipeline:latest` (built from `01-DATA-PIPELINE/Dockerfile.job` via `01-DATA-PIPELINE/cloudbuild.yaml`). There's no Cloud Build trigger wired up (confirmed — deploys are manual), and pushing a new `:latest` image does **not** automatically get picked up by existing Cloud Run Jobs; the job resources need to be pointed at the tag again to force Cloud Run to re-resolve it. To ship this fix:

```
cd 01-DATA-PIPELINE
gcloud builds submit --config=cloudbuild.yaml .
gcloud run jobs update nfl-pipeline-full --image=gcr.io/nfl-model-471509/nfl-data-pipeline:latest --region=us-central1
gcloud run jobs update nfl-pipeline-gameday --image=gcr.io/nfl-model-471509/nfl-data-pipeline:latest --region=us-central1
```

(`nfl-production-refresh` uses a different image, `nfl-experiment-runner:latest` — unaffected by this fix, doesn't need redeploying for this.)

**After redeploying, verify** the same way I did today: force-run `nfl-pipeline-full-weekly` from Cloud Scheduler, check the new execution in Cloud Run → Jobs → History reaches **Succeeded** (not just created), and confirm `raw_nflfastr.pbp`/`rosters` and `curated.games`/`curated.plays` last-modified timestamps actually advance.

**Separate, unfixed loose thread spotted while reading this code (flagging, not touched):** `run_pipeline_job.py`'s `PIPELINE_MODE=gameday` branch calls `run_pipeline.main()` with `--start-at 1` — identical to `PIPELINE_MODE=full`'s default — even though its own comment says gameday should skip PBP/rosters "for speed" and flags this with "Note: Confirm with DATA-PIPELINE that `--start-at 1` is the correct invocation." In other words, `nfl-pipeline-gameday` currently runs the *entire* 7-step pipeline (including a full historical PBP re-ingest) on every Thu/Sun/Mon trigger, not a lightweight schedules-only refresh. That's a real cost/timing question for Priority 2/3 below, not something I changed — it needs a DATA-PIPELINE decision on what gameday mode should actually do.

---

## Priority 1 — Backfill the 13 staged OL/advanced sources (one-off, this week)

- Get GCP credentials onto whichever machine will run this — either `gcloud auth application-default login` (per `01-DATA-PIPELINE/RUN.md`'s existing Step 0) or a service-account key with BigQuery Data Editor on `nfl-model-471509`.
- `cd 01-DATA-PIPELINE/new_sources_staging && pip install google-cloud-bigquery pyarrow pandas && python load_to_bigquery.py` — idempotent, safe to re-run, lands everything in a new `raw_ol_sources` dataset.
- Update `docs/DATA_SOURCES.md` to reflect these 13 sources (currently silent on all of them).

This is a backfill of mostly-historical data. Four of these files are **in-season feeds**, not one-time pulls — carried into Priority 2.

---

## Priority 2 — Make the in-season-updating sources recurring

`ol_injuries`, `ol_depth_charts`, `ol_snap_counts`, and both NGS files (passing/rushing) update weekly *during* the season via the same `nfl_data_py` functions already used for the one-off pull above. Rather than standing up a parallel scheduler job with its own timing to maintain, the simplest and most reliable option is to **extend `nfl-pipeline-gameday`'s existing container** to also refresh these five tables into `raw_ol_sources` on every gameday trigger — the timing (post-Thu/Sun/Mon games) is already right for them, and it's one less job to keep healthy.

| Table | Refreshed by | Cadence (once P0 is fixed) |
|---|---|---|
| `raw_ol_sources.ol_injuries` | `nfl-pipeline-gameday` (extended) | After Thu / Sun / Mon games |
| `raw_ol_sources.ol_depth_charts` | `nfl-pipeline-gameday` (extended) | After Thu / Sun / Mon games |
| `raw_ol_sources.ol_snap_counts` | `nfl-pipeline-gameday` (extended) | After Thu / Sun / Mon games |
| `raw_ol_sources.ngs_passing` / `ngs_rushing` | `nfl-pipeline-gameday` (extended) | After Thu / Sun / Mon games |
| `raw_ol_sources.contracts*`, `draft_picks`, `combine` | Manual / on-demand | Effectively static — re-run once a year (draft/free agency) |

---

## Priority 3 — Tighten timing so gameday data actually lands close to real time

The existing 3 gameday triggers are reasonable but coarse — each is a single next-day catch-all:

| Scheduler job | Fires (UTC) | Local (ET) | Covers |
|---|---|---|---|
| `nfl-pipeline-gameday-thursday` | Fri 05:00 | Thu ~11pm–1am | TNF |
| `nfl-pipeline-gameday-sunday` | Mon 05:00 | Sun 11pm–1am | **All** Sunday games (early, late, SNF) in one pull |
| `nfl-pipeline-gameday-monday` | Tue 07:00 | Mon 1–3am (next day) | MNF |

The Sunday job is the one worth splitting if the goal is genuinely "as close to real-time as possible": right now, an early-window game that finishes ~4pm ET doesn't get pulled until after midnight, alongside SNF. Recommend adding one earlier same-day Sunday trigger (~7:30–8pm ET, after early + afternoon windows close, before SNF kicks off) so early/afternoon results are available same evening instead of the next day, keeping the existing post-SNF trigger for the rest. Same logic doesn't apply to Thu/Mon since those are single-game windows already.

Separately: **inactives are announced ~90 minutes before kickoff** and are the single most time-sensitive pre-game signal this pipeline touches (`ol_injuries`/`ol_depth_charts` won't reflect them — that's a same-day, near-kickoff data point nflverse's weekly injury report doesn't cover at all). If inactives matter to the model, that's a distinct, smaller scrape (likely needs its own source — nflverse doesn't carry inactives specifically) triggered ~2 hours before each kickoff, not something to fold into the weekly cadence above. Flagging this as a separate build, not assuming it's wanted.

---

## Priority 4 — Close the monitoring gap

The existing "Cloud Run Job — Execution Failed" alert (enabled, verified live) never fired during 115 days of continuous failure, because the failure happens at the Scheduler→API auth step, before a Cloud Run execution is ever created — there was nothing for that alert to see. Two additions close this:

1. **A Cloud Scheduler-level alert**, not just a Cloud Run-level one: a log-based metric on `resource.type="cloud_scheduler_job" AND severity="ERROR"`, alerting on any occurrence. This is exactly the metric that would have caught this on day one.
2. **A data-freshness check**, independent of *why* something failed: a small scheduled query (or Cloud Function) that asserts `MAX(last_modified)` across `raw_nflfastr.*` / `raw_ol_sources.*` is within N days of "now" during the season, alerting if not. This catches the *next* failure mode too — schema drift, quota, a changed nflverse column — not just this specific auth bug.

Both route to the existing `matt.lilley4@gmail.com` notification channel already wired up in `monitoring.tf`.

---

## Priority 5 — True live in-game data (needs your decision, not assumed)

Out of scope of everything above, since it needs a different source than nflverse entirely. If you want actual live scores/status during games (not just "same day" post-game pulls), the lightest version is a short-interval poll (e.g. every 2–5 minutes during live windows only, not all day) of a scoreboard/odds feed, written to its own small `raw_live.*` table, kept fully separate from the batch pipeline above so a live-polling hiccup can't take down the core ingest. This needs: picking a source and confirming its terms allow polling at that frequency (same standard this project already applies — see `docs/DATA_SOURCES.md`'s scraping notes), and a Cloud Scheduler job with a much shorter interval than anything above, gated to only run during actual game windows to avoid needless cost/load the rest of the week. Flagging as a scope decision rather than building it — say if you want this and I'll spec it properly.

---

## Consolidated schedule (existing + proposed)

| Job | Cron (UTC) | Status |
|---|---|---|
| `nfl-pipeline-full-weekly` | `0 11 * * 2` | Scheduler fixed & verified; blocked on P0b redeploy |
| `nfl-pipeline-gameday-thursday` | `0 5 * * 5` | Scheduler fixed & verified; blocked on P0b redeploy |
| `nfl-pipeline-gameday-sunday` (early/afternoon) | *new, ~`30 23 * * 0`* | Proposed (P3) |
| `nfl-pipeline-gameday-sunday` (existing, post-SNF) | `0 5 * * 1` | Scheduler fixed & verified; blocked on P0b redeploy |
| `nfl-pipeline-gameday-monday` | `0 7 * * 2` | Scheduler fixed; blocked on P0b redeploy |
| `nfl-production-refresh-weekly` | `0 14 * * 2` | Scheduler fixed (different image — unaffected by P0b, not yet force-verified) |
| OL sources refresh | *folded into gameday jobs* | Proposed (P2) |
| Scheduler-failure alert | n/a (log-based metric) | Proposed (P4) |
| Data-freshness check | *new, daily during season* | Proposed (P4) |
| Live in-game poll | *new, short-interval, game windows only* | Optional (P5) — needs decision |

---

## Suggested order of work this week

1. ~~Apply the P0 auth fix and verify all 5 jobs actually execute.~~ **Done and verified 2026-08-31.**
2. Rebuild + redeploy the pipeline image so the P0b closing-line-gate fix goes live (commands above), then re-verify a full run reaches Step 7 and `curated.*` timestamps advance.
3. Run the P1 backfill (`load_to_bigquery.py`) once credentials are in place.
4. Extend `nfl-pipeline-gameday` per P2 so the in-season sources ride along on the now-fixed trigger — and resolve the P0b gameday-mode loose thread (does gameday need the full 7 steps, or should it actually skip PBP/rosters as originally intended?) while you're in that code.
5. Add the P4 alerting so the next failure — whatever it turns out to be — gets caught in a day, not a season.
6. Decide on P3's split Sunday trigger and P5's live-data scope; both are additive and don't block kickoff.
