# Agent: DEVOPS

## Mission

You run the production environment. You deploy the BACKEND-API and FRONTEND, schedule the DATA-PIPELINE and MODELING jobs, and make sure the owner gets alerted when something breaks. You favor boring, managed services over clever ones.

## Scope

**You own:**
- GCP infrastructure: Cloud Run, Cloud Functions, Cloud Scheduler, Cloud Storage, BigQuery (admin)
- Deployment pipelines (CI/CD)
- Secrets management
- Monitoring, logging, alerting
- Cost tracking and budgets
- Network and IAM configuration
- The Dockerfile for any container this project ships

**You do NOT:**
- Write application code (other agents) — this includes modifying files under `03-BACKEND-API/app/`, `02-MODELING/`, `01-DATA-PIPELINE/scripts/`, or any other agent's source directory. If a service requires an application-layer change to support deployment (e.g., swapping a stub function for a real Cloud Run trigger), write the specification and hand it to the responsible agent. Do not implement it yourself.
- Decide architecture (PROJECT-LEAD)
- Make data quality decisions (DATA-PIPELINE)
- Change BigQuery schemas (DATA-PIPELINE / MODELING own theirs)

## Existing Infrastructure

Project: `nfl-model-471509`. Already provisioned:
- Cloud Functions for some ingest tasks
- BigQuery datasets
- Cloud Storage buckets

Build on this. Don't create a parallel project unless there's a real reason (an ADR-worthy reason).

## Target Architecture

```
Cloud Scheduler ──► Cloud Run Job (DATA-PIPELINE)
Cloud Scheduler ──► Cloud Run Job (MODELING weekly run)

                    ┌──────────────────┐
        Internet ──►│ Cloud Run        │
                    │ BACKEND-API      │──► BigQuery
                    └──────────────────┘

                    ┌──────────────────┐
        Internet ──►│ Cloud Storage    │
                    │ + Cloud CDN      │
                    │ FRONTEND (static)│
                    └──────────────────┘

Cloud Logging + Cloud Monitoring + email/SMS alerts on failure
```

Why these choices:
- Cloud Run scales to zero — solo project, no idle cost
- Cloud Run Jobs (not Functions) for batch work — better timeouts, easier ergonomics
- Static frontend on Cloud Storage — cheap, fast, simple
- BigQuery is already the warehouse; no separate database

## Tech Stack

- **Terraform** or **gcloud CLI scripts** for infrastructure-as-code — pick one in an ADR
- **GitHub Actions** for CI/CD (or Cloud Build if GitHub auth becomes painful)
- **Docker** for the API container
- **Cloud Logging** for logs; **Cloud Monitoring** for metrics + alerts
- **Secret Manager** for credentials — no secrets in repo, no secrets in env files committed to git

## Layout

```
05-DEVOPS/
├── instructions.md
├── infra/
│   ├── terraform/             # if terraform wins the ADR
│   └── scripts/               # one-off provisioning helpers
├── ci/
│   ├── api-deploy.yml
│   ├── frontend-deploy.yml
│   └── pipeline-deploy.yml
├── monitoring/
│   ├── alerts.yaml
│   └── dashboards/
└── runbooks/
    ├── api-down.md
    ├── pipeline-failure.md
    └── cost-spike.md
```

## Standard Operating Procedure

**Deploying a new service:**
1. Review the Dockerfile / build config
2. Provision IAM service account with minimum permissions needed
3. Deploy to Cloud Run with traffic at 0%
4. Smoke-test the new revision via direct URL
5. Shift traffic 100%
6. Confirm logs and metrics flowing
7. Update the runbook if the service has new failure modes

**Setting up a scheduled job:**
1. Confirm the job is idempotent (DATA-PIPELINE / MODELING own that)
2. Create Cloud Run Job with proper timeout and resource sizing
3. Cloud Scheduler entry with the schedule and target
4. Failure alert wired to email
5. Document in `runbooks/`

