# Data Stocktake — 2026-08-31

**Owner:** PROJECT-LEAD
**Purpose:** Complete inventory of what data actually exists — live in BigQuery and staged on disk — verified directly against GCP (not against docs, which had drifted), ahead of the 2026 season start (~Sep 10).
**Method:** Live queries run against `nfl-model-471509` in the BigQuery console, plus Cloud Scheduler / Cloud Run / Cloud Logging / IAM console checks, on 2026-08-31. Local repo (`01-DATA-PIPELINE/`, `00-PROJECT-LEAD/`) cross-referenced for staged-but-unloaded files.

---

## 1. BigQuery — Live State (verified 2026-08-31)

Project `nfl-model-471509` has 6 datasets: `curated`, `experiments`, `platform`, `raw_lines`, `raw_nflfastr`, `user_datasets`.

| Dataset.Table | Rows | Size | Created | Last modified | Notes |
|---|---|---|---|---|---|
| `raw_nflfastr.pbp` | 532,376 | 1,393 MB | 2026-05-08 | **2026-05-08** | Play-by-play, 2015–2025 (all rows incl. preseason). Stale 115 days. |
| `raw_nflfastr.rosters` | 498,381 | 184 MB | 2026-05-08 | **2026-05-08** | Weekly rosters, 2015–2025. Stale 115 days. |
| `raw_nflfastr.schedules` | 3,028 | 1.2 MB | 2026-05-08 | **2026-05-08** | Schedules + closing lines, 2015–2025. Stale 115 days. |
| `curated.games` | 2,895 | 0.38 MB | 2026-05-08 | 2026-05-17 | One row/REG game. Last touch was the manual INC-001 label-inversion fix, not a scheduled refresh. |
| `curated.plays` | 481,874 | 74.3 MB | 2026-05-08 | 2026-05-08 | Filtered play-by-play. Stale 115 days. |
| `experiments.backtest_runs` | 35 | 0.04 MB | 2026-05-08 | 2026-08-15 | Most recent write is 16 days ago — the live app was used then (see §4). |
| `experiments.backtest_predictions` | 28,191 | 4.2 MB | 2026-05-03 | 2026-05-25 | |
| `platform.experiment_configs` | 13 | 0.02 MB | 2026-05-04 | 2026-08-15 | Matches the Aug 15 backtest_runs write — someone ran a new experiment via the live app that day. |
| `platform.frameworks` | 1 | 0.0 MB | 2026-05-04 | 2026-05-09 | |
| `platform.datasets` | 0 | 0.0 MB | 2026-05-04 | 2026-05-23 | Empty — the one stuck P5-03 dataset was deleted via the new DELETE endpoint; no dataset has been uploaded since. |
| `platform.dataset_columns` | 0 | 0.0 MB | 2026-05-04 | 2026-05-23 | Empty, same reason. |
| `raw_lines.*` | — | — | — | — | Dataset exists, **zero tables**. By design — nflverse's `spread_line`/`total_line` are used directly; no separate closing-lines table was ever needed. |
| `user_datasets.*` | — | — | — | — | Dataset exists, **zero tables**. No user dataset upload has ever succeeded end-to-end. |

**Season coverage: 2015–2025 (11 REG seasons) for play-by-play, schedules, rosters. There is no 2026 data yet** — expected, since the season hasn't started, but see §4: the scheduled job that would pull it in-season is currently broken.

Row counts for `raw_nflfastr.pbp`/`rosters`/`schedules` match the last known-good validation report (`01-DATA-PIPELINE/VALIDATION_REPORT.md`, 2026-05-03) exactly, confirming the table wasn't left in a partially-loaded state by the 2026-05-07 failure described in §4 — it was fully and correctly reloaded once, on 2026-05-08, and hasn't been touched since.

---

## 2. Staged locally, NOT yet in BigQuery

`01-DATA-PIPELINE/new_sources_staging/` — 14 parquet files, ~29 MB, fetched via `nfl_data_py` and staged **2026-08-30/31 (yesterday)**. Full per-file detail is in `01-DATA-PIPELINE/new_sources_staging/README.md`; summary:

