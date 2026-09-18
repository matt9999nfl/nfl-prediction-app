# PROMPT-FIX-PIPELINE-IAM-AND-RETRY — stop the pipeline crash-looping on a missing IAM grant

Start in: C:\Users\OEM\OneDrive\Desktop\nfl-prediction-app
Written: 2026-09-19 by PROJECT-LEAD. Stage B1-2a of `PLAN-BUCKET1-DATA-COVERAGE.md`.
Next stage: the B1-2 retry (`PROMPT-DEPLOY-DATA-PIPELINE.md`), which must not run until this lands.

## Why

The 2026-09-18 B1-2 deploy failed. Diagnosis in `QUESTIONS.md` (2026-09-18 entry): it was
not a slow image and not a race between two jobs. `nfl-pipeline-sa` has no BigQuery grant
on the `raw_lines` dataset — that dataset was created 2026-09-09 with only Matt's personal
account as owner, and the service-account grant was never added. `snapshot_lines.py`
swallows the resulting 403 by design. `validate_and_report.py` does not: it raises, kills
the container, and Cloud Run retries the whole pipeline from step 1. Both executions that
day restarted four times at ~12 minutes a cycle — the historical baseline — which is the
48 minutes, and two of those retry cycles dropping and rebuilding `raw_nflfastr.pbp`
around 05:00 is what produced the `NotFound` collision. The collision was a symptom.

This is deterministic. It will happen on every run of the new image until fixed.

## The defect is narrower than "the freshness check crashes"

`validate_and_report.py` section 3c is already designed correctly. `evaluate_line_snapshot_freshness()`
is a pure function, `check()` records a pass/fail, and `all_pass &=` makes a stale or empty
table fail the run visibly. That design is right and must not be softened.

The bug is one line earlier: `run_query(client, "SELECT ... FROM raw_lines.line_snapshots")`
raises the 403 before `evaluate_line_snapshot_freshness()` is ever reached. An unreadable
table is a case the code never anticipated.

Three levels exist here and only one is correct:
- crash the container — what happens now, too much
- log an error and move on — what `snapshot()` does, demonstrably too little (nine days unnoticed)
- **fail the validation report** — visible in `VALIDATION_REPORT.md`, counted in `all_pass`

Fix (b) means catching the query failure and routing it to the third level, with the error
text in the report. It does not mean making 3c non-fatal.

## The three fixes interlock — do not stop after one

- **(a) IAM grant — MATT'S CALL, not this session's.** Grant `nfl-pipeline-sa` the same
  dataset-level BigQuery access on `raw_lines` that it already has on `raw_nflfastr` and
  `curated`. Do not run this yourself. Write the exact command for Matt, say what it
  changes, and wait. Without it, (b) turns a crash into a permanently failing check.
- **(b) Catch the unreadable-table case** in `validate_and_report.py` 3c, as above.
- **(c) Cloud Run retry policy on `nfl-pipeline-full` and `nfl-pipeline-gameday`.** Note
  that (b) alone does not solve the loop: a failed check still exits non-zero, and step 7
  failing still triggers a retry that re-runs the destructive steps 3 and 6 from scratch.
  A pipeline whose first act is to drop its landing tables must not silently auto-retry.
  Report the current retry setting, then propose the change and its trade-off (a missed
  ingest Matt is told about beats a table rebuilt four times that he isn't). Matt decides
  the number.

## Read first
- `00-PROJECT-LEAD/PROJECT-CHARTER.md`
- `00-PROJECT-LEAD/STATE.md` (Decisions — standing rulings, don't re-ask)
- `00-PROJECT-LEAD/QUESTIONS.md`, the 2026-09-18 deploy-data-pipeline entry — the full diagnosis
- `00-PROJECT-LEAD/context/talking-to-matt.md`
- `01-DATA-PIPELINE/scripts/validate_and_report.py` section 3c, and `line_snapshot_freshness.py`
- `01-DATA-PIPELINE/scripts/snapshot_lines.py` — how it handles the same 403, for contrast
- `01-DATA-PIPELINE/instructions.md`

## Scope
Allowed to change: `validate_and_report.py` and its tests; `test_line_snapshot_freshness.py`.
Must not: run `gcloud builds submit`, repoint or execute any Cloud Run job, change IAM,
change schedules, retry B1-2, or touch modeling, backend or frontend.

This prompt lands code and a recommendation. It deploys nothing.

## Kill-switch
Stop, write to `00-PROJECT-LEAD/QUESTIONS.md`, and tell Matt if: the fix would make 3c
non-fatal or otherwise weaken `all_pass`; the retry setting cannot be read without a change;
`nfl-pipeline-sa` turns out to lack grants on datasets beyond `raw_lines`; or any step would
execute a pipeline job.

## Acceptance (each line true or false)
- [ ] A test proves that an unreadable `raw_lines.line_snapshots` produces a **failed check**
      in the report, not an exception, and that `all_pass` is False.
- [ ] A test proves a readable-but-stale table still fails, and a fresh one still passes —
      the existing behaviour is unchanged.
- [ ] `VALIDATION_REPORT.md` output for the unreadable case names the dataset and the error.
- [ ] Data-pipeline test count reported before and after.
- [ ] The exact `gcloud`/`bq` command for (a) is written out for Matt, with what it grants.
- [ ] The current Cloud Run retry setting for both jobs is reported, with a recommendation
      and its trade-off. No change applied.
- [ ] No image built, no job repointed, no job executed, no IAM changed.

## Returns-with
`00-PROJECT-LEAD/HANDOFF-2026-09-<dd>-fix-pipeline-iam-and-retry.md`: goal achieved yes/no
(first line), commit SHA(s), test counts before and after, the command written for Matt,
the retry recommendation, and what remains before B1-2 can retry.