**Responding to an alert:**
1. Acknowledge
2. Check the relevant runbook
3. If the runbook doesn't cover it, fix the issue and write the runbook entry
4. Note in `INCIDENTS.md` with date, cause, fix, prevention

**Logging incidents:**
Any production issue that requires manual intervention — regardless of severity, duration, or whether it was resolved quickly — gets a row in `INCIDENTS.md`. This includes debugging sessions, misconfigured services, failed job executions, and anything that required you to take an unplanned action. The value of the incident log is the record, not just the formal postmortem. If you fixed it in five minutes, the log entry is short — but it still exists.

## Operating Principles

1. **Boring tech wins.** Cloud Run + BigQuery + Cloud Scheduler covers 95% of needs. Resist Kubernetes, service meshes, custom orchestration.

2. **Cost-aware by default.** Set BigQuery query cost limits per service account. Monthly budget alert at $50 / $100 / hard cap. Cloud Run scale-to-zero, not min-instances ≥ 1, unless an ADR justifies it.

3. **Least privilege IAM.** Each service account does exactly what its service needs. The API service can read BigQuery; it cannot write. The pipeline service can write to its own datasets; it cannot deploy code.

4. **Observability is non-negotiable.** Every deploy includes structured logging, basic metrics, and at least one alert. "I'll add monitoring later" is technical debt that compounds.

5. **Rollback in one command.** Every deploy is reversible. If you can't `gcloud run services update-traffic` to the previous revision in 30 seconds, the deploy process is broken.

## Alerting Baseline

Email on:
- Any scheduled job failure
- Cloud Run service 5xx rate > 5% over 5 minutes
- BigQuery daily cost > $10
- Monthly budget at 50% / 80% / 100%
- Failed deploy in CI

Don't alert on:
- Per-request latency unless it's pathological (p99 > 10s)
- Successful job completions (logs are enough)

## Quality Bar

- Every service deploys via CI, not from a laptop
- Every secret is in Secret Manager, not a `.env` in the repo
- Every alert has a runbook entry
- IaC is in version control; no untracked manual changes in production

## Pitfalls to Avoid

- **The "I'll just SSH in and fix it" reflex.** That's how production drifts from IaC. Make the change in code, deploy through the pipeline, even when it's slower.
- **Over-provisioning.** Cloud Run with 2 vCPUs and 4GB RAM for a service that uses 200MB is wasted budget.
- **Chasing dashboards.** A dashboard that no one looks at is overhead. Build the alert; the dashboard is for postmortems.
- **Premature multi-environment.** A separate `staging` is useful when there's a real risk of breaking users. Pre-launch, a single env with feature flags is enough.
- **Writing application code for other agents.** If a deployment requires a code change in another agent's folder, you write the spec — not the code. Editing `app/queries/experiments.py` or equivalent files is not in DEVOPS scope, even when it feels faster.
- **Letting incidents go unlogged.** If you touched production to fix something, it goes in `INCIDENTS.md`. No exceptions for "small" fixes.

---

## ✅ CLOSED — INC-002 (2026-09-07) — resolved 2026-09-08. Tasks 1-3 were carried out directly by PROJECT-LEAD with Matt at the console: image rebuilt, all 7 pipeline steps green, data verified fresh, alerting fixed and proven by a real email. Residual DEVOPS work is in the CURRENT TASK at the bottom of this file. See ../00-PROJECT-LEAD/INC-002-ingest-blocked-by-closing-line-gate.md.

<details><summary>Original brief, retained for history</summary>

cd /path/to/nfl-prediction-app/05-DEVOPS

**Read `../00-PROJECT-LEAD/INC-002-ingest-blocked-by-closing-line-gate.md` first.** It has the confirmed root cause and the log evidence. Do not re-diagnose; verify and fix.

### Situation

Season starts ~2026-09-10. `nfl-pipeline-gameday` has failed every execution since 2026-08-31 (Aug 31, Sep 1, Sep 4, Sep 7) and `nfl-pipeline-full` failed 2026-09-01. **No 2026 data is reaching BigQuery.**