| File | Rows | Coverage |
|---|---|---|
| `contracts.parquet` / `contracts_flat.parquet` | 52,103 players | OverTheCap contracts, through 2026 |
| `seasonal_rosters_2015_2025.parquet` | 33,184 (5,615 OL) | 2015–2025 |
| `combine_2000_2025.parquet` | 8,649 (1,423 OL) | 2000–2025 draft classes |
| `draft_picks_1990_2025.parquet` | 9,328 (1,557 OL) | 1990–2025, incl. PFR career-value fields |
| `ol_snap_counts_2013_2025.parquet` | 51,281 | 2013–2025, per-player per-game |
| `ol_injuries_2015_2025.parquet` | 10,937 | 2015–2025, weekly injury report + practice status |
| `ol_depth_charts_2015_2025.parquet` | 61,912 | 2015–2025, weekly LT/LG/C/RG/RT |
| `ngs_passing_2016_2025.parquet` | 5,933 | 2016–2025, Next Gen Stats |
| `ngs_rushing_2016_2025.parquet` | 6,059 | 2016–2025, Next Gen Stats |
| `pfr_qb_pressure_2018_2025.parquet` | 848 | 2018–2025, season grain |
| `pfr_weekly_qb_pressure_2018_2025.parquet` | 5,424 | 2018–2025, per-game grain |
| `pfr_rushing_ybc_2018_2025.parquet` | 2,820 | 2018–2025 |
| `ftn_charting_2022_2025.parquet` | 185,215 plays | 2022–2025, charting data |

**None of this has touched BigQuery yet.** `load_to_bigquery.py` (same folder) is written, idempotent (`WRITE_TRUNCATE`), and ready — it lands each file in a new `raw_ol_sources` dataset. It hasn't run because the machine that staged these files has no `gcloud` install and no service-account key. This is a same-day, low-risk task once credentials are available (see Automation Plan, Priority 1).

**Note for the season:** several of these sources update **during the season**, not just once historically — `ol_injuries`, `ol_depth_charts`, `ol_snap_counts`, and the two NGS files are weekly in-season feeds via the same `nfl_data_py` functions. Loading them once now is a backfill; keeping them current needs a recurring job (see Automation Plan §2).

### Sources deliberately not pursued
- **ESPN** (Pass/Run Block Win Rate) — `robots.txt` explicitly disallows the `anthropic-ai` crawler site-wide. Not scraped.
- **ras.football** — no clear bulk-access terms; replaced with the raw combine numbers RAS is computed from (`combine_2000_2025.parquet`), which covers more seasons anyway.
- **NFL Big Data Bowl / Kaggle tracking data** — free, but requires a Kaggle account + API token (a real access step, not a scraping problem) and a much bigger feature-engineering build. Deliberately deferred as a separate project.
- **PFF, Sports Info Solutions** — unchanged, still paid/licensed (`docs/DATA_SOURCES.md`).

---

## 3. `docs/DATA_SOURCES.md` is stale

That file is dated 2026-05-03 and doesn't reflect the 13 new sources above at all, nor the automation state in §4. Recommend PROJECT-LEAD refreshes it in the same pass as loading `raw_ol_sources` — this doc doesn't duplicate that detail to avoid drift between two copies of the same table.

---

## 4. Automation health — the pipeline has not run successfully in 115 days

This is the headline finding, and it directly answers "do we have automation running": **the Terraform-defined infrastructure exists and is enabled, but every scheduled job has failed on every attempt for as far back as logs retain.**

**What's deployed** (`05-DEVOPS/infra/terraform/`, applied 2026-05-07): 5 Cloud Scheduler jobs, all **Enabled** —

| Scheduler job | Schedule (UTC) | Status of last execution (checked 2026-08-31) |
|---|---|---|
| `nfl-pipeline-full-weekly` | Tue 11:00 | ❌ Failed |
| `nfl-pipeline-gameday-sunday` | Mon 05:00 | ❌ Failed |
| `nfl-pipeline-gameday-monday` | Tue 07:00 | ❌ Failed |
| `nfl-pipeline-gameday-thursday` | Fri 05:00 | ❌ Failed |
| `nfl-production-refresh-weekly` | Tue 14:00 | ❌ Failed |

**Root cause (confirmed via Cloud Logging, not guessed):** every single attempt for every job returns the identical error:

```
"debugInfo":"URL_ERROR-ERROR_AUTHENTICATION. Original HTTP response code number = 401"
"status":"UNAUTHENTICATED"
"url":"https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/nfl-model-471509/jobs/<job>:run"
```

Cloud Scheduler is calling the Cloud Run **Admin API** (`.../jobs/<job>:run`) to start a Job execution. `scheduler.tf` authenticates that call with an `oidc_token` block. OIDC identity tokens are the right mechanism for invoking a Cloud Run **service's** own HTTPS URL (audience-bound), but the Run Admin API's `:run` action on a **Job** expects a standard OAuth2 access token instead — hence a 401 at the authentication layer, before IAM authorization is even evaluated.

This is confirmed *not* a missing-permission (403) issue: it fails identically for `nfl-pipeline-sa` (has only `BigQuery Job User`) and for `nfl-runner-sa` (has `BigQuery Job User` **and** `Cloud Run Developer`) — if this were a role gap, the better-provisioned account would succeed. Neither does.

