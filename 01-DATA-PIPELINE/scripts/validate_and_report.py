"""
Phase 1 Validation Report — runs all checks from the spec and produces
a Markdown report at 01-DATA-PIPELINE/VALIDATION_REPORT.md.

Usage:
    python scripts/validate_and_report.py

Prerequisite: all ingest + curated build scripts must have completed.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")

from scripts.bq_utils import PROJECT, get_client
from scripts.line_snapshot_freshness import (
    LINE_SNAPSHOT_MAX_AGE_DAYS,
    evaluate_line_snapshot_freshness,
)
from scripts.roster_snapshot_freshness import (
    ROSTER_SNAPSHOT_MAX_AGE_DAYS,
    evaluate_roster_snapshot_freshness,
)

REPORT_PATH = Path(__file__).parent.parent / "VALIDATION_REPORT.md"

CURRENT_SEASON = datetime.now().year - (1 if datetime.now().month < 7 else 0)
SEASONS = list(range(2015, CURRENT_SEASON + 1))


def run_query(client, sql: str):
    return client.query(sql).to_dataframe()


def is_in_progress_season(label: str) -> bool:
    """
    True when a check label refers to the season currently being played.

    Labels embed their season (`pbp_2026_row_count`, `spread_null_rate_2026`),
    so this catches every per-season check at one choke point.
    """
    token = str(CURRENT_SEASON)
    return f"_{token}_" in label or label.endswith(f"_{token}")


def fetch_line_snapshot_status(client, now: datetime | None = None) -> tuple[bool, str, str | None]:
    """
    Query raw_lines.line_snapshots and evaluate freshness for the validation
    report. Never raises: an unreadable table (missing IAM grant, dropped
    dataset, wrong project -- see QUESTIONS.md 2026-09-18) is a FAILED check
    with the query error attached, not a crashed report. Before this, the
    query itself raised straight out of main(), which killed the whole
    pipeline process and, because Cloud Run auto-retries a failed container,
    turned one unreadable table into four full pipeline reruns.

    Returns (ok, summary, query_error):
      ok           -- whether this check should count as a PASS
      summary      -- one-line description for the report row
      query_error  -- the exception text if the query itself failed, else None
    """
    if now is None:
        now = datetime.now(timezone.utc)
    try:
        snap_freshness = run_query(client, f"""
            SELECT COUNT(*) AS n_rows, MAX(captured_at) AS latest
            FROM `{PROJECT}.raw_lines.line_snapshots`
        """)
    except Exception as exc:
        return False, "query failed", str(exc)

    sf = snap_freshness.iloc[0]
    n_rows = int(sf["n_rows"])
    latest = sf["latest"]
    ok, age_txt = evaluate_line_snapshot_freshness(n_rows, latest, now)
    return ok, f"{n_rows:,} row(s) total, latest capture {age_txt}", None


def _is_dataset_or_table_not_found(exc: Exception) -> bool:
    """
    True when a BigQuery failure means "this dataset or table does not
    exist" (`google.api_core.exceptions.NotFound` in production), as
    opposed to some other failure (missing IAM grant, network error) at the
    same call site.

    Matched by exception class name rather than
    `isinstance(exc, google.api_core.exceptions.NotFound)`: some of this
    repo's other test modules (test_snapshot_lines.py,
    test_capture_injury_snapshots.py) replace `sys.modules["google"]`
    wholesale to stub out `google.cloud.bigquery` without credentials,
    which breaks a plain `from google.api_core.exceptions import NotFound`
    whenever those modules are collected first in the same pytest session.
    Name-matching sidesteps that without touching those other tests, which
    are out of this stage's scope.
    """
    return type(exc).__name__ == "NotFound"


def fetch_roster_snapshot_status(
    client, table: str, now: datetime | None = None,
) -> tuple[bool, str, str, str | None]:
    """
    Same pattern as fetch_line_snapshot_status, for one of the two
    raw_roster_snapshots tables (PROMPT-CAPTURE-INJURY-SNAPSHOTS.md). Never
    raises: an unreadable table (missing IAM grant, wrong project) is a
    FAILED check with the query error attached, not a crashed report --
    this is a separately-scheduled job from the main pipeline (design point
    1), so its own failures must not be able to take this report down
    either.

    PROMPT-FIX-ROSTER-FRESHNESS-STATES.md (2026-09-21): "the dataset/table
    doesn't exist" is distinguished from every other query failure -- it
    means "the capture job was never deployed", not "something is broken",
    and must not be reported the same way a real query failure is. When the
    table exists but is empty, its creation time (BigQuery exposes this via
    get_table()) tells apart "just deployed, awaiting its first capture"
    from "has existed too long with nothing in it" -- see
    roster_snapshot_freshness.py for the age budget used for both.

    Returns (ok, state, summary, query_error):
      ok           -- whether this check should count as a PASS
      state        -- one of "not deployed", "awaiting first capture",
                       "stale", "fresh" (see roster_snapshot_freshness.py)
      summary      -- one-line description for the report row
      query_error  -- the exception text if a query failed for a reason
                       other than "table not found", else None
    """
    if now is None:
        now = datetime.now(timezone.utc)
    table_ref = f"{PROJECT}.raw_roster_snapshots.{table}"

    try:
        freshness = run_query(client, f"""
            SELECT COUNT(*) AS n_rows, MAX(captured_at) AS latest
            FROM `{table_ref}`
        """)
    except Exception as exc:
        if _is_dataset_or_table_not_found(exc):
            ok, state, detail = evaluate_roster_snapshot_freshness(
                table_exists=False, n_rows=0, latest=None, now=now,
            )
            return ok, state, detail, None
        return False, "query failed", "query failed", str(exc)

    f = freshness.iloc[0]
    n_rows = int(f["n_rows"])
    latest = f["latest"]

    table_created = None
    if n_rows == 0:
        # Only needed to place an empty table within its creation-time
        # budget -- skip the extra call when there are rows to judge by.
        try:
            table_created = client.get_table(table_ref).created
        except Exception as exc:
            return False, "query failed", "query failed", str(exc)

    ok, state, detail = evaluate_roster_snapshot_freshness(
        table_exists=True, n_rows=n_rows, latest=latest, now=now,
        table_created=table_created,
    )
    return ok, state, f"{n_rows:,} row(s) total, {detail}", None


def check(condition: bool, label: str, results: list) -> bool:
    """
    Record a check. Returns whether it should count toward pass/fail.

    INC-002 (2026-09-07): every threshold in this report describes a COMPLETED
    season -- full row counts, populated closing lines, settled cover rates.
    The season being played satisfies none of them until it is over, so
    applying them to it fails the report on every run all season and takes the
    pipeline's exit code with it.

    In-progress checks are still RUN and still REPORTED, so nothing is hidden;
    they are simply advisory and do not fail the run. Completed seasons are
    unchanged -- the historical guarantees this report exists to provide are
    exactly as strict as they were.
    """
    if is_in_progress_season(label):
        results.append((label, "⚠️ IN-PROGRESS" if not condition else "✅ PASS"))
        return True

    status = "✅ PASS" if condition else "❌ FAIL"
    results.append((label, status))
    return condition


def main(client=None):
    if client is None:
        client = get_client()
    lines = []
    check_results = []
    all_pass = True

    def h(text): lines.append(f"\n{text}\n{'=' * len(text)}\n")
    def h2(text): lines.append(f"\n### {text}\n")
    def row(text): lines.append(text)

    lines.append("# Phase 1 Validation Report")
    lines.append(f"\n**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"**Project:** `{PROJECT}`")
    lines.append(f"**Seasons:** 2015–{CURRENT_SEASON}")
    lines.append(
        f"\n> Checks for **{CURRENT_SEASON}** are advisory: that season is still being "
        f"played, so completed-season thresholds do not apply to it yet. They are "
        f"shown as ⚠️ IN-PROGRESS and do not fail this report. Every earlier season "
        f"is held to the full standard."
    )

    # ------------------------------------------------------------------ #
    # 1. Row counts — raw tables                                          #
    # ------------------------------------------------------------------ #
    h("1. Row Counts — Raw Tables")

    h2("raw_nflfastr.pbp (all rows including preseason)")
    pbp_counts = run_query(client, f"""
        SELECT season, COUNT(*) AS row_count
        FROM `{PROJECT}.raw_nflfastr.pbp`
        GROUP BY season ORDER BY season
    """)
    row("| Season | Rows | Check |")
    row("|--------|------|-------|")
    for _, r in pbp_counts.iterrows():
        s, n = int(r["season"]), int(r["row_count"])
        ok = 40_000 <= n <= 70_000
        all_pass &= check(ok, f"pbp_{s}_row_count", check_results)
        row(f"| {s} | {n:,} | {'✅' if ok else '❌'} |")

    h2("raw_nflfastr.schedules")
    sched_counts = run_query(client, f"""
        SELECT season, COUNT(*) AS row_count
        FROM `{PROJECT}.raw_nflfastr.schedules`
        GROUP BY season ORDER BY season
    """)
    row("| Season | Rows | Check |")
    row("|--------|------|-------|")
    for _, r in sched_counts.iterrows():
        s, n = int(r["season"]), int(r["row_count"])
        ok = 256 <= n <= 290
        all_pass &= check(ok, f"schedules_{s}_row_count", check_results)
        row(f"| {s} | {n:,} | {'✅' if ok else '❌'} |")

    h2("raw_nflfastr.rosters")
    roster_counts = run_query(client, f"""
        SELECT season, COUNT(*) AS row_count
        FROM `{PROJECT}.raw_nflfastr.rosters`
        GROUP BY season ORDER BY season
    """)
    row("| Season | Rows | Check |")
    row("|--------|------|-------|")
    for _, r in roster_counts.iterrows():
        s, n = int(r["season"]), int(r["row_count"])
        ok = n > 500
        row(f"| {s} | {n:,} | {'✅' if ok else '❌'} |")

    # ------------------------------------------------------------------ #
    # 2. Row counts — curated tables                                      #
    # ------------------------------------------------------------------ #
    h("2. Row Counts — Curated Tables")

    h2("curated.games")
    games_counts = run_query(client, f"""
        SELECT season, COUNT(*) AS row_count
        FROM `{PROJECT}.curated.games`
        GROUP BY season ORDER BY season
    """)
    row("| Season | Games | Check |")
    row("|--------|-------|-------|")
    for _, r in games_counts.iterrows():
        s, n = int(r["season"]), int(r["row_count"])
        ok = 256 <= n <= 285
        all_pass &= check(ok, f"curated_games_{s}_row_count", check_results)
        row(f"| {s} | {n:,} | {'✅' if ok else '❌'} |")

    h2("curated.plays")
    plays_counts = run_query(client, f"""
        SELECT season, COUNT(*) AS row_count
        FROM `{PROJECT}.curated.plays`
        GROUP BY season ORDER BY season
    """)
    row("| Season | Plays | Check |")
    row("|--------|-------|-------|")
    for _, r in plays_counts.iterrows():
        s, n = int(r["season"]), int(r["row_count"])
        ok = 35_000 <= n <= 60_000
        all_pass &= check(ok, f"curated_plays_{s}_row_count", check_results)
        row(f"| {s} | {n:,} | {'✅' if ok else '❌'} |")

    # ------------------------------------------------------------------ #
    # 3. Null rate checks                                                  #
    # ------------------------------------------------------------------ #
    h("3. Null Rate Checks")

    h2("curated.games — closing line coverage")
    spread_nulls = run_query(client, f"""
        SELECT
            season,
            COUNTIF(home_spread_close IS NULL) AS spread_nulls,
            COUNT(*) AS total,
            ROUND(100 * COUNTIF(home_spread_close IS NULL) / COUNT(*), 2) AS null_pct
        FROM `{PROJECT}.curated.games`
        GROUP BY season ORDER BY season
    """)
    row("| Season | Spread Nulls | Total | Null % | Check |")
    row("|--------|-------------|-------|--------|-------|")
    for _, r in spread_nulls.iterrows():
        s, nulls, total, pct = int(r["season"]), int(r["spread_nulls"]), int(r["total"]), float(r["null_pct"])
        ok = pct <= 5.0
        all_pass &= check(ok, f"spread_null_rate_{s}", check_results)
        row(f"| {s} | {nulls} | {total} | {pct:.1f}% | {'✅' if ok else '❌'} |")

    h2("curated.plays — EPA null rate on pass/run plays")
    epa_null = run_query(client, f"""
        SELECT
            season,
            COUNTIF(epa IS NULL) AS epa_nulls,
            COUNT(*) AS total,
            ROUND(100 * COUNTIF(epa IS NULL) / COUNT(*), 2) AS null_pct
        FROM `{PROJECT}.curated.plays`
        WHERE play_type IN ('pass', 'run')
        GROUP BY season ORDER BY season
    """)
    row("| Season | EPA Nulls | Total Pass/Run | Null % | Check |")
    row("|--------|-----------|----------------|--------|-------|")
    for _, r in epa_null.iterrows():
        s, nulls, total, pct = int(r["season"]), int(r["epa_nulls"]), int(r["total"]), float(r["null_pct"])
        ok = pct <= 5.0
        all_pass &= check(ok, f"epa_null_rate_{s}", check_results)
        row(f"| {s} | {nulls} | {total:,} | {pct:.1f}% | {'✅' if ok else '❌'} |")

    h2("curated.plays — qb_hit / sack null rate (must be 0%)")
    bool_nulls = run_query(client, f"""
        SELECT
            COUNTIF(qb_hit IS NULL) AS qb_hit_nulls,
            COUNTIF(sack IS NULL) AS sack_nulls,
            COUNT(*) AS total
        FROM `{PROJECT}.curated.plays`
    """)
    r = bool_nulls.iloc[0]
    qb_ok = int(r["qb_hit_nulls"]) == 0
    sack_ok = int(r["sack_nulls"]) == 0
    all_pass &= check(qb_ok, "qb_hit_zero_nulls", check_results)
    all_pass &= check(sack_ok, "sack_zero_nulls", check_results)
    row(f"- qb_hit nulls: {int(r['qb_hit_nulls'])} / {int(r['total']):,}  {'✅' if qb_ok else '❌'}")
    row(f"- sack nulls:   {int(r['sack_nulls'])} / {int(r['total']):,}  {'✅' if sack_ok else '❌'}")

    # ------------------------------------------------------------------ #
    # 3b. Semantic distribution check — home_covered cover rate           #
    # ------------------------------------------------------------------ #
    h("3b. Semantic Check — home_covered Cover Rate")

    row("""