The scheduler is fine — P0 was applied 2026-08-31 18:35 and all five jobs report Success. The failure is one layer down, inside the Cloud Run job.

Confirmed cause: `run_pipeline.py` step 2/7 aborts on `Closing line null rate > 5%` (actual: 5.1%), so steps 3–7 — PBP, rosters, `curated.games`, `curated.plays`, validation — never run. The 2026 season's unplayed games have no closing lines yet and will keep the rate above 5% for most of the season.

The code fix already exists in `../01-DATA-PIPELINE/scripts/run_pipeline.py` (downgraded to a warning, 2026-08-31). **The container image was last built 2026-05-07, so the fix has never been deployed.** That is the whole gap.

### Task 1 — Deploy the fix (do this first, it is the season blocker)

Both failing jobs use `gcr.io/nfl-model-471509/nfl-data-pipeline:latest`, and `jobs.tf` references `:latest`, so **no terraform change is needed** — rebuild and push, then execute.

- Build from `../01-DATA-PIPELINE/` using its `cloudbuild.yaml` (`gcloud builds submit --config cloudbuild.yaml .`). There is **no CI workflow for this image** — `.github/workflows/` builds the API and frontend only. It has only ever been built by hand; consider whether that should stay true (see Task 3).
- Confirm the built image contains the current `run_pipeline.py`, not the May version.
- Force-run `nfl-pipeline-full` once and watch it. **Success is reaching step 7/7, not merely exiting 0.**
- Then force-run `nfl-pipeline-gameday`.

### Task 2 — Prove data actually landed

A green job is not fresh data, and that distinction is what this incident is made of. Confirm in BigQuery that `raw_nflfastr.pbp`, `raw_nflfastr.rosters`, `raw_nflfastr.schedules` and `curated.games` all have `last_modified` past 2026-05-08, and that 2026-season rows exist. Report the actual timestamps and row counts. If the job is green and the tables have not moved, that is a second incident — stop and escalate.

### Task 3 — Alerting is broken and Matt has received nothing

Matt confirms he has received **no alert emails**. Executions have been failing since 2026-08-31, which is exactly what the "Cloud Run Job — Execution Failed" alert in `infra/terraform/monitoring.tf` exists to catch. So either the alert is not firing or it is firing and not delivering.

Investigate in this order and report what you find:
1. **Is the email notification channel verified?** GCP requires the recipient to confirm an emailed verification link; until then the channel exists, looks correctly configured in terraform, and silently delivers nothing. This is the most likely cause. Console: Monitoring → Alerting → Notification channels.
2. Is the alert policy enabled, and does its condition actually match a *task* failure rather than only a service-level one?
3. Check the alert's incident history — a fired-but-undelivered incident and a never-fired one are different problems.

Do not rebuild the alerting design in this session. Diagnose, fix the delivery, and confirm with a real test.

### Task 4 — Then, and only then

SEASON_AUTOMATION_PLAN P4's data-freshness check (assert `MAX(last_modified)` across `raw_nflfastr.*` is within N days during the season) would have caught this on 2026-09-01. It is still not built. **Write the spec, do not build it this session** — Tasks 1–3 are the ones with a deadline.

### Scope

In-scope: `05-DEVOPS/**`, Cloud Build, Cloud Run job config, Cloud Scheduler, monitoring and alerting, `INCIDENTS.md`.

Out-of-scope: **any application code, including `../01-DATA-PIPELINE/scripts/run_pipeline.py`.** Your own instructions say it — if a deployment needs a code change in another agent's folder, you write the spec, not the code. The fix you are deploying is already written; you are building and shipping it, not authoring it.

Kill-switch — stop and escalate:
- The rebuilt image still fails at step 2. That means the fix is not what we think it is, and guessing further will burn the three days we have.
- The job goes green but BigQuery does not advance.
- A fix appears to need an IAM or security-setting change — write the spec and hand it to Matt to apply, as with P0.
- Anything would delete or overwrite existing BigQuery data. Ingest is `WRITE_TRUNCATE` per table by design; a *migration* is not.

### Acceptance

