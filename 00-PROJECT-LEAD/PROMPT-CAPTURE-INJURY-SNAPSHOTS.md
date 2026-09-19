# PROMPT-CAPTURE-INJURY-SNAPSHOTS — start the injury and depth-chart clock, on its own schedule

Start in: C:\Users\OEM\OneDrive\Desktop\nfl-prediction-app
Written: 2026-09-19 by PROJECT-LEAD. Stage B1-3c of `PLAN-BUCKET1-DATA-COVERAGE.md`.

## Why

`raw_ol_sources.nflverse_ol_injuries` holds exactly one row per player-week — the week's
**final** report, timestamped, Friday for 79% of rows. There is one `practice_status` per
player-week, so the Wednesday→Thursday→Friday practice progression does not exist in the
archive and never will. DNP-DNP-Limited and Limited-Limited-Full arrive at the same Friday
designation and mean different things, and that difference is only obtainable by capturing
it as it happens.

Same for depth charts: `dt` is null for every pre-2025 row, so there is no observation time
at all in the archive.

This stage starts that clock. It builds **no features and touches no model**. Its entire
value is that in November there is data that does not exist today.

## Design point 1 — this must NOT live inside the pipeline

`snapshot_lines.py` runs inside `run_pipeline.py`. Do not follow that pattern here.

The pipeline drops and rebuilds its landing tables as its first act, crash-looped for a week
on one missing IAM grant, and ran 10 days on a stale image without anyone noticing
(`QUESTIONS.md`, 2026-09-18). A capture job whose only job is to never miss a day must not
share fate with it. Build a separate, small Cloud Run job with its own schedule, reading
nflverse and writing append-only rows. It should be able to run while the pipeline is broken.

## Design point 2 — the existing schedule would capture almost nothing new

Scheduled pipeline runs (UTC): Mon 05:00, Tue 07:00, Tue 11:00, Fri 05:00. NFL injury
reports publish Wednesday, Thursday and Friday US time. Capturing on the existing cadence
would land roughly one mid-week snapshot plus the final state — which is what the archive
already has.

**Daily capture, at a fixed UTC time, is the minimum that delivers the progression.** Work
out the right time from when nflverse actually refreshes (its injuries feed updates daily at
07:00 UTC — capture after that), state your reasoning, and say plainly what the cadence does
and does not capture.

## Task

An append-only snapshot log of nflverse injuries and depth charts, in the shape
`raw_lines.line_snapshots` already established: one row per observed change, nothing updated,
nothing deleted, every row carrying the observation timestamp.

Handle the traps already found in this data (see `PLAN-BUCKET1-DATA-COVERAGE.md`, the
point-in-time verification section): `report_status` uses the **literal string** `"None"` for
half the rows rather than NULL, so an `IS NULL` check silently misses them; `date_modified` is
null for 9.9% of archive rows; depth charts are not unique per player-week (up to 8 rows,
multiple `depth_position` entries per player).

Failure handling follows the B1-2a lesson exactly — three levels, only one correct. Crashing
the job is too much. Logging an error is demonstrably too little (nine days unnoticed). A
failed capture must show up as a **failed check in the validation report**.

## Read first
- `00-PROJECT-LEAD/PROJECT-CHARTER.md`, `STATE.md` (Decisions), `context/talking-to-matt.md`
- `00-PROJECT-LEAD/PLAN-BUCKET1-DATA-COVERAGE.md` — B1-3c, and the point-in-time verification
- `01-DATA-PIPELINE/scripts/snapshot_lines.py` — the append-only shape to copy, not the host
- `01-DATA-PIPELINE/scripts/validate_and_report.py` §3c — how a capture failure becomes visible
- `01-DATA-PIPELINE/instructions.md`

## Scope
Allowed: a new capture script and its tests, a new raw dataset, a validation check, and the
Terraform/job definition for a new scheduled Cloud Run job.
Must not: change the existing pipeline's steps, build features, change any model, touch
`curated.*`, or deploy anything.

Write the code and the job definition. **Deploying it is a separate step for Matt**, the same
way B1-2 was.

## Kill-switch
Stop, write to `00-PROJECT-LEAD/QUESTIONS.md`, and tell Matt if: the capture would have to run
inside `run_pipeline.py`; a new dataset needs an IAM grant (write the command, don't run it —
this is exactly what cost 2026-09-18); the nflverse feed turns out not to refresh daily; or
capturing daily would exceed a free-tier or cost threshold worth naming.

## Acceptance (each line true or false)
- [ ] A capture script exists and runs standalone, independent of `run_pipeline.py`.
- [ ] Rows are append-only, timestamped, and a re-run with unchanged source data adds no rows.
- [ ] Tests cover: the literal `"None"` string, a null `date_modified`, and a player with
      multiple depth-chart rows in one week.
- [ ] A capture failure produces a failed check in the validation report, not a crash and not
      only a log line.
- [ ] The chosen cadence is stated, with what it captures and what it misses.
- [ ] Any required IAM grant is written out for Matt, not applied.
- [ ] Nothing deployed, no existing pipeline step changed, no model or feature touched.

## Returns-with
`00-PROJECT-LEAD/HANDOFF-2026-09-<dd>-capture-injury-snapshots.md`: goal achieved yes/no
(first line), commit SHA(s), the cadence and its justification, test counts before and after,
any grant Matt must run, and what remains before the first capture actually runs.