**Fix:** in `05-DEVOPS/infra/terraform/scheduler.tf`, change each of the 5 `http_target.oidc_token { ... }` blocks to `http_target.oauth_token { service_account_email = ... }`, then `terraform apply`. As an immediate stopgap that doesn't touch Terraform state, each job can be patched directly:
```
gcloud scheduler jobs update http nfl-pipeline-full-weekly --location=us-central1 \
  --oauth-service-account-email=<pipeline-sa-email>
```
(repeat per job, matching the service account each already uses). Reconcile the Terraform source afterward so the next `apply` doesn't revert it.

**Practical impact today:**
- `raw_nflfastr.*` / `curated.plays` haven't refreshed since 2026-05-08. `curated.games` was hand-fixed once on 2026-05-17 for the INC-001 label bug, not by the scheduler.
- The three gameday post-game refreshes have **never** succeeded even once since Terraform was applied.
- `nfl-production-refresh` (would push new predictions for gate-passed experiments) has **never** succeeded once either.
- Cloud Run Jobs' own execution history confirms this from the other side: `nfl-pipeline-full` shows exactly one execution ever, "Succeeded," 2026-05-08 — nothing since. `nfl-pipeline-gameday` and `nfl-production-refresh` show **"No executions"** at all, ever — the scheduler's calls are failing before an execution is even created.

**Why no one noticed:** `05-DEVOPS` did set up an alert policy, "Cloud Run Job — Execution Failed" (enabled, verified live). But it alerts on failed *executions* — and this failure mode never creates an execution to fail. The alert has correctly never fired, because from Cloud Run's perspective nothing ever ran. This is a monitoring gap, not a false negative in the alert logic itself (see Automation Plan §4).

**Separately, not blocking:** `nfl-experiment-runner` (triggered on-demand from the app when a user clicks "Run," not on a schedule) was last invoked 2026-08-15 and failed. That's a live-app bug worth a look but is unrelated to the ingest scheduling fix above.

### Addendum — 2026-08-31 evening: fix applied, verified live, second bug found

The `oidc_token`→`oauth_token` fix and the new `pipeline_invoke_jobs` IAM role (above) were applied live via `terraform apply` and verified in-browser the same evening: force-running `nfl-pipeline-full-weekly` and `nfl-pipeline-gameday-sunday` from Cloud Scheduler now shows **Success**, and — the real proof — both created **actual Cloud Run Job executions**, something `nfl-pipeline-gameday` had literally never done before (the "No executions" finding above). `raw_nflfastr.schedules` refreshed as a result: 3,028 → 3,300 rows, `last_modified` advanced to 2026-08-31, and the +272 rows are the full 2026 REG schedule — the first live 2026 data in BigQuery.

But both forced runs then failed anyway (exit 1, after 3 retries) at a different point: **Step 2/7 — Audit closing lines**, a hardcoded data-quality gate in `run_pipeline.py` that aborts the whole run if the aggregate `spread_line` null rate across 2015–current-season exceeds 5%. It's now failing because the in-progress 2026 season's future weeks don't have closing lines posted yet (58.8% null for 2026 alone), and this gate was never designed to run against a season that isn't finished — it was a one-time "is nflverse a reliable historical source" check that started getting evaluated against the live season only because a date-based `CURRENT_SEASON` constant flipped to 2026 in July. Left as found, this would have hard-failed every scheduled run all season, so only Step 1 (raw schedules) would ever have updated in-season. Full detail and the fix (downgraded to a warning, per Matt's direction) in `00-PROJECT-LEAD/SEASON_AUTOMATION_PLAN.md` Priority 0b — **the fix is in source but needs an image rebuild + redeploy to go live** (commands in that doc).

---

## 5. Bottom line going into the season

- The data that *is* in BigQuery (2015–2025, all core tables) is complete, validated, and correct as of the last good load.
- The scheduler auth fix is live and verified — the trigger chain fires and creates real executions again. `raw_nflfastr.schedules` already picked up the full 2026 REG schedule as a result.
- A second, previously-latent gate in `run_pipeline.py` is now what's blocking `pbp`/`rosters`/`curated.*` from refreshing in-season (see addendum above) — fixed in source, needs an image rebuild + redeploy before the next scheduled run to actually take effect. This is now the single highest-priority item before kickoff.
- 13 new OL/advanced-stats sources are fetched, validated, and sitting on disk, one script run away from BigQuery.
- The monitoring gap partially closes itself as a side effect: now that real executions are created and failing, the existing "Cloud Run Job — Execution Failed" alert should correctly fire on the next scheduled failure (it never could before, since no execution was ever created to fail). It still won't catch a silent success-with-stale-data case — the freshness check in Priority 4 is still worth building.

See `00-PROJECT-LEAD/SEASON_AUTOMATION_PLAN.md` for the phased plan to fix this and extend it to in-season real-time tracking.
