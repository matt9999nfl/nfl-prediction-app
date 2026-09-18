# PROMPT-DEPLOY-DATA-PIPELINE — rebuild the data-pipeline image so line capture actually runs, and pin both pipeline jobs to the digest

Start in: C:\Users\OEM\OneDrive\Desktop\nfl-prediction-app
Written: 2026-09-18 by PROJECT-LEAD. Small deploy stage. Next: PROMPT-BATCH-RUNNER.

## Why
The deployed `nfl-data-pipeline:latest` image was built 2026-09-08, before `snapshot_lines.py` existed, so no scheduled run has ever captured a betting line (`HANDOFF-2026-09-18-spread-sign-and-snapshots.md`). A manual catch-up capture was run on 2026-09-18 (3,300 rows), but the next scheduled run will still be running 10-day-old code.

What the rebuild picks up, in `01-DATA-PIPELINE` since the deployed build: `snapshot_lines.py` and its tests, `line_snapshot_freshness.py` and its tests, the `run_pipeline.py` call to `snapshot()`, `validate_and_report.py`'s snapshot check, a comment fix in `audit_closing_lines.py`, `verify_label_convention.py` (a standalone script the pipeline doesn't call), and docs. No change to ingest, curated builds or step order.

## Timing — check before acting
Scheduled pipeline jobs (UTC): Mon 05:00 gameday-sunday · Tue 07:00 gameday-monday · Tue 11:00 full rebuild · Fri 05:00 gameday-thursday.
Build and repoint in a gap, and confirm no execution is running first. **Don't build or repoint within 30 minutes of a scheduled start, and don't repoint between Tue 11:00 and 15:00 UTC.**

## Steps
1. Confirm the currently deployed digest for both `nfl-pipeline-full` and `nfl-pipeline-gameday`, and the last execution of each (status and finish time). Report them.
2. Confirm nothing is running.
3. `gcloud builds submit --config cloudbuild.yaml .` from `01-DATA-PIPELINE`, built from a clean export of the pushed commit, not the working tree. Report the new digest and the commit.
4. Point both jobs at that digest explicitly. No `:latest` in the job definition. Show `describe` before and after for each.
5. Execute `nfl-pipeline-gameday` once by hand. Report: exit status, the step summary line for `line_snapshots` with its row count, the validation output including the new freshness check, and the `curated.games` / `curated.plays` row counts before and after.
6. If step 5's run fails or the row counts move in a way you can't explain, put both jobs back on the previous digest, then stop and tell Matt.

## Scope
Allowed: building the data-pipeline image, repointing those two jobs, one manual `nfl-pipeline-gameday` execution.
Must not: change any code, change schedules or IAM, run `nfl-pipeline-full`, run the production refresh, or touch modeling jobs.

## Kill-switch
Stop, write to `00-PROJECT-LEAD/QUESTIONS.md`, and tell Matt if: the build pulls in a code change outside the list above; the manual run writes fewer rows to `curated.*` than were there before; the snapshot step fails again; or a repoint would land in a scheduled window.

## Acceptance (each line true or false)
- [ ] Both jobs show the same new digest, and neither references `:latest`.
- [ ] The manual `nfl-pipeline-gameday` run exited 0, and its summary shows `line_snapshots` with a row count.
- [ ] `raw_lines.line_snapshots` row count is given before and after the run.
- [ ] The validation output includes the line-snapshot freshness check, and it passes.
- [ ] `curated.games` and `curated.plays` row counts are unchanged or explained.
- [ ] The previous digest is recorded in the handoff, so the change can be undone.

## Returns-with
`00-PROJECT-LEAD/HANDOFF-2026-09-<dd>-deploy-data-pipeline.md`: goal achieved yes/no (first line), old and new digests for both jobs, the commit built, the manual run's output summary, row counts before and after, anything left open.
