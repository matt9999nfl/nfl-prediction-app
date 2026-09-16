#!/usr/bin/env python3
"""
Report generator for the prior-season blend backtest (PROMPT-PRIOR-SEASON-BLEND.md §4).

Reads experiments.backtest_predictions for a set of experiment_ids (config
UUIDs) and computes, for each, per season 2023-2025 and combined:
  - log loss for weeks 2-4 and for all weeks
  - ATS % for weeks 2-4 and for all weeks
  - share of picks at >=0.10 from 50% (i.e. "high" confidence) in week 2
  - games counted (decided games only; pushes/nulls excluded)

Usage:
    python backtests/report_blend_backtest.py <label>=<experiment_id> [<label>=<experiment_id> ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from google.cloud import bigquery
from sklearn.metrics import log_loss

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PROJECT = "nfl-model-471509"
PREDS_TABLE = f"{PROJECT}.experiments.backtest_predictions"

CONFIRM_SEASONS = [2023, 2024, 2025]


def load_predictions(client: bigquery.Client, experiment_id: str) -> pd.DataFrame:
    query = f"""
        SELECT season, week, predicted_home_cover_prob, actual_home_covered, correct
        FROM `{PREDS_TABLE}`
        WHERE experiment_id = @eid
          AND season IN UNNEST(@seasons)
    """
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("eid", "STRING", experiment_id),
        bigquery.ArrayQueryParameter("seasons", "INT64", CONFIRM_SEASONS),
    ])
    df = client.query(query, job_config=job_config).to_dataframe()
    return df


def _log_loss(df: pd.DataFrame) -> float:
    decided = df.dropna(subset=["actual_home_covered"])
    if decided.empty:
        return float("nan")
    y = decided["actual_home_covered"].astype(int).values
    p = np.clip(decided["predicted_home_cover_prob"].astype(float).values, 1e-7, 1 - 1e-7)
    return float(log_loss(y, p))


def _ats_pct(df: pd.DataFrame) -> tuple[float, int]:
    decided = df.dropna(subset=["correct"])
    n = len(decided)
    if n == 0:
        return float("nan"), 0
    return float(decided["correct"].astype(int).mean()), n


def _high_conf_share_week2(df: pd.DataFrame) -> tuple[float, int]:
    wk2 = df[df["week"] == 2]
    if wk2.empty:
        return float("nan"), 0
    high = (wk2["predicted_home_cover_prob"] - 0.5).abs() >= 0.10
    return float(high.mean()), len(wk2)


def compute_metrics(df: pd.DataFrame, seasons: list[int] | None) -> dict:
    sub = df if seasons is None else df[df["season"].isin(seasons)]
    wk24 = sub[sub["week"].between(2, 4)]

    ll_wk24 = _log_loss(wk24)
    ll_all = _log_loss(sub)
    ats_wk24, n_wk24 = _ats_pct(wk24)
    ats_all, n_all = _ats_pct(sub)
    hi_share, n_wk2 = _high_conf_share_week2(sub)

    return {
        "log_loss_wk2_4": ll_wk24,
        "log_loss_all": ll_all,
        "ats_wk2_4": ats_wk24,
        "ats_all": ats_all,
        "n_games_wk2_4": n_wk24,
        "n_games_all": n_all,
        "high_conf_share_wk2": hi_share,
        "n_games_wk2": n_wk2,
    }


def format_report(label: str, df: pd.DataFrame) -> str:
    lines = [f"### {label}", ""]
    lines.append("| Season | LogLoss wk2-4 | LogLoss all | ATS% wk2-4 | ATS% all | Hi-conf share wk2 | Games (wk2-4 / all) |")
    lines.append("|---|---|---|---|---|---|---|")
    rows = []
    for s in CONFIRM_SEASONS:
        m = compute_metrics(df, [s])
        rows.append((str(s), m))
    combined = compute_metrics(df, None)
    rows.append(("Combined", combined))

    for label_s, m in rows:
        lines.append(
            f"| {label_s} | {m['log_loss_wk2_4']:.4f} | {m['log_loss_all']:.4f} | "
            f"{m['ats_wk2_4']:.1%} | {m['ats_all']:.1%} | {m['high_conf_share_wk2']:.1%} | "
            f"{m['n_games_wk2_4']} / {m['n_games_all']} |"
        )
    return "\n".join(lines)


def main() -> None:
    client = bigquery.Client(project=PROJECT)
    pairs = [arg.split("=", 1) for arg in sys.argv[1:]]
    if not pairs:
        print(__doc__)
        sys.exit(1)

    all_data = {}
    for label, eid in pairs:
        df = load_predictions(client, eid)
        all_data[label] = df
        print(format_report(label, df))
        print()

    # Bar check for each non-baseline label against 'baseline'
    if "baseline" in all_data:
        base_combined = compute_metrics(all_data["baseline"], None)
        base_wk24 = compute_metrics(all_data["baseline"], None)["log_loss_wk2_4"]
        base_all = compute_metrics(all_data["baseline"], None)["log_loss_all"]
        print("### Bar check (2023-2025 combined): log loss wk2-4 lower AND log loss all not higher than baseline")
        print(f"baseline: wk2-4={base_wk24:.4f}  all={base_all:.4f}")
        for label, df in all_data.items():
            if label == "baseline":
                continue
            m = compute_metrics(df, None)
            passed = (m["log_loss_wk2_4"] < base_wk24) and (m["log_loss_all"] <= base_all)
            print(f"{label}: wk2-4={m['log_loss_wk2_4']:.4f}  all={m['log_loss_all']:.4f}  BAR_MET={passed}")


if __name__ == "__main__":
    main()
