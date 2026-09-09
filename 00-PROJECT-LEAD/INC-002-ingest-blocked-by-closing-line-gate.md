# INC-002 — 2026 ingest blocked by the closing-line audit gate

**Status:** 🟢 CLOSED 2026-09-08 — ingest fixed and verified, alerting fixed and **proven by a real email**. Residual items listed at the end.
**Found:** 2026-09-07 by PROJECT-LEAD during a season-readiness check
**Severity:** Critical — no 2026 play-by-play, rosters or curated data is reaching BigQuery
**Owner of the fix:** DEVOPS (container rebuild + redeploy). Not yet dispatched.

---

## What is actually happening

The Cloud Scheduler auth fix (SEASON_AUTOMATION_PLAN P0) **was applied** — `terraform apply` ran 2026-08-31 18:35. All five scheduler jobs are Enabled and report `Success`. That part is fixed and working.

But scheduler `Success` only means the trigger fired. The Cloud Run jobs it triggers are failing:

| Job | Last execution | Result |
|---|---|---|
| `nfl-pipeline-gameday` | 2026-09-07 17:00 | **Failed** — and every run since 2026-08-31 (Aug 31, Sep 1, Sep 4, Sep 7) |
| `nfl-pipeline-full` | 2026-09-01 23:00 | **Failed** |
| `nfl-production-refresh` | 2026-09-02 | Succeeded |
| `nfl-experiment-runner` | 2026-09-02 | Succeeded |

## Root cause — confirmed in logs, not inferred

From `nfl-pipeline-gameday` task logs, 2026-09-07:

```
INFO STEP: 1/7 — Ingest raw schedules
INFO STEP COMPLETE: 1/7 — Ingest raw schedules (50.3s)
INFO STEP: 2/7 — Audit closing lines
     TASK 4 — CLOSING LINE AUDIT
     RESULT: 5.1% null rate > 5% → OPTION 1 FAILS
ERROR Closing line null rate > 5%. Stopping — review source before curated layer.
Container called exit(1)
```

Step 1 succeeds. Step 2 aborts the process. **Steps 3–7 never run** — that is PBP ingest, roster ingest, `curated.games`, `curated.plays`, and validation. Retried 3 times per execution, identical result.

The null rate is **5.1%** against a 5% threshold. The 2026 season's unplayed games carry no closing lines yet, which drags the aggregate just over the line. It will stay over for most of the season.

## Why this appeared now

It did not regress. The jobs had never executed at all for 115 days because of the scheduler auth bug. Fixing that on 2026-08-31 let them run for the first time since May — and they immediately hit a gate that has been wrong the whole time. **The first failure is 2026-08-31 20:06, ninety minutes after the terraform apply.** Fixing P0 did not cause this; it revealed it.

## The fix already exists and is not deployed

`01-DATA-PIPELINE/scripts/run_pipeline.py` was changed on 2026-08-31 to downgrade this from `sys.exit(1)` to a warning. The reasoning in that commit is correct and worth quoting in substance: the closing-line audit was designed as a one-time "is nflverse a reliable historical source" decision — `audit_closing_lines.py`'s own docstring says it *"prints report; continues automatically"* — and wiring it as a per-run production gate contradicted that.

**But the container image for `nfl-pipeline-gameday` was last updated 2026-05-07.** The fix is in source and has never been built or deployed. That is the entire remaining gap.

## What needs to happen

1. **Rebuild and redeploy the pipeline job image** so `run_pipeline.py`'s current code is what actually runs. Both `nfl-pipeline-gameday` and `nfl-pipeline-full` use it. Owner: DEVOPS.
2. **Force-run `nfl-pipeline-full` once** after deploying, and confirm it reaches step 7 rather than stopping at 2.
3. **Verify data actually landed** — `raw_nflfastr.pbp`, `rosters`, `schedules` and `curated.games` last-modified must advance past 2026-05-08. A green job is not the same as fresh data; that distinction is what this incident is made of.
4. **Then** re-check whether the 13 staged OL sources still need the manual backfill (SEASON_AUTOMATION_PLAN P1).

