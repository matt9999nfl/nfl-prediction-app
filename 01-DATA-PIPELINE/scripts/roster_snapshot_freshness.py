"""
Pure freshness check for raw_roster_snapshots.{injury_report_snapshots,
depth_chart_snapshots} (PROMPT-CAPTURE-INJURY-SNAPSHOTS.md).

Split out of validate_and_report.py, same reason as line_snapshot_freshness.py:
this one check needs to be testable without a BigQuery client, credentials, or
network. Mirrors that module's shape deliberately -- it is the established,
correct answer to "how does a capture failure become visible" (B1-2a lesson,
QUESTIONS.md 2026-09-18): not a log line, not a crash, a failed check here.

PROMPT-FIX-ROSTER-FRESHNESS-STATES.md (2026-09-21): the capture this checks
(`nfl-injury-capture`) is a separate, independently-deployed Cloud Run job
(B1-3c), so there are three states this check must tell apart, not one:

  1. not deployed   -- the dataset/table does not exist at all. Not a
                        failure; the capture has simply never been rolled
                        out yet.
  2. awaiting first
     capture        -- the table exists (deployed) but has no rows yet,
                        and it hasn't been long enough to expect one. Not
                        a failure *yet*.
  3. stale          -- the table exists, and either it has rows whose
                        latest capture is too old, or it has never had a
                        single row despite existing long enough to expect
                        one. This is the failure B1-3c was built to catch,
                        and it must still fail the report and exit non-zero
                        -- that's the whole point (see B1-2a, the nine-day
                        silent failure this design exists to prevent).

This found the B1-2 verification failure on 2026-09-21: the check treated
"dataset doesn't exist because the capture was never deployed" identically
to "capture ran, then stopped", so a component that had never been deployed
was able to fail an unrelated pipeline's validation run.
"""
from __future__ import annotations

from datetime import datetime

# This capture runs daily (not weekly, like line_snapshots), so its staleness
# budget is tighter. 3 days tolerates one missed weekend run without a false
# failure but still catches a stuck capture well inside a week -- long before
# the next injury report cycle would need it.
ROSTER_SNAPSHOT_MAX_AGE_DAYS = 3


def evaluate_roster_snapshot_freshness(
    table_exists: bool,
    n_rows: int,
    latest: datetime | None,
    now: datetime,
    table_created: datetime | None = None,
    max_age_days: float = ROSTER_SNAPSHOT_MAX_AGE_DAYS,
) -> tuple[bool, str, str]:
    """
    Returns (ok, state, detail) for reporting in the validation output.

    state is one of "not deployed", "awaiting first capture", "stale", or
    "fresh" -- always in these plain words, so the report never has to fall
    back to a bare tick or cross to say which of the three is true.

    There is deliberately no separate "empty window" constant. The same
    `max_age_days` budget that already governs "how long since the last
    capture" also governs "how long since this table existed with zero
    captures": there is no principled reason a freshly-created table should
    get a more generous grace period than an established one that missed a
    run. In practice the gap between `terraform apply` creating the table
    and the first scheduled capture (daily, 08:00 UTC) is well under a day,
    so this budget is generous for state 2 and still tight enough to catch a
    capture job that is deployed but has never once succeeded.
    """
    if not table_exists:
        return True, "not deployed", "dataset/table does not exist yet"

    has_rows = n_rows > 0 and latest is not None
    reference = latest if has_rows else table_created
    if reference is None:
        # Table exists but we have neither a row timestamp nor a table
        # creation timestamp to measure age from. Don't guess -- treat as
        # failing so this doesn't silently pass forever.
        return False, "stale", "no rows, and no table creation time available"

    age_days = (now - reference).total_seconds() / 86400.0
    ok = age_days <= max_age_days
    if has_rows:
        state = "fresh" if ok else "stale"
        detail = f"{age_days:.1f} day(s) old (latest capture {reference})"
    else:
        state = "awaiting first capture" if ok else "stale"
        detail = f"table created {age_days:.1f} day(s) ago, no rows yet"
    return ok, state, detail
