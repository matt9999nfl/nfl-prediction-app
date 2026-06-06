"""
Side-by-side experiment comparison script — Phase 4 Track 2 (item 2.4).

CLI
---
    python backtests/compare_experiments.py --run_ids <id1> <id2> [<id3> ...]

Outputs
-------
  Markdown table printed to stdout
  backtests/reports/{timestamp}_comparison.md   (written file)

Sources
-------
  experiments.backtest_runs       — aggregate metrics (hit rate, n_games, gate_passed)
  experiments.backtest_predictions — per-season breakdown
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PROJECT     = "nfl-model-471509"
REPORTS_DIR = ROOT / "backtests" / "reports"

RUNS_TABLE  = f"{PROJECT}.experiments.backtest_runs"
PREDS_TABLE = f"{PROJECT}.experiments.backtest_predictions"


# ── Data loaders ─────────────────────────────────────────────────────────────

def _load_run_summaries(client: bigquery.Client, run_ids: list[str]) -> dict[str, dict]:
    """Load aggregate stats for each run_id from backtest_runs."""
    placeholders = ", ".join(f"'{rid}'" for rid in run_ids)
    query = f"""
        SELECT
            run_id, name, ats_hit_rate, n_games_evaluated, gate_passed,
            feature_importances
        FROM `{RUNS_TABLE}`
        WHERE run_id IN ({placeholders})
        ORDER BY run_at DESC
    """
    rows = list(client.query(query).result())

    # Keep only the most-recent row per run_id (in case of duplicates)
    seen: dict[str, dict] = {}
    for row in rows:
        rid = row["run_id"]
        if rid not in seen:
            d = dict(row)
            if isinstance(d.get("feature_importances"), str):
                try:
                    d["feature_importances"] = json.loads(d["feature_importances"])
                except Exception:
                    d["feature_importances"] = {}
            seen[rid] = d

    missing = [rid for rid in run_ids if rid not in seen]
    if missing:
        logger.warning(f"run_ids not found in backtest_runs: {missing}")

    return seen


def _load_per_season(client: bigquery.Client, run_ids: list[str]) -> dict[str, pd.DataFrame]:
    """Load per-season hit rates for each run_id from backtest_predictions."""
    placeholders = ", ".join(f"'{rid}'" for rid in run_ids)
    query = f"""
        SELECT
            run_id,
            season,
            COUNTIF(correct = 1)                                            AS wins,
            COUNTIF(correct = 0)                                            AS losses,
            COUNTIF(correct IS NULL)                                        AS pushes,
            SAFE_DIVIDE(COUNTIF(correct = 1), COUNTIF(correct IS NOT NULL)) AS hit_rate,
            COUNTIF(correct IS NOT NULL)                                    AS n_games
        FROM `{PREDS_TABLE}`
        WHERE run_id IN ({placeholders})
        GROUP BY run_id, season
        ORDER BY run_id, season
    """
    df = client.query(query).to_dataframe()

    result: dict[str, pd.DataFrame] = {}
    for rid in run_ids:
        result[rid] = df[df["run_id"] == rid].drop(columns=["run_id"]).reset_index(drop=True)

    return result


# ── Markdown table builder ────────────────────────────────────────────────────

def _top_features(fi: dict | None, n: int = 3) -> list[str]:
    if not fi:
        return ["—"] * n
    sorted_feats = sorted(fi.items(), key=lambda x: x[1], reverse=True)
    names = [f for f, _ in sorted_feats[:n]]
    while len(names) < n:
        names.append("—")
    return names


def build_comparison_table(
    run_ids: list[str],
    summaries: dict[str, dict],
    per_season: dict[str, pd.DataFrame],
) -> str:
    """Return a Markdown comparison table as a string."""
    # Column widths — use run_id truncated to 12 chars as header
    headers = ["Metric"] + [rid[:16] for rid in run_ids]
    sep     = ["-" * max(len(h), 20) for h in headers]

    def row(label: str, values: list[str]) -> str:
        cells = [label] + values
        return "| " + " | ".join(cells) + " |"

    def pct(v) -> str:
        if v is None or (isinstance(v, float) and v != v):
            return "—"
        return f"{float(v):.1%}"

    lines: list[str] = []

    # Header
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(sep) + " |")

    # Names
    lines.append(row("Name", [summaries.get(rid, {}).get("name", "—")[:40] for rid in run_ids]))

    # Overall hit rate
    lines.append(row("Overall hit rate",
                     [pct(summaries.get(rid, {}).get("ats_hit_rate")) for rid in run_ids]))

    # N games
    lines.append(row("N games",
                     [str(summaries.get(rid, {}).get("n_games_evaluated", "—")) for rid in run_ids]))

    # Gate passed
    lines.append(row("Gate passed",
                     [str(summaries.get(rid, {}).get("gate_passed", "—")) for rid in run_ids]))

    # Per-season rows
    all_seasons: set[int] = set()
    for rid in run_ids:
        ps = per_season.get(rid, pd.DataFrame())
        if not ps.empty:
            all_seasons.update(ps["season"].tolist())

    for season in sorted(all_seasons):
        season_vals = []
        for rid in run_ids:
            ps = per_season.get(rid, pd.DataFrame())
            row_df = ps[ps["season"] == season]
            if row_df.empty:
                season_vals.append("—")
            else:
                hr = row_df["hit_rate"].iloc[0]
                n  = row_df["n_games"].iloc[0]
                season_vals.append(f"{pct(hr)} ({int(n)}g)")
        lines.append(row(f"Season {season}", season_vals))

    # Top features
    for i in range(1, 4):
        feat_vals = []
        for rid in run_ids:
            fi = summaries.get(rid, {}).get("feature_importances") or {}
            top = _top_features(fi, n=3)
            feat_vals.append(top[i - 1])
        lines.append(row(f"Top feature {i}", feat_vals))

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Compare multiple backtest run_ids side by side")
    parser.add_argument("--run_ids", nargs="+", required=True, help="Two or more run_ids to compare")
    parser.add_argument("--project", default=PROJECT, help="GCP project")
    args = parser.parse_args()

    if len(args.run_ids) < 2:
        parser.error("At least two run_ids are required for comparison")

    client = bigquery.Client(project=args.project)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    logger.info(f"Loading summaries for {len(args.run_ids)} runs ...")
    summaries  = _load_run_summaries(client, args.run_ids)

    logger.info("Loading per-season breakdown ...")
    per_season = _load_per_season(client, args.run_ids)

    table_md = build_comparison_table(args.run_ids, summaries, per_season)

    # Print to stdout
    print("\n" + table_md + "\n")

    # Write to file
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = REPORTS_DIR / f"{ts}_comparison.md"
    out_path.write_text(table_md + "\n", encoding="utf-8")
    logger.info(f"Wrote: {out_path}")
    print(f"Comparison written to: {out_path}")


if __name__ == "__main__":
    main()