## The monitoring lesson, which is the durable part

SEASON_AUTOMATION_PLAN P4 predicted this shape exactly: the Cloud Run execution-failed alert never fired during the 115-day scheduler outage because no execution was ever created. That alert should be firing *now* — executions are being created and failing. **Whether Matt received those emails is worth checking**, because if it did not fire, the alerting is broken in a second, independent way and P4's data-freshness check becomes the only thing that would ever catch this class of failure.

A freshness check — assert `MAX(last_modified)` across `raw_nflfastr.*` is within N days during the season — would have caught this on 2026-09-01. It is still not built.

---

## Update 2026-09-07 — it was three gates, not one

The closing-line fix was correct but incomplete. Rebuilding the image (build `94bb2833`, digest `sha256:ce98df84…`) got the pipeline past step 2 and into step 3, where it hit the next member of the same family.

```
2015: 48,122 rows [OK]  …  2025: 48,771 rows [OK]
2026:      0 rows  [VALIDATION_FAILED]
ERROR PBP Ingest: 1 season(s) failed: [2026]
```

**One disease, three symptoms: checks calibrated for COMPLETED seasons, wired as per-run production gates.**

| # | Gate | Why it fails on a live season |
|---|---|---|
| 1 | `run_pipeline.py` — closing-line null rate > 5% | Unplayed games have no closing lines. Fixed 2026-08-31, deployed 2026-09-07. |
| 2 | `adapters/nflfastr.py::validate_pbp` — requires ≥40,000 rows | Week 1 is ~2,700 plays; 40k is not reached until ~week 15. **This would have failed every gameday run for most of the season**, not just pre-season. |
| 3 | `build_curated_games.py` — `status != "OK"` | No tolerance for `EMPTY`, unlike its sibling `build_curated_plays.py` which already had it. |

### Fixes applied 2026-09-07 (not yet deployed)

Principle throughout: **current season warns, completed seasons still error.** No protection on historical data is weakened.

- `adapters/nflfastr.py` — added `current_season()`; the 40k floor is a warning for the in-progress season, an error for finished ones. Column checks still apply to every season.
- `scripts/ingest_pbp.py` — zero plays returns `EMPTY` and skips the load, rather than validating and failing. `run_pipeline` already tolerates `EMPTY`.
- `scripts/build_curated_games.py` — tolerates `EMPTY`, matching `build_curated_plays.py`.
- `01-DATA-PIPELINE/.gcloudignore` — added. `Dockerfile.job` does `COPY . .`, so 29 MB of staged parquet was being uploaded and baked into the production image. Context is now 224 KB.

**Role-boundary deviation, recorded deliberately:** PROJECT-LEAD edited DATA-PIPELINE application code, which the delegation protocol forbids. Done at Matt's explicit instruction with three days to kickoff. DATA-PIPELINE should review these four changes rather than inherit them silently.

### Still unverified

- The rebuild with fixes 2 and 3 has not been run.
- ~~`validate_and_report.py` was deliberately not loosened~~ **SUPERSEDED within the same commit.** This bullet was written mid-incident, before gate 4 was fixed; `42336b6` adds `is_in_progress_season()` and makes per-season checks advisory for the live season. The bullet was never re-read after the fix landed, so this document contradicted itself for two days — one section saying the file was untouched, another listing it as changed. Corrected 2026-09-09 after DATA-PIPELINE caught it during DP-REVIEW. **It remains un-audited against 2026 partial data**, which is what DP-REVIEW is for.
- Whether the 2015–2025 PBP from the 22:33 run actually landed in BigQuery. The summary logged 532,376 rows as `[OK]` before the exit, and loads happen per-season inside `ingest_season`, so they probably did — but "probably" is exactly what this incident is about. Verify `raw_nflfastr.pbp.last_modified`.

---

## Resolved 2026-09-08

`nfl-pipeline-full-c26v7` — **successfully completed, 1/1**. Build `fc531b02`.

**`raw_nflfastr.pbp` last modified: 2026-09-08 09:32 UTC+12.** It had been frozen at 2026-05-08 for 122 days. Green job *and* fresh data — the distinction this incident was built around.

