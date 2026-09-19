"""
Pure freshness check for raw_roster_snapshots.{injury_report_snapshots,
depth_chart_snapshots} (PROMPT-CAPTURE-INJURY-SNAPSHOTS.md).

Split out of validate_and_report.py, same reason as line_snapshot_freshness.py:
this one check needs to be testable without a BigQuery client, credentials, or
network. Mirrors that module's shape deliberately -- it is the established,
correct answer to "how does a capture failure become visible" (B1-2a lesson,
QUESTIONS.md 2026-09-18): not a log line, not a crash, a failed check here.
"""
from __future__ import annotations

from datetime import datetime

# This capture runs daily (not weekly, like line_snapshots), so its staleness
# budget is tighter. 3 days tolerates one missed weekend run without a false
# failure but still catches a stuck capture well inside a week -- long before
# the next injury report cycle would need it.
ROSTER_SNAPSHOT_MAX_AGE_DAYS = 3


def evaluate_roster_snapshot_freshness(
    n_rows: int, latest: datetime | None, now: datetime,
    max_age_days: float = ROSTER_SNAPSHOT_MAX_AGE_DAYS,
) -> tuple[bool, str]:
    """Returns (ok, age_txt) for reporting in the validation output."""
    if n_rows == 0 or latest is None:
        return False, "no rows"
    age_days = (now - latest).total_seconds() / 86400.0
    ok = age_days <= max_age_days
    return ok, f"{age_days:.1f} day(s) old (latest capture {latest})"