This check guards against a sign-inversion bug in `derive_home_covered`.
Because closing spreads represent the market's best estimate, the home team
cover rate in every spread bin must be approximately 50% (efficient market
hypothesis). A monotonic pattern (e.g. heavy favourites covering at <10%,
heavy underdogs covering at >90%) is a definitive sign of label inversion.
See INC-001 and PIPELINE_REMEDIATION_002.md for history.
""")

    cover_rate_sql = f"""
        WITH bins AS (
            SELECT
                CASE
                    WHEN home_spread_close <= -10 THEN 'home_fav_10+'
                    WHEN home_spread_close <= -3  THEN 'home_fav_3-10'
                    WHEN home_spread_close < 3    THEN 'pick_em'
                    WHEN home_spread_close < 10   THEN 'home_dog_3-10'
                    ELSE                               'home_dog_10+'
                END AS bucket,
                home_covered
            FROM `{PROJECT}.curated.games`
            WHERE season BETWEEN 2015 AND {CURRENT_SEASON}
              AND home_covered IS NOT NULL
        )
        SELECT
            bucket,
            COUNTIF(home_covered) AS covers,
            COUNT(*) AS total,
            ROUND(100 * COUNTIF(home_covered) / COUNT(*), 1) AS cover_pct
        FROM bins
        GROUP BY bucket
        ORDER BY bucket
    """
    cover_df = run_query(client, cover_rate_sql)

    row("| Spread Bucket | Covers | Total | Cover % | Check |")
    row("|---------------|--------|-------|---------|-------|")
    bin_all_pass = True
    for _, r in cover_df.iterrows():
        bucket = r["bucket"]
        covers = int(r["covers"])
        total = int(r["total"])
        pct = float(r["cover_pct"])
        ok = 45.0 <= pct <= 55.0
        bin_all_pass &= ok
        all_pass &= check(ok, f"cover_rate_{bucket}", check_results)
        row(f"| {bucket} | {covers} | {total} | {pct:.1f}% | {'✅' if ok else '❌'} |")

    # Overall cover rate check (tighter band: 46–54%)
    overall_sql = f"""
        SELECT
            COUNTIF(home_covered) AS covers,
            COUNT(*) AS total,
            ROUND(100 * COUNTIF(home_covered) / COUNT(*), 1) AS cover_pct,
            MIN(season) AS min_season,
            MAX(season) AS max_season
        FROM `{PROJECT}.curated.games`
        WHERE home_covered IS NOT NULL
    """
    overall_df = run_query(client, overall_sql)
    ov = overall_df.iloc[0]
    ov_covers = int(ov["covers"])
    ov_total = int(ov["total"])
    ov_pct = float(ov["cover_pct"])
    ov_min_s = int(ov["min_season"])
    ov_max_s = int(ov["max_season"])
    ov_ok = 46.0 <= ov_pct <= 54.0
    all_pass &= check(ov_ok, "overall_cover_rate_46_to_54", check_results)

    if ov_ok:
        row(f"\n- **Overall cover rate ({ov_min_s}–{ov_max_s}):** {ov_pct:.1f}%  ({ov_covers}/{ov_total})  ✅")
    else:
        row(
            f"\n- **Overall cover rate ({ov_min_s}–{ov_max_s}):** {ov_pct:.1f}%  ({ov_covers}/{ov_total})  ❌"
            f"\n  **ERROR:** home cover rate {ov_pct:.1f}% is outside the 46–54% sanity band for seasons"
            f" {ov_min_s}–{ov_max_s}. This is a strong indicator of a sign-inversion bug in"
            f" `derive_home_covered`. Do NOT hand off to MODELING until this is resolved."
            f" See INC-001 and PIPELINE_REMEDIATION_002.md."
        )

    # ------------------------------------------------------------------ #
    # 3c. Line snapshot freshness                                          #
    # ------------------------------------------------------------------ #
    h("3c. Line Snapshot Freshness")
    row("""
