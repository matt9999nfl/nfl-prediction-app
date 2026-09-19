# PROMPT-TERRAFORM-IMAGE-OWNERSHIP — make `terraform apply` safe again (DP-R-13)

Start in: C:\Users\OEM\OneDrive\Desktop\nfl-prediction-app
Written: 2026-09-19 by PROJECT-LEAD. Stage B1-2e of `PLAN-BUCKET1-DATA-COVERAGE.md`.

## Why

Terraform and the deploy workflows now disagree about who owns container images, and
Terraform would win. Every one of these declares `:latest` and has no `lifecycle` block:

- `cloud_run.tf:15` — the backend API service
- `jobs.tf:30` — `dataset_processor`
- `jobs.tf:71` — `experiment_runner`
- `jobs.tf:107` — `pipeline_full`
- `jobs.tf:148` — `pipeline_gameday`
- `jobs.tf:215` — `injury_capture`
- `jobs.tf:265` — `production_refresh`

Meanwhile both modeling jobs were pinned to a digest on 2026-09-18 (`STATE.md`), and
`pipeline-deploy.yml` pins both pipeline jobs to a digest on **every dispatch**. So a plain
`terraform apply` today reverts four digest pins and the API service in one command — it
undoes B1-2 and the explanations deploy together. `iam.tf:238-249` currently manages this
with a hand-maintained `-target` list, which is a warning taped to a landmine: it works
until someone, or a future session, runs `apply` without reading the comment.

`tf-plan.yml` only runs on a pull request touching `05-DEVOPS/infra/terraform/**`, so this
drift is invisible in normal use.

## Task

Terraform owns each job's and service's existence, schedule, service account, memory,
timeout and IAM. CI owns the image. When this is done, `terraform apply` is safe to run with
no `-target` list and does not move any image.

The mechanism is a `lifecycle { ignore_changes = [...] }` block on the image attribute of
each resource above. Get the address right for `google_cloud_run_v2_job` versus
`google_cloud_run_v2_service` — they nest differently — and verify with a plan, not by
reading the docs alone.

Also in scope: reconcile the rest of the DP-R-13 drift that the `iam.tf` comment names
(refresh job digest, timeout, memory) so the declared state matches live, and delete the
`-target` comment block once it is no longer needed. If a piece of drift can't be reconciled
without changing live state, leave it, name it, and say why.

## The check that proves it

`terraform plan` with no `-target`, showing **no change to any image attribute** on any of
the seven resources, against live state that currently has digest pins on `pipeline_full`,
`pipeline_gameday`, `experiment_runner` and `production_refresh`.

Run `plan` only. Do not `apply`.

## Read first
- `00-PROJECT-LEAD/PROJECT-CHARTER.md`, `STATE.md` (Decisions, and DP-R-13 in the background list)
- `00-PROJECT-LEAD/context/talking-to-matt.md`
- `05-DEVOPS/infra/terraform/jobs.tf`, `cloud_run.tf`, `iam.tf` (lines 238-249)
- `.github/workflows/pipeline-deploy.yml` — what CI sets, and when
- `05-DEVOPS/instructions.md`, `01-DATA-PIPELINE/DP-REVIEW-2026-09-09.md` (DP-R-13)

## Scope
Allowed: `05-DEVOPS/infra/terraform/**`, `.github/workflows/tf-plan.yml`, docs.
Must not: run `terraform apply`, change any image tag or digest, dispatch any workflow,
execute any Cloud Run job, change IAM bindings, or touch modeling, backend or frontend code.

## Kill-switch
Stop, write to `00-PROJECT-LEAD/QUESTIONS.md`, and tell Matt if: a `plan` shows a destructive
change to anything other than an image attribute; `ignore_changes` cannot express the image
path for one of the resource types; reconciling drift would require an `apply` to discover
the answer; or the plan cannot run without credentials Matt has not provided.

## Acceptance (each line true or false)
- [ ] All seven resources have `ignore_changes` covering their image attribute.
- [ ] `terraform plan`, with no `-target`, shows zero image changes. Output quoted.
- [ ] The plan shows no unexplained destroys or replacements. Anything remaining is listed
      with a one-line reason.
- [ ] The `-target` comment block in `iam.tf` is removed, or kept with a stated reason.
- [ ] `tf-plan.yml` still runs and still gates on a PR touching the terraform path.
- [ ] No `apply`, no dispatch, no job execution, no IAM change.

## Returns-with
`00-PROJECT-LEAD/HANDOFF-2026-09-<dd>-terraform-image-ownership.md`: goal achieved yes/no
(first line), commit SHA(s), the quoted `plan` summary, which drift was reconciled and which
was left, and whether `terraform apply` is now safe to run unattended.