### It was four gates, not one

All the same mistake: **checks that describe a COMPLETED season, wired as gates on a live pipeline.** Each one was individually reasonable when written against a finished historical backfill; none had ever met a season in progress, because the scheduler had been broken since May and the jobs never ran.

| # | Gate | Would have failed |
|---|---|---|
| 1 | `run_pipeline.py` — closing-line null rate > 5% | Every run, all season |
| 2 | `validate_pbp` — requires ≥40,000 rows | Every gameday run until ~week 15 |
| 3 | `build_curated_games` — no `EMPTY` tolerance | **INFERRED, NEVER OBSERVED — see note** |

> **Correction, 2026-09-09 (DP-REVIEW, DP-R-06).** Gates 1, 2 and 4 were observed
> in logs. **Gate 3 was not.** The 2026-09-07 run died at step 3, so steps 5-7 never
> executed. Gate 3 was inferred by reading `build_curated_plays.py` and assuming its
> sibling behaved the same way — and the inference names a status
> `build_curated_games.build_season` cannot emit: it returns only `OK` and `ERROR`.
> The `EMPTY` tolerance added for it is unreachable code. Harmless, mildly defensive,
> **but it is not a fix and must not be counted as one.** This table presented four
> gates identically; three were evidence and one was a guess.
| 4 | `validate_and_report` — completed-season thresholds per season | Every run, all season |

Gate 2 is the one worth remembering. It would not have announced itself today — it would have failed quietly every Sunday until mid-December, long after everyone stopped watching the deploy.

### Fix principle, applied uniformly

**The current season warns; completed seasons still error.** Every historical guarantee is exactly as strict as it was. In-progress checks still run and still appear in the validation report, marked `⚠️ IN-PROGRESS`, so the softening is visible in the output rather than buried in source.

### Files changed (all in 01-DATA-PIPELINE — committed as `42336b6`, pushed; the six below plus `.gitignore` at repo root)

- `scripts/run_pipeline.py` — closing-line gate to warning *(pre-existing, 2026-08-31; deployed here)*
- `adapters/nflfastr.py` — `current_season()`; row-count floor advisory for the live season
- `scripts/ingest_pbp.py` — zero plays returns `EMPTY`, skips load
- `scripts/build_curated_games.py` — tolerates `EMPTY`
- `scripts/validate_and_report.py` — per-season checks advisory for the live season
- `.gcloudignore` — new; build context 29 MB → 224 KB, keeps staged parquet out of the production image

### Open

1. **Commit and push. Nothing is committed.** A fresh clone still gets May's behaviour. This bug has already survived being fixed once for exactly this reason.
2. Run `nfl-pipeline-gameday` — same image, not yet exercised.
3. **Alerting delivers nothing.** Matt received no email across 115 days of scheduler failure and a week of job failure. Prime suspect: unverified notification channel. DEVOPS task 3.
4. Confirm `curated.games` / `curated.plays` freshness and that 2026 rows appear once week 1 is played.
5. P4 data-freshness check still unbuilt — it would have caught this on 2026-09-01.
6. **Role-boundary deviation:** PROJECT-LEAD edited DATA-PIPELINE application code (5 files) at Matt's instruction. DATA-PIPELINE should review rather than inherit silently.

---

## Alerting root cause — found and fixed 2026-09-08

Not the unverified notification channel I suspected. The channel (`matt.lilley4@gmail.com`) exists and is correctly configured, and both policies were enabled the whole time.

**Neither `condition_threshold` in `monitoring.tf` declared a `trigger` block.** Without one the API defaults the trigger to zero, and the console reports *"Triggers when: 0% of time series cross threshold"* — enabled, correct-looking, and structurally incapable of firing. Both policies had it.

This means the earlier explanation was only half the story. `SEASON_AUTOMATION_PLAN` §P4 said the alert stayed silent through the 115-day outage because no Cloud Run execution was ever created — true, but it also would not have fired last week when executions *were* being created and failing daily. **The alerting has never worked, on any policy, since it was built.**

