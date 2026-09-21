Goal achieved: yes.

Commit: `79d9872` — fix: distinguish not-deployed/awaiting-first-capture/stale
in roster freshness check (B1-2g).

## What was wrong

§3d in `validate_and_report.py` (added by B1-3c, `c7b5ead`) queried
`raw_roster_snapshots.{injury_report_snapshots,depth_chart_snapshots}` and
treated every query failure the same way: "no rows" or "query failed" both
counted as a FAILED check. That dataset doesn't exist yet — `nfl-injury-
capture` (B1-3c) has never been deployed — so the check failed identically to
a genuinely stale capture, and that's what took down B1-2's 2026-09-21
verification run (`HANDOFF-2026-09-21-diagnose-pipeline-run-failure.md`).

## The three states, and how each is now handled

`roster_snapshot_freshness.py`'s `evaluate_roster_snapshot_freshness()` now
takes `table_exists` and `table_created` (from BigQuery's own
`get_table().created`) alongside `n_rows`/`latest`, and returns `(ok, state,
detail)` instead of `(ok, age_txt)`:

1. **not deployed** — `table_exists` is False (the query raised "not
   found"). `ok = True`. Not a failure; the capture has simply never been
   rolled out.
2. **awaiting first capture** — table exists, `n_rows == 0`, and the table's
   own creation time is within the freshness budget. `ok = True`. Not a
   failure yet.
3. **stale** — table exists and either (a) it has rows whose latest capture
   is older than the budget, or (b) it has zero rows and has existed longer
   than the budget. `ok = False`, `all_pass` goes False, `sys.exit(1)` —
   **unchanged from today**. This is the failure B1-3c exists to catch.

`fetch_roster_snapshot_status()` in `validate_and_report.py` distinguishes
"not found" from every other query failure by exception class name
(`type(exc).__name__ == "NotFound"`), not `isinstance(..., google.api_core.
exceptions.NotFound)` — see the code comment for why: two other test modules
in this folder (`test_snapshot_lines.py`, `test_capture_injury_snapshots.py`)
replace `sys.modules["google"]` wholesale to stub BigQuery without
credentials, which breaks a direct import of that class whenever those
modules are collected first in the same pytest session. Name-matching avoids
that without touching those out-of-scope files. A real access problem other
than "not found" (bad IAM grant on a table that does exist) still reports as
"query failed" with the error attached, exactly as before.

The §3d report block now prints the state in words for both tables, e.g.:

```
- `injury_report_snapshots`: **not deployed** -- dataset/table does not exist yet  ✅
- `depth_chart_snapshots`: **awaiting first capture** -- 0 row(s) total, table created 0.1 day(s) ago, no rows yet  ✅
```

The `**ERROR:**` explanatory paragraph now only appears for a genuine `stale`
result or a real query error — not for the two passing states.

## The empty window

No separate constant. The empty-table case reuses
`ROSTER_SNAPSHOT_MAX_AGE_DAYS` (3 days, unchanged) by measuring age from the
table's `created` time instead of a capture's `captured_at` when there's no
row yet. Reasoning (in the code comment): there's no principled reason a
freshly-created table should get a more generous grace period than an
established one that missed a run, and in practice the gap between
`terraform apply` creating the table and the first scheduled capture (daily,
08:00 UTC) is well under a day — so 3 days is generous for "awaiting first
capture" and still tight enough to catch a deployed capture that has never
once succeeded.

## `line_snapshot_freshness.py`

Checked, does **not** have the same defect — no change made. Its table,
`raw_lines.line_snapshots`, is written by `snapshot_lines.py`, which runs
inside the main pipeline on every scheduled execution and has been live
since 2026-09-09 (confirmed in this run's own diagnosis: `line_snapshots_
freshness` passed). There is no "not yet deployed" state for it: the
pipeline itself is the deployment, so the table not existing means something
is actually broken (dropped dataset, wrong project, missing IAM), which is
exactly what `fetch_line_snapshot_status()`'s existing comment already says.
Softening that check would hide a real regression, so it was left alone.

## Tests

Data-pipeline test count: **34 before → 50 after** (+16: 9 in the new
`test_roster_snapshot_freshness.py` covering the pure function's four states
directly (absent passes, empty-and-recent passes, stale-with-rows fails,
empty-beyond-window fails, plus boundary/no-timestamp-available cases); 7 new
in `test_validate_and_report.py` — six isolate `fetch_roster_snapshot_status`
against fake BigQuery clients (not-found, empty-recent, empty-stale, rows-
stale, rows-fresh, and a real `get_table()` error that isn't "not found"),
and one runs `main()` end-to-end reproducing the actual B1-2 failure —
`raw_roster_snapshots` absent, line snapshots fresh — and asserts `all_pass`
stays True and the process never exits non-zero).

All 50 pass, run from both the repo root and `01-DATA-PIPELINE/`:
```
python -m pytest 01-DATA-PIPELINE -q
```

## B1-2 retry

Unblocked either way. `fetch_roster_snapshot_status` now reports "not
deployed" (passing) when `raw_roster_snapshots` doesn't exist, and "awaiting
first capture" (also passing) once B1-3c's Terraform is applied but before
the first daily capture lands rows — so the retry succeeds whether B1-3c is
deployed first or not, as the prompt required. Once a capture actually runs
and then stops for more than 3 days, the check still fails the report and
the run's exit code, same as today.

## Scope confirmation

Nothing deployed, built, repointed, executed, or `terraform apply`'d.
Touched only `roster_snapshot_freshness.py`, `validate_and_report.py` (§3d,
plus the shared `_is_dataset_or_table_not_found` helper and the new
`fetch_roster_snapshot_status`/`FullPipelineFakeClient` test scaffolding),
and their tests.
