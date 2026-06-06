"""
Run all Phase 4 experiments sequentially, logging to _run_all_phase4_log.txt.
Check _run_all_phase4_log.txt for progress and results.
"""
import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
LOG_FILE = ROOT / "_run_all_phase4_log.txt"

def log(msg="", flush=True):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        if flush:
            f.flush()

# Wipe log
LOG_FILE.write_text("", encoding="utf-8")
log("Phase 4 re-run started")
log(f"Python: {sys.executable}")

sys.path.insert(0, str(ROOT))

from google.cloud import bigquery
PROJECT = "nfl-model-471509"
client = bigquery.Client(project=PROJECT)

CONFIGS = {
    "A2 (23-feature faithfulness)":      "6ec7deac-3c62-4954-a8d4-a7bfb21b410f",
    "A3 (shuffle-label leakage test)":   "decaa551-b991-43af-9a71-ab70b9580af7",
    "test3 (rush features)":             "19a50bf1-e812-4745-b153-042c6db46a00",
}

results = {}  # label -> run_id

for label, config_id in CONFIGS.items():
    log()
    log("=" * 60)
    log(f"Starting: {label}")
    log(f"Config ID: {config_id}")
    log("=" * 60)

    os.environ["EXPERIMENT_CONFIG_ID"] = config_id
    t0 = time.time()

    try:
        # Import fresh each time by removing cached module
        if "backtests.run_experiment" in sys.modules:
            del sys.modules["backtests.run_experiment"]

        from backtests.run_experiment import main
        main()
        elapsed = time.time() - t0
        log(f"Completed in {elapsed:.0f}s")

        # Fetch latest_run_id from BQ
        sql = f"""
            SELECT latest_run_id
            FROM `{PROJECT}.platform.experiment_configs`
            WHERE experiment_id = '{config_id}'
            LIMIT 1
        """
        rows = list(client.query(sql).result())
        run_id = rows[0]["latest_run_id"] if rows else None
        results[label] = run_id
        log(f"run_id: {run_id}")

    except Exception as e:
        elapsed = time.time() - t0
        log(f"FAILED after {elapsed:.0f}s: {e}")
        results[label] = None
        import traceback
        log(traceback.format_exc())
        # Continue to next experiment

log()
log("=" * 60)
log("ALL RUNS COMPLETE — Summary")
log("=" * 60)

for label, run_id in results.items():
    if run_id:
        sql = f"""
            SELECT overall_hit_rate, total_wins, total_losses, total_pushes, n_games, gate_passed
            FROM `{PROJECT}.experiments.backtest_runs`
            WHERE run_id = '{run_id}'
            LIMIT 1
        """
        rows = list(client.query(sql).result())
        if rows:
            r = rows[0]
            hr = float(r["overall_hit_rate"]) if r["overall_hit_rate"] is not None else None
            log(f"{label}:")
            log(f"  run_id:   {run_id}")
            log(f"  ATS:      {r['total_wins']}-{r['total_losses']}-{r['total_pushes']} ({r['n_games']} games)")
            log(f"  Hit rate: {hr:.3%}" if hr else "  Hit rate: N/A")
            log(f"  Gate:     {'PASSED' if r['gate_passed'] else 'not met'}")
        else:
            log(f"{label}: run_id={run_id} but no backtest_runs row found")
    else:
        log(f"{label}: FAILED (no run_id)")

# A1: Per-fold breakdown for test3
test3_run_id = results.get("test3 (rush features)")
if test3_run_id:
    log()
    log("=" * 60)
    log("A1: Per-fold breakdown for test3")
    log("=" * 60)
    fold_sql = f"""
    SELECT season,
      COUNTIF(correct = 1) AS wins,
      COUNTIF(correct = 0) AS losses,
      COUNTIF(correct IS NULL) AS pushes,
      SAFE_DIVIDE(COUNTIF(correct=1), COUNTIF(correct IS NOT NULL)) AS hit_rate,
      COUNTIF(correct IS NOT NULL) AS n_games
    FROM `{PROJECT}.experiments.backtest_predictions`
    WHERE run_id = '{test3_run_id}'
    GROUP BY season ORDER BY season
    """
    fold_rows = list(client.query(fold_sql).result())
    log(f"{'Season':<8} {'W':>6} {'L':>6} {'P':>6} {'Hit Rate':>10} {'N':>8}")
    log("-" * 48)
    total_w = total_l = total_p = 0
    above_54 = 0
    for r in fold_rows:
        w = int(r["wins"])
        l = int(r["losses"])
        p = int(r["pushes"])
        hr = float(r["hit_rate"]) if r["hit_rate"] is not None else 0.0
        n = int(r["n_games"])
        total_w += w; total_l += l; total_p += p
        if hr >= 0.54:
            above_54 += 1
        log(f"{r['season']:<8} {w:>6} {l:>6} {p:>6} {hr:>10.3%} {n:>8}")
    overall_hr = total_w / (total_w + total_l) if (total_w + total_l) > 0 else 0
    log(f"{'TOTAL':<8} {total_w:>6} {total_l:>6} {total_p:>6} {overall_hr:>10.3%} {total_w+total_l:>8}")
    log(f"Folds >= 54%: {above_54}/6")

log()
log("DONE. Check this file for all results.")
