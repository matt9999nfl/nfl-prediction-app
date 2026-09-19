# HANDOFF — ci-pipeline-deploy (B1-2b)

**Goal achieved: yes.** `pipeline-deploy.yml` exists, dispatch-only, pinned to digest
throughout, with a recorded-previous-digest revert path and both required guards. No IAM
gap found — nothing written for Matt to grant. Nothing was executed against
`nfl-model-471509`.

## Commit(s)

Not yet committed at time of writing this file — see "Commit" note at the end (same
paper-trail pattern as prior stages this week: land locally, note push status separately).

## What was written

- `.github/workflows/pipeline-deploy.yml` (new)
- `05-DEVOPS/ci/pipeline-deploy.yml` (copy, per the existing — if imperfectly maintained —
  convention noted in `05-DEVOPS/instructions.md`)
- This handoff.

## Design, against the prompt's five points

1. **`workflow_dispatch` only.** No `push` trigger anywhere in the file. Confirmed by
   parsing the YAML: trigger block is `{workflow_dispatch: {}}` only.
2. **Digest, never `:latest`.** The build step tags with the short git SHA only (no
   `:latest` push, unlike `api-deploy.yml`'s service pattern, which does push `:latest`
   for its own reasons). Every job-update step uses `image@sha256:...`, resolved via
   `gcloud container images describe ... --format='value(image_summary.digest)'` right
   after the push — the same command used to reconstruct the 2026-09-18 digest after the
   fact, now run proactively instead of forensically.
3. **Previous digest recorded before repointing.** `Record previous digests` step runs
   before the build/push/repoint steps and captures both jobs' current image via
   `gcloud run jobs describe`, into step outputs used by the revert path.
4. **Verification run + kill-switch.** Executes `nfl-pipeline-gameday --wait` with
   `continue-on-error: true`, captures `raw_lines.line_snapshots` / `curated.games` /
   `curated.plays` row counts both before and after (via `bq query`), and on failure
   (`steps.verify.outcome == 'failure'`) reverts both jobs to the recorded previous digest
   and fails the workflow (`exit 1`). This path is reachable — it's gated on the real step
   outcome, not a placeholder condition.
5. **Scheduled-window guard + already-running check**, as the first two real steps (after
   auth/setup). The window guard blocks 30min before / 60min after each of Mon 05:00, Tue
   07:00, and Fri 05:00 UTC, and a wide 30min-before / 240min-after blackout around Tue
   11:00 UTC (covers the full rebuild through the 14:00 production refresh that reads its
   output) — replacing the timing rule `PROMPT-DEPLOY-DATA-PIPELINE.md` asked a human to
   honour by hand. Tested locally against 11 synthetic timestamps, including exact-boundary
   cases (30/60/240 min to the minute) and a week-wraparound case — all matched intent. The
   already-running check reads `status.conditions[0].status` for each job's most recent
   execution and refuses to proceed if either reads `Unknown` (running) — this is
   specifically the failure mode that produced the 2026-09-18 collision (two independently
   retrying executions dropping the same tables at once).

## WIF service account — checked, no gap found

The prompt flagged this as the likely blocker, the same class of gap as `raw_lines`. It
isn't one here. Found by checking live GCP state rather than trusting
`05-DEVOPS/DEVOPS_COMPLETION_REPORT.md` (2026-05-06, stale — its WIF pool name and SA
plan don't match what's actually deployed):

- The WIF pool/provider (`github-pool`/`github-provider`) has exactly one service account
  bound to it via `roles/iam.workloadIdentityUser`, scoped to
  `matt9999nfl/nfl-prediction-app`: **`terraform-ci@nfl-model-471509.iam.gserviceaccount.com`**.
  This must be `secrets.WIF_SERVICE_ACCOUNT` — it's the only account the pool can
  impersonate for this repo, and it matches `api-deploy.yml`'s already-working pattern.
