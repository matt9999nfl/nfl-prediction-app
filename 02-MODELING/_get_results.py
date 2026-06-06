"""Get final results for all three experiments and per-fold breakdown for test3."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from google.cloud import bigquery

PROJECT = "nfl-model-471509"
client = bigquery.Client(project=PROJECT)

# Get column names from backtest_runs
schema_sql = """
SELECT column_name
FROM `nfl-model-471509`.`experiments`.INFORMATION_SCHEMA.COLUMNS
WHERE table_name = 'backtest_runs'
ORDER BY ordinal_position
"""
schema_rows = list(client.query(schema_sql).result())
print("backtest_runs columns:")
cols = [r["column_name"] for r in schema_rows]
print(cols)
print()

# Run IDs from the experiment run
A2_RUN_ID    = "20260517_020202_0504ff"
A3_RUN_ID    = "20260517_020425_38cf03"
TEST3_RUN_ID = "20260517_020637_245bc9"

# Get summary for each run
for label, run_id in [("A2 (23-feature faithfulness)", A2_RUN_ID),
                       ("A3 (shuffle-labels)", A3_RUN_ID),
                       ("test3 (rush features)", TEST3_RUN_ID)]:
    sql = f"""
    SELECT *
    FROM `{PROJECT}.experiments.backtest_runs`
    WHERE run_id = '{run_id}'
    LIMIT 1
    """
    rows = list(client.query(sql).result())
    if rows:
        r = dict(rows[0])
        print(f"{label} ({run_id}):")
        for k, v in r.items():
            if k not in ("feature_importances", "notes"):
                print(f"  {k}: {v}")
        print()
    else:
        print(f"{label}: No row found for run_id={run_id}")
        print()

# Per-fold breakdown for test3
print("=" * 60)
print("A1: Per-fold breakdown for test3")
print("=" * 60)

fold_sql = f"""
SELECT season,
  COUNTIF(correct = 1) AS wins,
  COUNTIF(correct = 0) AS losses,
  COUNTIF(correct IS NULL) AS pushes,
  SAFE_DIVIDE(COUNTIF(correct=1), COUNTIF(correct IS NOT NULL)) AS hit_rate,
  COUNTIF(correct IS NOT NULL) AS n_games
FROM `{PROJECT}.experiments.backtest_predictions`
WHERE run_id = '{TEST3_RUN_ID}'
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
    print(f"{r['season']:<8} {w:>6} {l:>6} {p:>6} {hr:>10.3%} {n:>8}")

overall_hr = total_w / (total_w + total_l) if (total_w + total_l) > 0 else 0
print(f"{'TOTAL':<8} {total_w:>6} {total_l:>6} {total_p:>6} {overall_hr:>10.3%} {total_w+total_l:>8}")
print(f"\nFolds >= 54%: {above_54}/6")
print(f"Folds >= 52%: {sum(1 for r in fold_rows if r['hit_rate'] and float(r['hit_rate']) >= 0.52)}/6")

# Also get per-fold for A2
print()
print("=" * 60)
print("Per-fold breakdown for A2 (faithfulness check)")
print("=" * 60)
fold_sql2 = f"""
SELECT season,
  COUNTIF(correct = 1) AS wins,
  COUNTIF(correct = 0) AS losses,
  COUNTIF(correct IS NULL) AS pushes,
  SAFE_DIVIDE(COUNTIF(correct=1), COUNTIF(correct IS NOT NULL)) AS hit_rate,
  COUNTIF(correct IS NOT NULL) AS n_games
FROM `{PROJECT}.experiments.backtest_predictions`
WHERE run_id = '{A2_RUN_ID}'
GROUP BY season ORDER BY season
"""
fold_rows2 = list(client.query(fold_sql2).result())
print(f"{'Season':<8} {'W':>6} {'L':>6} {'P':>6} {'Hit Rate':>10} {'N':>8}")
print("-" * 48)
tw2 = tl2 = 0
for r in fold_rows2:
    w = int(r["wins"]); l = int(r["losses"]); p = int(r["pushes"])
    hr = float(r["hit_rate"]) if r["hit_rate"] is not None else 0.0
    tw2 += w; tl2 += l
    print(f"{r['season']:<8} {w:>6} {l:>6} {p:>6} {hr:>10.3%}")
ohr2 = tw2 / (tw2 + tl2) if (tw2 + tl2) > 0 else 0
print(f"{'TOTAL':<8} {tw2:>6} {tl2:>6} {'':>6} {ohr2:>10.3%} {tw2+tl2:>8}")
