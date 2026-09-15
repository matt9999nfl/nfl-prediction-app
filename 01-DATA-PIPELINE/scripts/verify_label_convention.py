#!/usr/bin/env python3
"""
Verify the spread sign convention and the ATS label, against the data itself.

Why this exists
---------------
`home_spread_close` carries a sign convention that is the OPPOSITE of the one
people read spreads in:

    nflverse `spread_line` — POSITIVE means the home team is FAVOURED
    betting notation       — NEGATIVE means favoured ("PHI -6.0")

Everything downstream — the ATS label, the model's target, the dashboard — is
built on getting that right, and the project has already been burned twice by
sign errors near this column:

  * INC-001: a label inversion produced a 58-61% ATS result that was not real.
  * 2026-09-10: `audit_closing_lines.py` carried a comment asserting the opposite
    convention to the one `derive_home_covered()` actually used. The code was
    right and the comment was wrong, which is the more dangerous way round.
  * 2026-09-14: the dashboard printed `home_spread_close` in betting notation
    without converting, showing every favourite as an underdog on all 16 games
    of the 2026 week-1 slate.

Each time, the question "which way round is it?" was answered by reading a
document. This script answers it from the data, so the answer cannot rot.

What it checks
--------------
  C1  Convention (outright)  — favourites should win outright well over half the
                               time. Under an inverted reading this flips below
                               50%. Needs no documentation to interpret.
  C2  Label agreement        — re-derive home_covered from margin vs spread and
                               compare against what is stored, row by row.
  C3  Push handling          — margin exactly equal to the spread must store NULL.
  C4  Unexplained NULLs      — a completed game with a spread and a non-push
                               margin must not have a NULL label.
  C5  Orphan labels          — a game with no score must not carry a label.
  C6  ATS balance            — home_covered should sit near 50% over a large
                               sample. A large skew means something is wrong even
                               if every row is self-consistent.

C2 deliberately restates the rule rather than importing `derive_home_covered()`.
Importing the function under test would make this a tautology.

Usage
-----
    python scripts/verify_label_convention.py                  # all seasons
    python scripts/verify_label_convention.py --season 2026
    python scripts/verify_label_convention.py --season 2026 --week 1
    python scripts/verify_label_convention.py --quiet          # summary only

Exit code is 0 when every check passes, 1 otherwise, so this can gate CI.
Requires GCP auth (ADC or GOOGLE_APPLICATION_CREDENTIALS), like every other
script here.
"""
from __future__ import annotations

import argparse
import sys

from google.cloud import bigquery

PROJECT = "nfl-model-471509"
GAMES_TABLE = f"{PROJECT}.curated.games"

# A season's worth of games is ~270. Below this, the rate-based checks (C1, C6)
# are noise and are reported as inconclusive rather than passed or failed.
MIN_SAMPLE_FOR_RATES = 200

# C1: favourites win outright roughly 66-70% of the time in the modern NFL.
# The bound is deliberately loose — this check is looking for an inverted sign
# (which lands near 30%), not for a subtle drift.
FAVOURITE_WIN_RATE_FLOOR = 0.55

# C6: ATS outcomes are close to a coin flip by construction. Anything outside
# this band means the label or the line is wrong somewhere.
ATS_BAND = (0.42, 0.58)


class Check:
    """One named check with a verdict and a human-readable line."""

    def __init__(self, cid: str, name: str):
        self.cid, self.name = cid, name
        self.status = "PASS"          # PASS | FAIL | SKIP
        self.detail = ""
        self.rows: list[str] = []

    def fail(self, detail: str, rows: list[str] | None = None) -> "Check":
        self.status, self.detail = "FAIL", detail
        self.rows = rows or []
        return self

    def skip(self, detail: str) -> "Check":
        self.status, self.detail = "SKIP", detail
        return self

    def ok(self, detail: str) -> "Check":
        self.status, self.detail = "PASS", detail
        return self


def load_games(client: bigquery.Client, season: int | None, week: int | None) -> list[dict]:
    where = ["season_type = 'REG'"]
    params = []
    if season is not None:
        where.append("season = @season")
        params.append(bigquery.ScalarQueryParameter("season", "INT64", season))
    if week is not None:
        where.append("week = @week")
        params.append(bigquery.ScalarQueryParameter("week", "INT64", week))

    query = f"""
        SELECT game_id, season, week, home_team, away_team,
               home_score, away_score, home_spread_close, home_covered
        FROM `{GAMES_TABLE}`
        WHERE {' AND '.join(where)}
        ORDER BY season, week, game_id
    """
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    return [dict(r) for r in client.query(query, job_config=job_config).result()]


