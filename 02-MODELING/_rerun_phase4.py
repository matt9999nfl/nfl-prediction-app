"""
Phase 4 Re-run Script — post INC-001 fix.

Steps:
1. Verify labels are clean (spread-bin diagnostic)
2. Find experiment config IDs for A2 (52-feature faithfulness), A3 (shuffle-labels), test3
3. Re-run A2, A3, test3 sequentially via run_experiment.py main()
4. Query per-fold results for the new test3 run_id
5. Print all results for updating RUSH_VALIDATION_PLAN.md and PHASE4_STATUS.md

Run from 02-MODELING/:
    python _rerun_phase4.py
"""

import json
import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from google.cloud import bigquery

PROJECT = "nfl-model-471509"

# Known config IDs from _insert_configs.py (previous session)
A2_CONFIG_ID   = "6ec7deac-3c62-4954-a8d4-a7bfb21b410f"  # v2-23base-faithfulness-check (23 features)
A3_CONFIG_ID   = "decaa551-b991-43af-9a71-ab70b9580af7"  # test3-shuffle-labels-leakage-test

client = bigquery.Client(project=PROJECT)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Verify label fix
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 60)
print("STEP 1 — Spread-bin diagnostic (label verification)")
print("=" * 60)

label_check_sql = """
SELECT
  CASE
    WHEN home_spread_close <= -10 THEN 'home_fav_10+'
    WHEN home_spread_close <= -3  THEN 'home_fav_3-10'
    WHEN home_spread_close <  3   THEN 'pick_em'
    WHEN home_spread_close <  10  THEN 'home_dog_3-10'
    ELSE                               'home_dog_10+'
  END AS bucket,
  ROUND(100 * COUNTIF(home_covered) / COUNT(*), 1) AS cover_pct,
  COUNT(*) AS n
FROM `nfl-model-471509.curated.games`
WHERE season BETWEEN 2015 AND 2025
  AND home_covered IS NOT NULL
GROUP BY bucket
ORDER BY bucket
"""

rows = list(client.query(label_check_sql).result())
print(f"{'Bucket':<20} {'Cover %':>10} {'N':>8}")
print("-" * 42)
all_clean = True
for r in rows:
    pct = float(r["cover_pct"])
    n   = int(r["n"])
    flag = "" if 45.0 <= pct <= 55.0 else "  *** OUTSIDE RANGE ***"
    if flag:
        all_clean = False
    print(f"{r['bucket']:<20} {pct:>10.1f} {n:>8}{flag}")

print()
if not all_clean:
    print("CRITICAL: One or more buckets outside 45–55%. Labels are still bad.")
    print("Stopping — do not run any experiments. Report to PROJECT-LEAD.")
    sys.exit(1)

print("All buckets within 45–55%. Labels are CLEAN. Proceeding.")
print()

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Find all relevant experiment configs
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 60)
print("STEP 2 — Locate experiment configs")
print("=" * 60)

config_sql = """
SELECT experiment_id, name, status, updated_at
FROM `nfl-model-471509.platform.experiment_configs`
ORDER BY updated_at DESC
LIMIT 20
"""
config_rows = list(client.query(config_sql).result())
print(f"{'ID':<40} {'Name':<45} {'Status'}")
print("-" * 100)
for r in config_rows:
    print(f"{r['experiment_id']:<40} {r['name']:<45} {r['status']}")

print()

# Find test3 config — look for rush features config (not shuffle, not faithfulness)
test3_config_id = None
for r in config_rows:
    name = r["name"].lower()
    # test3 should be rush-only without shuffle
    if ("test3" in name or "rush" in name) and "shuffle" not in name and "faithful" not in name and "52" not in name and "23base" not in name and "v2-52" not in name:
        test3_config_id = r["experiment_id"]
        print(f"Found test3 candidate: {r['name']} ({r['experiment_id']})")
        break

if test3_config_id is None:
    # Try a broader search
    for r in config_rows:
        name = r["name"].lower()
        if "test3" in name:
            test3_config_id = r["experiment_id"]
            print(f"Found test3 by name: {r['name']} ({r['experiment_id']})")
            break

if test3_config_id is None:
    # Query more specifically
    test3_sql = """
    SELECT experiment_id, name, status, updated_at, methodology
    FROM `nfl-model-471509.platform.experiment_configs`
    WHERE name LIKE '%test3%' OR name LIKE '%rush%'
    ORDER BY updated_at DESC
    LIMIT 10
    """
    test3_rows = list(client.query(test3_sql).result())
    for r in test3_rows:
        print(f"Candidate: {r['name']} ({r['experiment_id']})")
        if "shuffle" not in r["name"].lower():
            test3_config_id = r["experiment_id"]
            break

