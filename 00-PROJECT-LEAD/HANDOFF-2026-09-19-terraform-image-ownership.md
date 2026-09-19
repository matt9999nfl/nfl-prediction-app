Goal achieved: yes, with one item handed to Matt rather than resolved.

Commits: `69436f5` (implementation), `dea3908` (SHA record).

## What changed

All seven Cloud Run job/service resources now carry a `lifecycle { ignore_changes }`
block on their image attribute, so Terraform stops trying to move images back to
`:latest` on every `apply`:

- `05-DEVOPS/infra/terraform/jobs.tf` — `dataset_processor`, `experiment_runner`,
  `pipeline_full`, `pipeline_gameday`, `injury_capture`, `production_refresh`
  (`google_cloud_run_v2_job`): `ignore_changes = [template[0].template[0].containers[0].image]`
- `05-DEVOPS/infra/terraform/cloud_run.tf` — the `api` service (`google_cloud_run_service`,
  a different resource type that nests differently):
  `ignore_changes = [template[0].spec[0].containers[0].image]`

Both addresses were found and confirmed by an actual `terraform plan` against live
state (using Matt's own already-authenticated `gcloud`/ADC credentials on this machine,
read-only), not assumed from documentation — the prompt asked for exactly this, since
the two resource types nest the container image differently and getting it wrong would
have looked fine in `validate` but done nothing in a real plan.

## The check that proves it

Baseline (`terraform plan`, before this change): 5 resources showed an image-attribute
diff (`pipeline_full`, `pipeline_gameday`, `experiment_runner`, `production_refresh`,
the `api` service), each reverting a live digest pin back to a `:latest` tag.

After: `terraform plan` with no `-target`, run against the same live state —

```
Plan: 7 to add, 5 to change, 0 to destroy.
```

The "7 to add" are the not-yet-deployed injury-capture resources from B1-3c (expected,
unrelated to this stage). Grepping the full plan output for every `image` line with a
change marker (`~ image`, `+ image` inside an *existing* resource, or `- image`) returns
nothing on any of the seven target resources — the only `+ image` in the whole plan is
inside the brand-new `injury_capture` job being created for the first time, which isn't
a change to a pinned image, it's the resource not existing yet.

## Drift reconciled vs. left

- **Image (digest pins):** reconciled — the `lifecycle` blocks above.
- **Refresh job timeout/memory** (the other drift STATE.md named for DP-R-13): checked
  against live (`gcloud run jobs describe nfl-production-refresh`) — already matches
  Terraform's declared `cpu=1, memory=512Mi, timeout=120s` exactly. Nothing to reconcile;
  this part of the drift note was already stale.
- **`client`/`client_version` fields** on all four `google_cloud_run_v2_job` resources,
  and matching `run.googleapis.com/client-name`/`client-version` annotations on the `api`
  service: still show as in-place updates (nulling out), because they're Google-populated
  provenance metadata stamped by whichever tool (`gcloud`) last touched each resource, and
  will be re-stamped by the next real deploy regardless. Not a destroy or replacement,
  cosmetic, left alone — reconciling it would mean either declaring it (pointless, it's
  set outside Terraform every time) or ignoring it too (not asked for, and out of scope
  for an "image ownership" stage specifically).
- **`google_cloud_run_service.api`'s `traffic` block** (0% to a revision tagged
  "candidate", undeclared in `cloud_run.tf`): **not reconciled.** This is a genuine
  destructive removal of live routing config, not cosmetic, and not an image attribute —
  the prompt's kill-switch is explicit that this is Matt's call, not mine. Two live
  options either declare it (but its `revision_name` is regenerated every deploy, so it
  would just drift again) or extend the same `ignore_changes` treatment to `traffic` too,
  on the theory that CI/manual `gcloud` owns traffic splits the same way it owns images.
  Written up in `QUESTIONS.md` (2026-09-19 entry) with both options and the context:
  `05-DEVOPS/instructions.md` rule 3 already documents `api-deploy.yml` shifting traffic
  to `LATEST` rather than the smoke-tested revision as a known bug, so this stale
  "candidate" tag may just be an artifact of that — unverified, not assumed.

## `iam.tf`'s `-target` comment

Updated, not deleted. Its original reason (a blanket apply reverting digest pins) is
gone. It stays for a different, narrower reason: a blanket apply right now would still
*create* the seven not-yet-deployed injury-capture resources from B1-3c, which isn't
wanted yet, and would also remove the `traffic` block above without Matt having decided
what to do about it. The comment now says this plainly instead of the old, now-false
DP-R-13 justification.

## Is `terraform apply` safe to run unattended now?

**For images: yes.** That was the actual ask, and it's verified. **Not fully unattended
yet**, for two reasons that have nothing to do with images: it would deploy the
injury-capture stage before Matt is ready to, and it would silently drop the live
"candidate" traffic tag. Once Matt answers the `QUESTIONS.md` item and either applies the
injury-capture resources on purpose or asks for them to wait, a plain `terraform apply`
with no `-target` is safe.

## Not touched

`tf-plan.yml` — still runs `plan` only, still gated on a PR touching
`05-DEVOPS/infra/terraform/**`; nothing about it needed to change for this stage. (Noted
but not fixed, out of scope: its "Comment PR with Plan" step reads a `tfplan.json` file
that no earlier step actually produces — `terraform plan -out=tfplan` writes a binary
plan file, not JSON, and there's no `terraform show -json tfplan > tfplan.json` step. PR
comments on terraform PRs are likely silently failing on that step. Flagging since I
noticed it while reading the workflow, not because this prompt asked for it.)

No `terraform apply`, no dispatch, no Cloud Run job execution, no IAM change made by this
session. Modeling, backend and frontend code untouched.