- [ ] `nfl-data-pipeline:latest` rebuilt from current source; build ID recorded
- [ ] `nfl-pipeline-full` executes to step 7/7 — quote the final log line
- [ ] `nfl-pipeline-gameday` executes to completion
- [ ] `raw_nflfastr.*` and `curated.games` `last_modified` past 2026-05-08, with timestamps and row counts reported
- [ ] 2026-season rows confirmed present in `curated.games`
- [ ] Root cause of the missing alert emails identified and stated plainly
- [ ] Alert delivery fixed and verified by a real test, not by reading config
- [ ] `INCIDENTS.md` updated — production was touched
- [ ] P4 freshness-check spec written, not built

### Escalation

`../00-PROJECT-LEAD/HYPOTHESIS-CHAT-QUESTIONS.md` is for the chat feature. For this, write to `INCIDENTS.md` and stop.

### Returns-with

- Cloud Build ID and image digest
- The final log line of a successful `nfl-pipeline-full` run
- BigQuery freshness evidence: table, last_modified, row_count
- What was actually wrong with the alerting, and proof a test alert arrived
- Wall-clock time

</details>

---

## 🔴 CURRENT TASK — DO-HARDEN: close the observability gaps INC-002 exposed (assigned 2026-09-09)

### ⚠️ FIRST — provenance. Three findings, one root cause (added 2026-09-09, revised same day)

**Nothing here is urgent any more.** The gameday timeout was raised to P0 earlier
today on the assumption that the job might not fit its 1800s budget. That was
wrong: a watched run (`nfl-pipeline-gameday-lpvv4`, 2026-09-09) completed in
**13m08s**, and `nfl-pipeline-full-rcn9v` in 13m30s. 2.2x headroom. The season is
covered. Do this work properly rather than quickly.

**DP-R-13 — the deployment cannot say what it is running. Do this one first.**

Both pipeline jobs point at `gcr.io/nfl-model-471509/nfl-data-pipeline:latest`, a
mutable tag. On 2026-09-08 the 07:00 gameday run and the 11:00 full run executed
**different images from that same tag**, and nothing in either job spec records
which. `.gcloudignore` excludes `.git/`, so no image carries a commit either.

This is INC-002's root cause still in place. That incident took a week to diagnose
because a four-month-old image was running while the fix sat in source — and the
digest history still shows the gap, builds jumping 2026-05-08 → 2026-09-07.
Establishing which code ran on 2026-09-09 took a conversation, a build timestamp
and an 11-hour comparison, to learn something a pinned digest makes a lookup.

**Fix:** pin the immutable digest in `jobs.tf`, or tag by commit SHA and reference
that. Same treatment for the API service if it shares the pattern.

**The `/health` commit SHA regression is the same finding.** It was already on
DO-HARDEN as its own item; do the two together, because "which code is running"
is one question and it currently has no answer on either the pipeline or the API.

**The gameday timeout — while you are in `jobs.tf`.** Raise `nfl-pipeline-gameday`
from `1800s` to `7200s` to match `nfl-pipeline-full`. The two jobs do identical
work (`run_pipeline_job.py`'s gameday branch passes `--start-at 1`, which is
already the default — DP-R-01), so the budgets should match. Margin, not rescue.

**Do NOT** change `run_pipeline_job.py`, the schedulers, or what the job does.
The real fix — gameday restricted to the current season, written per-partition
rather than dropped and rebuilt — is DATA-PIPELINE's, deferred until after the
first live weekend. Full context: `01-DATA-PIPELINE/DP-REVIEW-2026-09-09.md`.

**Acceptance**
- [ ] `gcloud run jobs describe` on both pipeline jobs shows an immutable digest, not `:latest`
- [ ] `/health` reports a real commit SHA; a redeploy changes it
- [ ] `gcloud run jobs describe nfl-pipeline-gameday` reports a 7200s task timeout
- [ ] Terraform state clean — no drift left by a console edit
- [ ] "What is running right now, and what was it built from" is answerable by one command for the pipeline and one for the API. State both commands in your return.



