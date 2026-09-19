# PROMPT-HARDEN-PIPELINE-WORKFLOW — three defects in pipeline-deploy.yml, before the first dispatch

Start in: C:\Users\OEM\OneDrive\Desktop\nfl-prediction-app
Written: 2026-09-19 by PROJECT-LEAD. Stage B1-2b follow-up. Blocks the first dispatch.

## Why

`pipeline-deploy.yml` (`dcf7c8a`, amended `91ab923`) is good and is the right shape. Three
defects were found reading it back, all verified against the file on disk. Each is small.
Two of them repeat mistakes this project has already paid for once.

## A — the kill-switch does not cover a hang

`if: steps.verify.outcome == 'failure'` on the revert step. A cancelled or timed-out job
skips it, leaving both Cloud Run jobs pinned to the NEW digest with no revert. There is no
`timeout-minutes` anywhere in the file (verified: zero matches), so GitHub's 6-hour default
applies to `gcloud run jobs execute --wait`.

Fix: `timeout-minutes` on the `deploy` job, sized to the real work (build + push + repoint +
a ~12-minute verification run — 30 is a sane start, justify whatever you pick), and change
the revert condition to `always() && steps.verify.outcome != 'success'` so a cancel or a
timeout still reverts.

## B — the window guard measures dispatch time, not finish time

Buffers are `30` minutes before each scheduled window (verified: all four entries). But the
workflow then runs for roughly 20–25 minutes. A dispatch that passes the guard 31 minutes
before a scheduled job is still executing its verification run when that job fires.

**This is the 2026-09-18 mistake exactly.** That incident's own write-up says the estimate
was wrong because it benchmarked the gap against the old code's run time rather than the
new one's. A 30-minute guard in front of a 25-minute workflow is the same arithmetic error
in a new place.

Fix: raise the `before` buffer so it exceeds the workflow's own worst-case runtime (90 is a
reasonable start), **or** re-check the clock immediately before the verification-run step so
the decision is made when it matters. Either is acceptable; say which and why.

## C — `docker build` ignores `.gcloudignore`, so 29MB of parquet lands in the image

The Dockerfile and the build context path are equivalent to the old `cloudbuild.yaml` path —
that part is fine. The context *contents* are not.

`01-DATA-PIPELINE/.gcloudignore` exists **specifically** to keep `new_sources_staging/`
(29MB of staged parquet), `__pycache__/`, `*.pyc`, `*.log` and `.git/` out of the build
context. Its own comment says why: "Dockerfile.job does `COPY . .`, so anything left here is
baked into the production image." It was added 2026-09-07 during INC-002.

There is no `.dockerignore` (verified: file does not exist). `docker build` does not read
`.gcloudignore`. So this workflow re-introduces exactly what INC-002 fixed.

Fix: add `01-DATA-PIPELINE/.dockerignore` mirroring `.gcloudignore`, and add a note in both
files that the two must stay in sync. Report the image size before and after if you can get
both; otherwise report the context size the build sends.

## Read first
- `.github/workflows/pipeline-deploy.yml` and the `05-DEVOPS/ci/` copy (they must stay identical)
- `01-DATA-PIPELINE/.gcloudignore`, `Dockerfile.job`, `cloudbuild.yaml`
- `00-PROJECT-LEAD/QUESTIONS.md`, the 2026-09-18 entry (for B)
- `docs/PIPELINE_REMEDIATION_001.md` / INC-002 references (for C)
- `00-PROJECT-LEAD/context/talking-to-matt.md`

## Scope
Allowed to change: `.github/workflows/pipeline-deploy.yml`, `05-DEVOPS/ci/pipeline-deploy.yml`,
a new `01-DATA-PIPELINE/.dockerignore`, `01-DATA-PIPELINE/.gcloudignore` (comment only), docs.
Must not: dispatch the workflow, build any image, repoint or execute any Cloud Run job,
change IAM, or touch modeling, backend or frontend.

## Kill-switch
Stop, write to `00-PROJECT-LEAD/QUESTIONS.md`, and tell Matt if: fixing A would require
removing `continue-on-error` from the verification step (it is load-bearing — the revert
needs to run after a failure); the two workflow copies have diverged; or any change would
need a dispatch to validate.

## Acceptance (each line true or false)
- [ ] `deploy` job has `timeout-minutes`, and the number is justified in a comment.
- [ ] The revert step fires on cancel and timeout, not only on `failure`.
- [ ] The window guard's `before` buffer exceeds the workflow's worst-case runtime, or the
      clock is re-checked immediately before the verification run. Which one, and why, stated.
- [ ] `01-DATA-PIPELINE/.dockerignore` exists and covers everything `.gcloudignore` covers.
- [ ] Build-context size reported before and after the `.dockerignore`.
- [ ] Both copies of the workflow parse as YAML and are byte-identical (`diff` exit 0).
- [ ] Nothing dispatched, built, repointed or executed.

## Returns-with
`00-PROJECT-LEAD/HANDOFF-2026-09-<dd>-harden-pipeline-workflow.md`: goal achieved yes/no
(first line), commit SHA(s), the three fixes with before/after, context size before and
after, and confirmation that the first dispatch is now unblocked.