def run_checks(games: list[dict]) -> list[Check]:
    played = [g for g in games if g["home_score"] is not None and g["away_score"] is not None]
    with_line = [g for g in played if g["home_spread_close"] is not None]

    checks: list[Check] = []

    # ── C1 — the convention, decided by outright results ──────────────────────
    c1 = Check("C1", "Sign convention (favourites win outright)")
    decisive = [g for g in with_line
                if g["home_spread_close"] != 0 and g["home_score"] != g["away_score"]]
    if len(decisive) < MIN_SAMPLE_FOR_RATES:
        c1.skip(f"only {len(decisive)} decisive games — need {MIN_SAMPLE_FOR_RATES}")
    else:
        # Positive spread => home favoured.
        fav_won = sum(
            1 for g in decisive
            if (g["home_spread_close"] > 0) == (g["home_score"] > g["away_score"])
        )
        rate = fav_won / len(decisive)
        msg = f"favourites won {fav_won}/{len(decisive)} = {rate:.1%}"
        if rate >= FAVOURITE_WIN_RATE_FLOOR:
            c1.ok(f"{msg} — consistent with POSITIVE = home favoured")
        else:
            c1.fail(
                f"{msg} — below {FAVOURITE_WIN_RATE_FLOOR:.0%}. If this is near "
                f"{1 - rate:.0%} inverted, the sign convention is backwards "
                "somewhere upstream."
            )
    checks.append(c1)

    # ── C2 — stored label vs re-derived label ─────────────────────────────────
    c2 = Check("C2", "Stored home_covered matches margin vs spread")
    mismatches = []
    for g in with_line:
        margin = g["home_score"] - g["away_score"]
        spread = g["home_spread_close"]
        expected = None if margin == spread else (margin > spread)
        if g["home_covered"] != expected:
            mismatches.append(
                f"{g['game_id']}: {g['away_team']} {g['away_score']} @ "
                f"{g['home_team']} {g['home_score']}  margin={margin:+g} "
                f"spread={spread:+g}  stored={g['home_covered']} expected={expected}"
            )
    if mismatches:
        c2.fail(f"{len(mismatches)} of {len(with_line)} games disagree", mismatches)
    else:
        c2.ok(f"all {len(with_line)} games with a line agree")
    checks.append(c2)

    # ── C3 — pushes ───────────────────────────────────────────────────────────
    c3 = Check("C3", "Pushes stored as NULL")
    pushes = [g for g in with_line if g["home_score"] - g["away_score"] == g["home_spread_close"]]
    bad = [f"{g['game_id']}: push but home_covered={g['home_covered']}"
           for g in pushes if g["home_covered"] is not None]
    if bad:
        c3.fail(f"{len(bad)} of {len(pushes)} pushes carry a non-null label", bad)
    else:
        c3.ok(f"{len(pushes)} push(es), all NULL")
    checks.append(c3)

    # ── C4 — completed, lined, non-push games must carry a label ──────────────
    c4 = Check("C4", "No unexplained NULL labels")
    orphans = [
        f"{g['game_id']}: score {g['home_score']}-{g['away_score']}, "
        f"spread={g['home_spread_close']:+g}, label is NULL but not a push"
        for g in with_line
        if g["home_covered"] is None
        and g["home_score"] - g["away_score"] != g["home_spread_close"]
    ]
    if orphans:
        c4.fail(f"{len(orphans)} completed game(s) missing a label", orphans)
    else:
        c4.ok("every completed, lined, non-push game has a label")
    checks.append(c4)

    # ── C5 — labels on unplayed games ─────────────────────────────────────────
    c5 = Check("C5", "No labels on unplayed games")
    ghosts = [f"{g['game_id']}: no score but home_covered={g['home_covered']}"
              for g in games
              if g["home_score"] is None and g["home_covered"] is not None]
    if ghosts:
        c5.fail(f"{len(ghosts)} unplayed game(s) carry a label", ghosts)
    else:
        c5.ok("none")
    checks.append(c5)

    # ── C6 — ATS balance ──────────────────────────────────────────────────────
    c6 = Check("C6", "ATS outcomes near 50/50")
    labelled = [g for g in with_line if g["home_covered"] is not None]
    if len(labelled) < MIN_SAMPLE_FOR_RATES:
        c6.skip(f"only {len(labelled)} labelled games — need {MIN_SAMPLE_FOR_RATES}")
    else:
        covered = sum(1 for g in labelled if g["home_covered"])
        rate = covered / len(labelled)
        msg = f"home covered {covered}/{len(labelled)} = {rate:.1%}"
        if ATS_BAND[0] <= rate <= ATS_BAND[1]:
            c6.ok(msg)
        else:
            c6.fail(f"{msg} — outside {ATS_BAND[0]:.0%}-{ATS_BAND[1]:.0%}")
    checks.append(c6)

    return checks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--season", type=int, help="Restrict to one season.")
    ap.add_argument("--week", type=int, help="Restrict to one week (needs --season).")
    ap.add_argument("--quiet", action="store_true", help="Summary only; no offending rows.")
    args = ap.parse_args()

    if args.week is not None and args.season is None:
        print("--week requires --season", file=sys.stderr)
        return 2

    client = bigquery.Client(project=PROJECT)
    games = load_games(client, args.season, args.week)

    scope = "all seasons" if args.season is None else (
        f"{args.season}" + (f" week {args.week}" if args.week is not None else "")
    )
    played = sum(1 for g in games if g["home_score"] is not None)
    print()
    print(f"  LABEL CONVENTION CHECK — {scope}")
    print(f"  {len(games)} games, {played} played")
    print("  " + "-" * 64)

    if not games:
        print("  No games matched. Nothing to check.")
        print()
        return 1

    checks = run_checks(games)
    for c in checks:
        mark = {"PASS": "ok  ", "FAIL": "FAIL", "SKIP": "skip"}[c.status]
        print(f"  [{mark}] {c.cid}  {c.name}")
        print(f"          {c.detail}")
        if c.rows and not args.quiet:
            for r in c.rows[:20]:
                print(f"            - {r}")
            if len(c.rows) > 20:
                print(f"            ... and {len(c.rows) - 20} more")
    print("  " + "-" * 64)

    failed = [c for c in checks if c.status == "FAIL"]
    skipped = [c for c in checks if c.status == "SKIP"]
    if failed:
        print(f"  {len(failed)} CHECK(S) FAILED: {', '.join(c.cid for c in failed)}")
        print()
        return 1

    tail = f" ({len(skipped)} skipped for sample size)" if skipped else ""
    print(f"  All checks passed{tail}.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