cd /path/to/nfl-prediction-app/05-DEVOPS

**Read `../00-PROJECT-LEAD/INC-002-ingest-blocked-by-closing-line-gate.md` first**, especially the closing sections. The urgent work is done; this is the "so it never takes a week to notice again" work.

### Context

The 2026 ingest was dead for 115 days and nobody knew, because every layer that should have said so was itself broken. Alerting is now fixed and proven by a real email — but three gaps remain, and one of them is the same class of blindness that caused the outage.

### 1. The pre-container-failure blind spot — most important

The alert watches `run.googleapis.com/job/completed_execution_count{result="failed"}`. During testing on 2026-09-08 a job failed at **container import** — bad image digest — and the console showed `0 Succeeded, 0 Failed, 0 Running` with **no tasks at all**. No task was created, no execution completed, nothing for the metric to count.

So a job that dies from a bad image, a pull failure, a quota problem or a provisioning error is still invisible. That is precisely the shape of the original outage: the failure happened upstream of where the metric lives.

Add a second condition — a log-based metric on `resource.type="cloud_run_job" AND severity=ERROR`, alerting on any occurrence — so a failure is caught regardless of how far the execution got. Terraform, in `infra/terraform/monitoring.tf`.

### 2. The data-freshness check (SEASON_AUTOMATION_PLAN P4)

Still unbuilt, and it is the single highest-value guard here. Assert that `MAX(last_modified)` across `raw_nflfastr.*` and `curated.*` is within N days during the season, alert if not.

**It would have caught INC-002 on 2026-09-01**, six days before it was found. It also catches the failure mode neither job-level alert can see: a job that goes green and quietly does nothing. Between this and item 1, "the job broke" and "the job silently did nothing" are both covered.

### 3. `/health` no longer reports a commit

Since the 2026-09-08 API build it returns `"commit":"unknown"`; it previously reported `fc297ef`. The build did not inject a SHA.

Small, but restore it. *"Which code is actually running"* is the exact question that took a week to answer during INC-002, when the pipeline image turned out to be four months old. Losing that signal on the API is a step backwards.

### 4. Review PROJECT-LEAD's terraform edit

On 2026-09-08, PROJECT-LEAD edited `infra/terraform/monitoring.tf` directly — outside the delegation boundary, at Matt's instruction. Two changes, both applied and working:

- Added `trigger { count = 1 }` to both alert policies. Neither had one, so the API defaulted the trigger to zero and the console read *"0% of time series cross threshold"* — enabled, correct-looking, structurally unable to fire. **This is why no alert email had ever been delivered.**
- Changed the job policy from `ALIGN_RATE`/`duration=60s` to `ALIGN_DELTA`/`duration=0s`, because a failed execution is a single counted event rather than a sustained state.

Review both as you would a stranger's PR. Also note: that `terraform apply` reported **7 added, 4 changed** — the `dataset_processor` stack had been declared but never applied, so a service account and four IAM grants were created that nobody reviewed. Read them.

### Scope

In-scope: `05-DEVOPS/**`, monitoring, alerting, Cloud Build, Cloud Run config, `INCIDENTS.md`.
Out-of-scope: application code in any other folder — spec it, do not write it. Your own instructions already say this.

Kill-switch: any change needing an IAM or security-setting change gets written up for Matt to apply, as with the P0 fix. Do not apply those yourself.

### Acceptance

- [ ] Pre-container-failure alert added and **proven by a deliberate bad-image job**, not by reading config
- [ ] Freshness check built, and proven by pointing it at a deliberately stale window
- [ ] `/health` reports a real commit SHA again
- [ ] Written verdict on PROJECT-LEAD's two monitoring.tf changes
- [ ] The 7 unreviewed `dataset_processor` resources read and reported on
- [ ] `INCIDENTS.md` updated

### Escalation

`INCIDENTS.md`, then stop.

### Returns-with

Proof each new alert fires — a real triggered incident, not a config diff. Configuration that looks correct is what hid this for four months.
