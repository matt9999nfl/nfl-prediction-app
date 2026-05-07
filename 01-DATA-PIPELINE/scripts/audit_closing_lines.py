"""
Task 4 — Audit closing line fields in nfl_data_py schedules.

Checks spread_line and total_line across 2015-present:
  1. Are the fields present?
  2. What are the null rates per season?
  3. Documentation check: opening vs. closing line?

Run this BEFORE building the curated layer. Output drives the sourcing decision.

Usage:
    python scripts/audit_closing_lines.py
"""
import sys
sys.path.insert(0, ".")

import logging
from datetime import datetime

import nfl_data_py as nfl
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CURRENT_SEASON = datetime.now().year - (1 if datetime.now().month < 7 else 0)
SEASONS = list(range(2015, CURRENT_SEASON + 1))

LINE_FIELDS = ["spread_line", "total_line"]


def main():
    logger.info(f"Fetching schedules for {SEASONS[0]}–{SEASONS[-1]} ...")
    df = nfl.import_schedules(years=SEASONS)
    logger.info(f"Fetched {len(df)} rows, {len(df.columns)} columns")

    print("\n=== Closing Line Audit: nfl_data_py schedules ===\n")

    # 1. Check field presence
    for field in LINE_FIELDS:
        present = field in df.columns
        print(f"  Column '{field}' present: {present}")
    print()

    # 2. Filter to REG season only for null rate analysis
    if "game_type" in df.columns:
        reg = df[df["game_type"] == "REG"].copy()
    elif "season_type" in df.columns:
        reg = df[df["season_type"] == "REG"].copy()
    else:
        logger.warning("No game_type/season_type column — using all rows")
        reg = df.copy()

    print(f"REG season games: {len(reg)}\n")

    # 3. Null rate per season per field
    print(f"{'Season':<8}", end="")
    for f in LINE_FIELDS:
        if f in df.columns:
            print(f"  {f:<20}", end="")
    print(f"  {'REG games':<10}")
    print("-" * 65)

    season_col = "season" if "season" in reg.columns else "year"
    overall_nulls = {f: 0 for f in LINE_FIELDS}
    overall_total = 0

    for season in sorted(reg[season_col].unique()):
        sdf = reg[reg[season_col] == season]
        n = len(sdf)
        overall_total += n
        print(f"  {season:<6}", end="")
        for f in LINE_FIELDS:
            if f in sdf.columns:
                null_n = sdf[f].isna().sum()
                null_pct = 100 * null_n / n if n > 0 else 0
                overall_nulls[f] += null_n
                print(f"  {null_n:>4} null ({null_pct:5.1f}%)   ", end="")
        print(f"  {n}")

    print("-" * 65)
    print(f"  {'TOTAL':<6}", end="")
    for f in LINE_FIELDS:
        if f in reg.columns:
            pct = 100 * overall_nulls[f] / overall_total if overall_total > 0 else 0
            print(f"  {overall_nulls[f]:>4} null ({pct:5.1f}%)   ", end="")
    print(f"  {overall_total}")

    # 4. Sample non-null values to spot-check
    print("\n=== Sample spread_line values (first 10 non-null REG games) ===")
    if "spread_line" in reg.columns:
        sample = reg[reg["spread_line"].notna()][
            ["season", "week", "home_team", "away_team", "spread_line", "total_line"]
        ].head(10)
        print(sample.to_string(index=False))

    # 5. Value distribution
    print("\n=== spread_line value distribution (REG, all seasons) ===")
    if "spread_line" in reg.columns:
        dist = reg["spread_line"].value_counts().sort_index().head(20)
        print(dist.to_string())

    # 6. Documentation note
    print("""
=== Source Notes ===
nflverse documents spread_line as the CLOSING spread (home-team perspective,
negative = home favored). This matches Pro-Football-Reference closing lines.
Source: https://nflverse.nflverse.com/reference/schedules.html

DECISION CRITERIA (per spec):
  - If overall null rate < 5% for REG 2015-present → USE nflverse schedules (Option 1)
  - Else investigate Option 2 (nflverse game_lines) or Option 3 (the-odds-api)
""")

    overall_spread_null_pct = 100 * overall_nulls.get("spread_line", 0) / overall_total if overall_total > 0 else 100
    if overall_spread_null_pct <= 5.0:
        print(f"RESULT: spread_line null rate = {overall_spread_null_pct:.1f}% ≤ 5% → OPTION 1 PASSES")
        print("Recommendation: use nflverse schedules spread_line/total_line directly.")
        print("No separate raw_lines.closing_spreads table needed.")
    else:
        print(f"RESULT: spread_line null rate = {overall_spread_null_pct:.1f}% > 5% → OPTION 1 FAILS")
        print("Recommendation: evaluate Option 2 or 3 before building curated layer.")


if __name__ == "__main__":
    main()