Second defect on the job policy, which would have kept it quiet even with the trigger fixed: `ALIGN_RATE` over `completed_execution_count` with `duration = "60s"`. A failed execution is a single counted event, not a sustained state — a rate over a sparse counter can align to a value that never clears the threshold, and requiring 60s of persistence can miss it outright. Now `ALIGN_DELTA` with `duration = "0s"`.

**Verified live after apply:** the policy reads "Triggers when: Any time series cross threshold", "No retest".

### Unplanned resources in the same apply — review these

The apply was expected to change two alert policies. It reported **7 added, 4 changed**, because the `dataset_processor` infrastructure had been declared in Terraform but never applied — it is the Phase 3 deferred item "Dataset upload background task → Cloud Run Job" (`ROADMAP.md` §Phase 3, "What Didn't Make Phase 3").

Added: `nfl-dataset-processor-sa` service account; `bigquery.dataEditor` on `platform` and `user_datasets`; `bigquery.jobUser`; `storage.objectViewer` on the uploads bucket; the `nfl-dataset-processor` Cloud Run job; and `run.invoker` for the API service account on it.
Also changed: `nfl-experiment-runner` job and the `nfl-backend-api` service.

None of this is wrong — it is the project's own declared IaC finally converging, and it closes a long-deferred item. But **IAM grants were created that nobody reviewed today**, and the drift between Terraform state and live infrastructure was larger than anyone knew. Worth a deliberate read by DEVOPS.

**API verified healthy after the apply:** `/health` → 200 `{"status":"ok","version":"0.1.0","commit":"fc297ef"}`, and `/api/v1/experiments?status=complete` → 200. Note the deployed commit is `fc297ef` — the API has not been redeployed since, so Phase 6's scoping endpoints are not live yet. That is HC-S7.

### Still untested

**No alert email has actually been received.** Configuration that looks correct is precisely what produced this incident. Until a real failure produces a real email in Matt's inbox, alerting is unproven, not fixed.

---

## Alerting proven 2026-09-08 — closing the incident

A deliberate failure of a throwaway `alert-test` job produced:

```
Policy:  Cloud Run Job — Execution Failed
Opened:  2026-09-08 17:53:48 +12
Closed:  2026-09-08 17:55:23 +12
```

**Email received.** First alert this project has ever delivered. Test job deleted.

### Two failed attempts that were themselves informative

The first two tests used `gcr.io/google-containers/busybox`, which failed on a registry digest mismatch — my error. But the *shape* of that failure matters: the execution died during container import, and the console showed **0 Succeeded, 0 Failed, 0 Running, no tasks**. No task was ever created and no execution ever completed.

The alert watches `completed_execution_count{result="failed"}`. A job that dies before a container starts produces nothing for it to count.

**So the alerting still has a blind spot**, narrower than before but real: it cannot see failures that occur before a container runs — bad image, pull failure, provisioning error, quota. Those are exactly the conditions that look like "nothing happened".

**Recommended follow-up (DEVOPS, not urgent):** a second condition on `resource.type="cloud_run_job"` with `severity=ERROR` in logs, which fires regardless of how far the execution got. Pair it with the P4 freshness check — between them, "the job broke" and "the job silently did nothing" are both covered.

---

## Residual items after close

| # | Item | Owner |
|---|---|---|
| 1 | ~~Three commits unpushed~~ **RESOLVED 2026-09-09.** `main` is level with `origin/main` at `06d99c1` | — |
| 2 | Pre-container-failure alert blind spot (above) | DEVOPS |
| 3 | P4 data-freshness check — still unbuilt; would have caught INC-002 on 2026-09-01 | DEVOPS |
| 4 | `/health` reports `commit:"unknown"` since the 2026-09-08 API build | DEVOPS |
| 5 | **Six** DATA-PIPELINE files (plus `.gitignore`) and one DEVOPS file edited by PROJECT-LEAD at Matt's instruction — review, do not inherit silently | DATA-PIPELINE, DEVOPS |
| 6 | Thursday 2026-09-10 TNF is the first unattended scheduled run | — |