`raw_lines.line_snapshots` is written by `snapshot_lines.py`, called
non-fatally from `run_ingest_schedules()` on every pipeline run so a snapshot
failure never blocks PBP/rosters ingest. Non-fatal previously also meant
invisible: the failure (or the deployed image simply not containing this
code) was only ever a line in Cloud Logging, never in this report or the
run's exit code -- the same silent-failure-only-logs-can-find pattern as
HC-S6-F6. This check makes a stale, empty, or **unreadable** (e.g. a
missing IAM grant on `raw_lines` -- see QUESTIONS.md 2026-09-18) snapshot
table fail the run visibly, in the report, instead of crashing the process.
""")
    snap_ok, snap_summary, snap_error = fetch_line_snapshot_status(client)
    all_pass &= check(snap_ok, "line_snapshots_freshness", check_results)
    row(f"- `line_snapshots`: {snap_summary}  {'✅' if snap_ok else '❌'}")
    if snap_error:
        row(
            f"\n  **ERROR:** could not query `{PROJECT}.raw_lines.line_snapshots`: {snap_error}\n"
            "  This looks like an access problem (for example a missing BigQuery IAM grant "
            "for the pipeline's service account on the `raw_lines` dataset -- see "
            "QUESTIONS.md, 2026-09-18 entry) rather than a genuinely stale table. Fix the "
            "underlying access/table issue and re-run; do not treat this the same as a "
            "merely-stale snapshot below."
        )
    elif not snap_ok:
        row(
            f"\n  **ERROR:** no line snapshot has been captured in the last "
            f"{LINE_SNAPSHOT_MAX_AGE_DAYS} days (or the table is empty). The "
            "`snapshot()` call inside `run_ingest_schedules()` may be failing, or "
            "the deployed pipeline image may predate `snapshot_lines.py` (added "
            "2026-09-09) -- check the execution logs for \"Line snapshot\" / "
            "\"SNAPSHOT_FAILED\", and confirm the deployed `nfl-data-pipeline` "
            "image was built after that commit."
        )

    # ------------------------------------------------------------------ #
    # 3d. Roster snapshot freshness (injuries + depth charts)               #
    # ------------------------------------------------------------------ #
    h("3d. Roster Snapshot Freshness (Injuries + Depth Charts)")
    row("""