print()
if test3_config_id:
    print(f"Test3 config ID: {test3_config_id}")
else:
    print("WARNING: Could not find test3 config. Will need to create it or search manually.")

print(f"A2 config ID:    {A2_CONFIG_ID}")
print(f"A3 config ID:    {A3_CONFIG_ID}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Run experiments in order: A2, A3, then test3
# ─────────────────────────────────────────────────────────────────────────────

def run_experiment(config_id: str, label: str) -> str | None:
    """
    Run run_experiment.py with the given config ID.
    Returns the run_id if successful, None if failed.
    """
    print(f"\n{'=' * 60}")
    print(f"Running {label} (config_id={config_id})")
    print(f"{'=' * 60}")

    env = os.environ.copy()
    env["EXPERIMENT_CONFIG_ID"] = config_id

    result = subprocess.run(
        [sys.executable, str(ROOT / "backtests" / "run_experiment.py")],
        env=env,
        capture_output=False,  # Let output stream to terminal
        cwd=str(ROOT),
    )

    if result.returncode != 0:
        print(f"\nERROR: {label} failed with return code {result.returncode}")
        return None

    # Find the latest run for this config
    latest_sql = f"""
    SELECT latest_run_id
    FROM `{PROJECT}.platform.experiment_configs`
    WHERE experiment_id = '{config_id}'
    LIMIT 1
    """
    rows = list(client.query(latest_sql).result())
    if rows:
        run_id = rows[0]["latest_run_id"]
        print(f"\n{label} complete. Run ID: {run_id}")
        return run_id
    return None


# Run A2 — 52/23-feature faithfulness check
a2_run_id = run_experiment(A2_CONFIG_ID, "A2 — 23-feature faithfulness check")

# Run A3 — shuffled-label leakage test
a3_run_id = run_experiment(A3_CONFIG_ID, "A3 — shuffled-label leakage test")

# Run test3 — rush features experiment
test3_run_id = None
if test3_config_id:
    test3_run_id = run_experiment(test3_config_id, "test3 — rush features")
else:
    print("\nSkipping test3 run — config ID not found.")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Query per-fold breakdown for test3
# ─────────────────────────────────────────────────────────────────────────────

print(f"\n{'=' * 60}")
print("STEP 4 — Per-fold breakdown for test3")
print("=" * 60)

if test3_run_id:
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
    print(f"{'Season':<8} {'W':>6} {'L':>6} {'P':>6} {'Hit Rate':>10} {'N':>8}")
    print("-" * 48)
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
        print(f"{r['season']:<8} {w:>6} {l:>6} {p:>6} {hr:>10.1%} {n:>8}")
    overall_hr = total_w / (total_w + total_l) if (total_w + total_l) > 0 else 0
    print(f"{'TOTAL':<8} {total_w:>6} {total_l:>6} {total_p:>6} {overall_hr:>10.1%} {total_w+total_l:>8}")
    print(f"\nFolds above 54%: {above_54}/6")
else:
    print("No test3 run_id available. Skipping per-fold query.")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — Summary of all results
# ─────────────────────────────────────────────────────────────────────────────

print(f"\n{'=' * 60}")
print("STEP 5 — Summary of all run results")
print("=" * 60)

def get_run_summary(run_id: str, label: str):
    if not run_id:
        print(f"{label}: No run ID")
        return
    sql = f"""
    SELECT overall_hit_rate, total_wins, total_losses, total_pushes, n_games, gate_passed, notes
    FROM `{PROJECT}.experiments.backtest_runs`
    WHERE run_id = '{run_id}'
    LIMIT 1
    """
    rows = list(client.query(sql).result())
    if rows:
        r = rows[0]
        hr = float(r["overall_hit_rate"]) if r["overall_hit_rate"] is not None else None
        print(f"{label}:")
        print(f"  Run ID:    {run_id}")
        print(f"  ATS:       {r['total_wins']}-{r['total_losses']}-{r['total_pushes']} ({r['n_games']} games)")
        print(f"  Hit rate:  {hr:.3%}" if hr is not None else "  Hit rate:  N/A")
        print(f"  Gate:      {'PASSED' if r['gate_passed'] else 'NOT MET'}")
        notes = r.get("notes", "") or ""
        if notes:
            print(f"  Notes:     {notes[:100]}")
    else:
        print(f"{label}: No result row found for run_id={run_id}")
    print()

get_run_summary(a2_run_id, "A2 — Faithfulness check")
get_run_summary(a3_run_id, "A3 — Shuffled-label leakage test")
get_run_summary(test3_run_id, "test3 — Rush features")

print("Done.")