- `terraform-ci`'s project-level roles: `roles/editor`, `roles/iam.securityAdmin`.
- Checked `roles/editor`'s actual included-permissions list (`gcloud iam roles describe
  roles/editor`, 12,112 permissions) rather than assuming from the role name. It includes
  `run.jobs.update`, `run.jobs.run`, `run.executions.get`/`list`, the full `cloudbuild.builds.*`
  set (not used by this workflow's docker-build-in-runner design, but present), and
  `artifactregistry.repositories.uploadArtifacts` (the modern gcr.io push path) plus
  `logging.logEntries.list`.
- BigQuery access for the row-count queries doesn't come through `roles/editor`'s
  permission list at all — it comes through the `projectWriters` special-group ACL entry
  present on every dataset checked (`raw_nflfastr`, `curated`, `raw_lines` all have
  `{"role": "WRITER", "specialGroup": "projectWriters"}`), which `roles/editor` maps into
  automatically. Same mechanism, different layer — worth recording since it's the kind of
  thing that looks like a gap if you only grep the IAM permission list.
- One empirical cross-check: `api-deploy.yml` already builds and pushes a *different* image
  (`nfl-backend-api`) to the same `gcr.io/nfl-model-471509/` registry using this exact
  account via this exact WIF path, successfully, in production. A second image name in the
  same project under the same account isn't a new permission surface.

**No grant needed. No command written for Matt on this stage.**

## Security note — `terraform-ci`'s role, not a blocker but worth recording

`terraform-ci` holds `roles/editor` *and* `roles/iam.securityAdmin` project-wide, and it's
the only account any GitHub Actions workflow in this repo can impersonate (it's the sole
`roles/iam.workloadIdentityUser` binding on the WIF pool). That was a reasonable shape when
it existed only to run Terraform. It now also builds/pushes every container image and
updates/runs Cloud Run jobs and services for three separate deploy workflows — a much
larger blast radius riding on the same identity, and `iam.securityAdmin` is the sharp edge:
it can rewrite project IAM policy, including granting itself more access. A compromised PR
or a leaked WIF trust boundary on this repo is therefore a path to persistent owner-level
control, not just "can redeploy things." The WIF attribute condition scopes this to
`matt9999nfl/nfl-prediction-app` specifically, which bounds it somewhat. Not fixing this
now — it's an IAM change, out of this stage's scope, and nothing found suggests it's been
exploited — but recorded in `STATE.md`'s background list so it doesn't sit unrecorded for
years. Suggested shape when someone picks it up: a narrow deploy-only service account
(`roles/run.admin` + `roles/artifactregistry.writer`, no `securityAdmin`) for the three
deploy workflows, with `terraform-ci`'s current broad grant kept only for actual
`terraform apply` runs.

## What has to be true before the first dispatch

1. `secrets.WIF_PROVIDER` and `secrets.WIF_SERVICE_ACCOUNT` are already configured on this
   repo (proven by `api-deploy.yml` working) — nothing new to add.
2. This file must be on `main` for `workflow_dispatch` to be dispatchable from the Actions
   tab / `gh workflow run` (GitHub only lists dispatchable workflows that exist on the
   default branch). Not yet pushed — see below.
3. Nothing else. `--max-retries=0` is now folded into the "Repoint both jobs" step itself
   (and the revert step), so the Monday-queued manual `gcloud run jobs update --max-retries=0`
   is no longer a separate prerequisite — dispatching this workflow applies it as part of
   the same repoint that sets the digest. The last manual gcloud step B1-2a left queued is
   gone; a first dispatch through this workflow is now push + dispatch, nothing else.
4. First dispatch should happen outside a scheduled window (the workflow enforces this
   itself, but choosing a deliberate time avoids wasting a dispatch to the guard).

## Commit

`.github/workflows/pipeline-deploy.yml`, `05-DEVOPS/ci/pipeline-deploy.yml`, and this
handoff are landed as a local commit. Not pushed — same standing constraint as the rest of
this week's paper trail (`git push` to `main` needs separate sign-off in this session).
Unlike the docs-only commits, **this one is safe to push to `main` directly without
triggering anything**: the file lives under `.github/workflows/` but isn't
`api-deploy.yml` or `frontend-deploy.yml`, so it doesn't match either existing workflow's
path filter, and it only defines `workflow_dispatch` itself, so merely landing it on `main`
fires nothing.
