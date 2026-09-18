"""
Pure freshness check for raw_lines.line_snapshots
(PROMPT-FIX-SPREAD-SIGN-AND-LINE-SNAPSHOTS.md Part B.5).

Split out of validate_and_report.py so this one check is testable without
pulling in bq_utils.py's BigQuery-client-typed imports — no credentials, no
network, no stubbing required.
"""
from __future__ import annotations

from datetime import datetime

# Pipeline runs happen multiple times a week, so 10 days catches a broken
# snapshot step within roughly one missed cycle. This is exactly the failure
# mode that went unnoticed for nine days (snapshot_lines.py added 2026-09-09,
# the deployed pipeline image never rebuilt to include it).
LINE_SNAPSHOT_MAX_AGE_DAYS = 10


def evaluate_line_snapshot_freshness(
    n_rows: int, latest: datetime | None, now: datetime,
    max_age_days: float = LINE_SNAPSHOT_MAX_AGE_DAYS,
) -> tuple[bool, str]:
    """Returns (ok, age_txt) for reporting in the validation output."""
    if n_rows == 0 or latest is None:
        return False, "no rows"
    age_days = (now - latest).total_seconds() / 86400.0
    ok = age_days <= max_age_days
    return ok, f"{age_days:.1f} day(s) old (latest capture {latest})"
