# PROMPT-CI-PIPELINE-DEPLOY — deploy the data pipeline from GitHub Actions instead of from Matt's laptop

Start in: C:\Users\OEM\OneDrive\Desktop\nfl-prediction-app
Written: 2026-09-19 by PROJECT-LEAD. Stage B1-2b of `PLAN-BUCKET1-DATA-COVERAGE.md`.

## Why

The data pipeline is the only component in this repo whose image is built by hand. The API
and the frontend both deploy from GitHub Actions on push. That asymmetry is why B1-2 has
taken a week, why it needs Matt's personal `gcloud`, and why it cannot be scheduled: every
GCP action in this project authenticates as `matt.lilley4@gmail.com`, so every GCP action
needs something running in his Windows profile.

Matt's requirement (2026-09-19): he wants these runs scheduled and unattended, not run by
hand. That is achievable now and does not need new infrastructure — the hard part already
exists and is proven in production.

## What already exists — do not rebuild it

`.github/workflows/api-deploy.yml` already does, on push to `main`:
`google-github-actions/auth@v2` with `secrets.WIF_PROVIDER` and `secrets.WIF_SERVICE_ACCOUNT`,
then `setup-gcloud@v2`, then `gcloud auth configure-docker`, then build and push to
`gcr.io/nfl-model-471509/...`. `setup_wif.bat` at the repo root created the OIDC provider,
scoped by attribute condition to `matt9999nfl/nfl-prediction-app`.

So Workload Identity Federation, the pool, the provider, the service account and the repo
secrets are all in place and working. This stage copies that pattern; it does not set up
federation.

## Task

A `pipeline-deploy.yml` workflow that builds `01-DATA-PIPELINE`'s image and repoints both
Cloud Run jobs to the resulting digest, authenticated by WIF, with no human and no laptop.

Design points, in order of importance:

1. **`workflow_dispatch` first, not push-triggered.** The API and frontend deploy on every
   push to their paths. The pipeline must NOT — a push at the wrong moment would repoint
   jobs mid-window. Manual dispatch (and later, a scheduled dispatch in a known-quiet
   window) keeps the timing decision explicit.
2. **Pin to the digest, never `:latest`.** The 2026-09-08 image being `:latest` is the
   original defect (`QUESTIONS.md`, 2026-09-18). The workflow outputs the digest it built
   and sets both jobs to it explicitly.
3. **Record the previous digest before repointing**, in the workflow output, so a revert
   never has to be reconstructed from GCR tag history the way it was on 2026-09-18.
4. **Verification run and kill-switch.** Execute `nfl-pipeline-gameday` once, report exit
   status, the `line_snapshots` row count before and after, and `curated.games` /
   `curated.plays` counts before and after. On failure, repoint both jobs back to the
   recorded previous digest and fail the workflow.
5. **Refuse to run in a scheduled window.** Scheduled jobs (UTC): Mon 05:00, Tue 07:00,
   Tue 11:00, Tue 14:00, Fri 05:00. A first step that checks the clock and whether an
   execution is already running, and exits early rather than colliding, replaces the
   timing rule that a human was previously expected to honour.

## Check before writing the workflow — likely blocker

`api-deploy.yml` deploys a Cloud Run **service**. This workflow updates Cloud Run **jobs**.
Confirm the WIF service account actually holds `run.jobs.update` / `run.jobs.run` and
Cloud Build permissions, and report what it holds. If a role is missing, do NOT grant it —
write the exact command for Matt, the same way the `raw_lines` grant was handled on
2026-09-19. A missing grant discovered at deploy time is exactly what caused the
2026-09-18 incident.

## Read first
- `00-PROJECT-LEAD/PROJECT-CHARTER.md`, `STATE.md` (Decisions), `context/talking-to-matt.md`
- `00-PROJECT-LEAD/QUESTIONS.md`, the 2026-09-18 and 2026-09-19 entries
- `00-PROJECT-LEAD/PROMPT-DEPLOY-DATA-PIPELINE.md` — the manual steps this replaces
- `.github/workflows/api-deploy.yml` — the template to copy
- `setup_wif.bat`, `01-DATA-PIPELINE/cloudbuild.yaml`, `05-DEVOPS/instructions.md`

## Scope
Allowed to change: `.github/workflows/pipeline-deploy.yml` (new), `05-DEVOPS/ci/` copy of it,
and docs.
Must not: run the workflow, build any image, repoint or execute any Cloud Run job, change
IAM, change schedules, or touch modeling, backend or frontend code.

This stage writes a workflow and a recommendation. It deploys nothing.

## Kill-switch
Stop, write to `00-PROJECT-LEAD/QUESTIONS.md`, and tell Matt if: the WIF service account is
missing a role the workflow needs; the workflow would have to trigger on push rather than
dispatch; `cloudbuild.yaml` builds to `:latest` in a way that can't be pinned to a digest;
or any step would execute against the live project.

## Acceptance (each line true or false)
- [ ] `pipeline-deploy.yml` exists, triggers on `workflow_dispatch` only, and contains no
      `:latest` reference in any job-update step.
- [ ] It records and outputs the previous digest for both jobs before repointing.
- [ ] It contains the revert-on-failure path, and the path is reachable (not dead code).
- [ ] It contains the scheduled-window guard and the already-running check.
- [ ] The WIF service account's current roles are reported, with any missing role named and
      the exact grant command written out for Matt. No IAM changed.
- [ ] Nothing was executed against `nfl-model-471509`.

## Returns-with
`00-PROJECT-LEAD/HANDOFF-2026-09-<dd>-ci-pipeline-deploy.md`: goal achieved yes/no (first
line), commit SHA(s), the workflow path, the WIF service account's roles and any gap, and
what has to be true before the first dispatch.