`raw_roster_snapshots.{injury_report_snapshots,depth_chart_snapshots}` are
written by `capture_injury_snapshots.py`, running as its own Cloud Run job on
its own daily schedule -- not inside this pipeline (PROMPT-CAPTURE-INJURY-
SNAPSHOTS.md, design point 1). Checking their freshness here, from a job that
never writes them, is deliberate: it is the same "loud in the report, not just
a log line" pattern line_snapshots uses (3c), applied to a capture that this
pipeline has no way to make happen itself.

Three states are distinguished, not one (PROMPT-FIX-ROSTER-FRESHNESS-STATES.md,
2026-09-21): **not deployed** (the dataset/table doesn't exist -- the capture
job simply hasn't been rolled out yet, not a failure), **awaiting first
capture** (deployed, table exists, no rows yet, but not long enough to expect
one -- not a failure yet), and **stale** (rows exist but the newest is too
old, or the table has existed too long with none at all -- this is the one
real failure, and it still fails this report and the run's exit code).
""")
    for table, label in (
        ("injury_report_snapshots", "injury_report_snapshots"),
        ("depth_chart_snapshots", "depth_chart_snapshots"),
    ):
        ok, state, summary, error = fetch_roster_snapshot_status(client, table)
        all_pass &= check(ok, f"roster_snapshot_freshness_{table}", check_results)
        row(f"- `{label}`: **{state}** -- {summary}  {'✅' if ok else '❌'}")
        if error:
            row(
                f"\n  **ERROR:** could not query `{PROJECT}.raw_roster_snapshots.{table}`: {error}\n"
                "  Likely a missing BigQuery IAM grant for the pipeline's service account on "
                "`raw_roster_snapshots` (write it up for Matt to apply -- see "
                "05-DEVOPS/infra/terraform/iam.tf). The table exists (this isn't the "
                "not-deployed case) but couldn't be read."
            )
        elif not ok and state == "stale":
            row(
                f"\n  **ERROR:** no `{label}` row captured in the last "
                f"{ROSTER_SNAPSHOT_MAX_AGE_DAYS} days (or the table has existed longer than "
                f"that with none at all). Check the `nfl-injury-capture` Cloud Run job's own "
                "execution logs -- this pipeline does not run that capture and cannot see why "
                "it stopped, only that it has."
            )

    # ------------------------------------------------------------------ #
    # 4. Integrity checks                                                  #
    # ------------------------------------------------------------------ #
    h("4. Integrity Checks")

    orphan = run_query(client, f"""
        SELECT COUNT(*) AS orphan_plays
        FROM `{PROJECT}.curated.plays` p
        LEFT JOIN `{PROJECT}.curated.games` g ON p.game_id = g.game_id
        WHERE g.game_id IS NULL
    """)
    orphan_n = int(orphan.iloc[0]["orphan_plays"])
    ok = orphan_n == 0
    all_pass &= check(ok, "referential_integrity_plays_to_games", check_results)
    row(f"\n- Orphan plays (game_id not in curated.games): {orphan_n}  {'✅' if ok else '❌'}")

    dupes = run_query(client, f"""
        SELECT COUNT(*) AS dupe_game_ids
        FROM (
            SELECT game_id, COUNT(*) AS cnt
            FROM `{PROJECT}.curated.games`
            GROUP BY game_id HAVING cnt > 1
        )
    """)
    dupe_n = int(dupes.iloc[0]["dupe_game_ids"])
    ok = dupe_n == 0
    all_pass &= check(ok, "no_duplicate_game_ids", check_results)
    row(f"- Duplicate game_ids in curated.games: {dupe_n}  {'✅' if ok else '❌'}")

    season_range = run_query(client, f"""
        SELECT MIN(season) AS min_s, MAX(season) AS max_s
        FROM `{PROJECT}.curated.games`
    """)
    min_s = int(season_range.iloc[0]["min_s"])
    max_s = int(season_range.iloc[0]["max_s"])
    ok = min_s >= 2015 and max_s <= CURRENT_SEASON
    all_pass &= check(ok, "season_range_in_scope", check_results)
    row(f"- Season range in curated.games: {min_s}–{max_s}  {'✅' if ok else '❌'}")

    # ------------------------------------------------------------------ #
    # 5. Summary                                                           #
    # ------------------------------------------------------------------ #
    h("5. Check Summary")
    passed = sum(1 for _, s in check_results if "PASS" in s)
    failed_list = [(l, s) for l, s in check_results if "FAIL" in s]
    row(f"**Total checks:** {len(check_results)}  |  **Passed:** {passed}  |  **Failed:** {len(failed_list)}")
    row(f"\n**Overall:** {'✅ ALL CHECKS PASSED — ready for handoff' if all_pass else '❌ SOME CHECKS FAILED — review before handoff'}")

    if failed_list:
        row("\n**Failed checks:**")
        for label, _ in failed_list:
            row(f"- {label}")

    # ------------------------------------------------------------------ #
    # 6. Closing line source decision                                      #
    # ------------------------------------------------------------------ #
    h("6. Closing Line Source")
    row("""
**Source chosen:** nflverse schedules (`spread_line` / `total_line` fields via `nfl_data_py.import_schedules()`)

**Rationale:** nflverse documents `spread_line` as the closing spread (home-team perspective,
negative = home favored), sourced from Pro-Football-Reference historical lines.
Null rate analysis above confirms coverage ≤ 5% across 2015–present for REG season games.
No separate `raw_lines.closing_spreads` table is needed (Option 1 from spec).

**Columns used:**
- `spread_line` → `curated.games.home_spread_close`
- `total_line`  → `curated.games.total_close`

**home_covered derivation:** `(home_score - away_score) > home_spread_close`
nflverse sign convention: positive spread_line = home favored (home must win by that amount).
Push (exactly equal) is stored as `NULL`.
""")

    # Write report
    report_text = "\n".join(lines)
    REPORT_PATH.write_text(report_text, encoding="utf-8")
    print(f"\nValidation report written to: {REPORT_PATH}")
    print(f"Overall: {'ALL CHECKS PASSED' if all_pass else 'SOME CHECKS FAILED'}")
    if not all_pass:
        sys.exit(1)


if __name__ == "__main__":
    main()
