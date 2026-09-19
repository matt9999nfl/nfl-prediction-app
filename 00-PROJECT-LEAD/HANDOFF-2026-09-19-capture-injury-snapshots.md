Goal achieved: yes.

Commits: `c7b5ead` (implementation), `278fa96` (SHA record), `a9305cd` (B1-2c handoff,
written earlier but not yet committed — folded in here for hygiene).

## What this stage built

A standalone daily capture of nflverse injury reports and depth charts, starting the
observation clock `PLAN-BUCKET1-DATA-COVERAGE.md` identified as missing: the existing
archive (`raw_ol_sources.nflverse_ol_injuries`/`.nflverse_ol_depth_charts`) holds exactly
one final-state row per player-week, with no way to ever recover the Wednesday-Thursday-
Friday practice-status progression after the fact.

- `01-DATA-PIPELINE/scripts/capture_injury_snapshots.py` — fetches `nfl_data_py`'s
  `import_injuries`/`import_depth_charts`, diffs against the latest stored row per key,
  and appends only new-or-changed rows into a new `raw_roster_snapshots` dataset
  (`injury_report_snapshots`, `depth_chart_snapshots`). Standalone entrypoint, not called
  from `run_pipeline.py` — design point 1 in the prompt: a capture whose only job is to
  never miss a day must not share fate with a pipeline that drops and rebuilds its own
  landing tables and once crash-looped for a week on one missing IAM grant.
- `01-DATA-PIPELINE/scripts/roster_snapshot_freshness.py` — pure freshness-evaluation
  function, same shape as the existing `line_snapshot_freshness.py`, no credentials needed
  to test.
- `01-DATA-PIPELINE/scripts/validate_and_report.py` — new §3d: queries both new tables'
  freshness and fails the check (not the whole report) if either has gone stale. This is
  how a capture failure becomes visible, per the B1-2a lesson: not a crash, not only a log
  line, a failed check in the report a human actually reads.
- `01-DATA-PIPELINE/scripts/test_capture_injury_snapshots.py` — 11 new tests.
- `05-DEVOPS/infra/terraform/{iam,jobs,scheduler}.tf` — new service account
  (`nfl-injury-capture-sa`), its IAM grants, the `nfl-injury-capture` Cloud Run job (reuses
  the existing `nfl-data-pipeline` image — no new Dockerfile needed), and a daily 08:00 UTC
  Cloud Scheduler entry. **Written, not applied.**

## The three traps, confirmed live (2026-09-19), not just against the archive

Fetched a real season live via `nfl_data_py` (version matches `requirements.txt`'s pin,
0.3.3) rather than relying only on the staged parquet:

1. `report_status` is the literal string `"None"` for roughly half of all rows (3,386 of
   ~6,200 in a 2024 season fetch), not NULL. The diff logic compares it as an ordinary
   value — `fillna()` only touches real nulls, so `"None"` never gets coerced into "no
   change" or dropped by any null check.
2. `date_modified` can still be null. It's informational-only here; it isn't in either
   table's comparison columns, so a null there can never affect what gets captured. The
   observation clock this stage exists to provide is `captured_at`, which is never null.
3. Depth charts are still not unique per player-week live (one player had up to 6 rows in
   a single 2024 week in the live fetch). `depth_position` is part of the identity key,
   not a compared column, so simultaneous entries for one player are tracked
   independently rather than colliding.

One correction found along the way: the archived depth-chart parquet's `team`/`dt`/
`espn_id` columns do not come from `nfl_data_py.import_depth_charts()` at all — a live
call returns no `team` or `dt` column, only `club_code`. The capture script uses
`club_code`, renamed to `team` for consistency with every other table in this project.

## Cadence

Daily, 08:00 UTC — one hour after nflverse's own daily injuries-feed refresh. Captures:
day-level granularity on report/practice status changes, which is what recovers the
Wed/Thu/Fri progression the archive cannot have. Misses: anything intra-day (a same-day
correction after 08:00 UTC is invisible until the next day's run). A day with no new
report (most weekends) costs one wasted invocation that inserts zero rows — expected, not
a failure.

## Tests

Before this stage: 12 tests in `01-DATA-PIPELINE/scripts/` (`test_snapshot_lines.py`).
After: 23 (`+11`, `test_capture_injury_snapshots.py`). All 11 new tests pass
(`python -m pytest 01-DATA-PIPELINE/scripts/test_capture_injury_snapshots.py`, run from
the repo root — 11 passed).

Note found, not fixed (out of scope for this prompt): `test_snapshot_lines.py` itself
fails to import when run the same way (`ModuleNotFoundError: No module named
'snapshot_lines'`) — pre-existing, caused by `scripts/__init__.py` making pytest resolve
imports as `scripts.<module>` rather than putting `scripts/` itself on `sys.path`. My own
test file adds its own directory to `sys.path` explicitly so it isn't affected. Worth a
follow-up if anyone wants `test_snapshot_lines.py` runnable from the repo root again.

## Grant Matt must run

Terraform in `05-DEVOPS/infra/terraform/{iam,jobs,scheduler}.tf` adds:
- `google_service_account.injury_capture` (`nfl-injury-capture-sa`)
- `google_bigquery_dataset_iam_member.injury_capture_editor_roster_snapshots` (write)
- `google_project_iam_member.injury_capture_job_user`
- `google_bigquery_dataset_iam_member.pipeline_reader_roster_snapshots` (read, on the
  existing `nfl-pipeline-sa`, so §3d's freshness check can query the new dataset)
- `google_cloud_run_v2_job.injury_capture` + `google_cloud_run_v2_job_iam_member.injury_capture_invoke_self`
- `google_cloud_scheduler_job.injury_capture_daily`

**Apply only these, by name, with `-target` flags — not a blanket `terraform apply`.**
Terraform has already drifted from live on the existing jobs (STATE.md, DP-R-13: still
declares `:latest` where digests are pinned outside Terraform); a blanket apply now would
revert those pins as a side effect of adding this service account. `iam.tf` has the exact
`-target` list in a comment above the new resources.

## What remains before the first capture actually runs

1. Matt applies the targeted Terraform resources above.
2. First scheduled run is the next 08:00 UTC after that.
3. Confirm via `validate_and_report.py`'s next run (or a manual
   `gcloud run jobs execute nfl-injury-capture --region us-central1 --wait`) that both new
   tables get their first rows and §3d passes.

Nothing dispatched, deployed, or applied by this session. No existing pipeline step
changed. No `curated.*` table touched. No model or feature touched.
