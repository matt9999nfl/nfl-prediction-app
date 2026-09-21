# PROMPT-FIX-ROSTER-FRESHNESS-STATES — a check for a component that isn't deployed yet must not fail the pipeline

Start in: C:\Users\OEM\OneDrive\Desktop\nfl-prediction-app
Written: 2026-09-21 by PROJECT-LEAD. Stage B1-2g of `PLAN-BUCKET1-DATA-COVERAGE.md`.
Unblocks the B1-2 retry.

## Why

B1-2's verification run failed on 2026-09-21 (diagnosis: `HANDOFF-2026-09-21-diagnose-pipeline-run-failure.md`).
Cause: §3d's two roster-snapshot-freshness checks, added by B1-3c in `c7b5ead`, query
`raw_roster_snapshots` — a dataset that does not exist, because `nfl-injury-capture` has
never been deployed. The checks failed, `all_pass` went False, `validate_and_report.py`
exited 1, the pipeline execution failed, and the kill-switch reverted both jobs.

Nothing about B1-2 was wrong. It was verified against an image carrying a check for a
component that isn't there yet.

**The obvious fix — deploy B1-3c, then retry — does not work.** `evaluate_roster_snapshot_freshness`
returns `False` for `n_rows == 0` (`roster_snapshot_freshness.py:27`). After a targeted
`terraform apply` the dataset exists but both tables are empty until the first daily capture
runs at 08:00 UTC. A retry before that fails again, identically.

## The real defect

The check cannot distinguish three states that mean different things:

1. **Dataset or table absent** — the capture was never deployed. Not a failure; nothing is broken.
2. **Present but empty** — deployed, waiting for its first run. Not a failure *yet*.
3. **Present with rows, newest older than `ROSTER_SNAPSHOT_MAX_AGE_DAYS`** — the capture ran and
   has stopped. **This is the failure worth having**, and the one B1-3c was built to surface.

Today all three fail identically, which is why a component that has never existed can stop
the data pipeline.

Note what is *not* being asked for: do not make §3d non-failing. State 3 must still fail the
report and the run — that visibility is the whole point of the three-levels rule from B1-2a,
and softening it recreates the nine-day silent failure. Only states 1 and 2 change.

## The hole to close while you are in there

If states 1 and 2 simply pass, a capture job that is deployed and never successfully writes a
single row would pass forever. Close it: once the dataset exists, empty is tolerable only for
a bounded window. BigQuery exposes dataset and table creation time — use it. Empty plus
"created more than N days ago" is state 3, and fails. Pick N, justify it in a comment.

## Task

Rework `evaluate_roster_snapshot_freshness` and its caller so the three states are distinct,
each with its own report line and its own pass/fail. The report must say which state it is in
plain words — "not deployed", "awaiting first capture", "stale" — not just a tick or a cross.

Apply the same treatment to `line_snapshot_freshness.py` only if it has the same defect.
Check; do not assume either way.

## Read first
- `00-PROJECT-LEAD/HANDOFF-2026-09-21-diagnose-pipeline-run-failure.md` — the full diagnosis
- `00-PROJECT-LEAD/STATE.md` (Decisions), `context/talking-to-matt.md`
- `01-DATA-PIPELINE/scripts/roster_snapshot_freshness.py` and `line_snapshot_freshness.py`
- `01-DATA-PIPELINE/scripts/validate_and_report.py` §3c and §3d
- `00-PROJECT-LEAD/PROMPT-CAPTURE-INJURY-SNAPSHOTS.md` — why the capture is a separate job

## Scope
Allowed: `roster_snapshot_freshness.py`, `validate_and_report.py` §3d (and §3c only if it has
the same defect), and their tests.
Must not: deploy, build or push an image, repoint or execute any Cloud Run job, dispatch the
workflow, run `terraform apply`, change IAM, or touch modeling, backend or frontend.

## Kill-switch
Stop, write to `00-PROJECT-LEAD/QUESTIONS.md`, and tell Matt if: distinguishing the states
needs a schema or dataset change; state 3 would stop failing as a side effect; or the bounded
empty-window rule cannot be implemented from information BigQuery exposes.

## Acceptance (each line true or false)
- [ ] Tests prove all three states independently: absent passes, empty-and-recent passes,
      stale fails, and empty-beyond-the-window fails.
- [ ] A stale table still sets `all_pass` False and still exits non-zero — unchanged from today.
- [ ] The report names the state in words for each of the three.
- [ ] `line_snapshot_freshness.py` was checked for the same defect; what was found is stated.
- [ ] Data-pipeline test count reported before and after.
- [ ] Nothing deployed, built, repointed, executed or applied.

## Returns-with
`00-PROJECT-LEAD/HANDOFF-2026-09-<dd>-fix-roster-freshness-states.md`: goal achieved yes/no
(first line), commit SHA(s), the three states and how each is now handled, the chosen empty
window and why, test counts before and after, and confirmation that the B1-2 retry is
unblocked regardless of whether B1-3c is deployed first.
