"""
Step 1: Verify labels are clean and find experiment config IDs.
Results written to _step1_results.txt
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

OUTPUT_FILE = ROOT / "_step1_results.txt"
lines = []

def log(msg=""):
    print(msg)
    lines.append(str(msg))

from google.cloud import bigquery

PROJECT = "nfl-model-471509"
client = bigquery.Client(project=PROJECT)

log("=" * 60)
log("STEP 1 — Spread-bin diagnostic (label verification)")
log("=" * 60)

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
log(f"{'Bucket':<20} {'Cover %':>10} {'N':>8}")
log("-" * 42)
all_clean = True
for r in rows:
    pct = float(r["cover_pct"])
    n   = int(r["n"])
    flag = "" if 45.0 <= pct <= 55.0 else "  *** OUTSIDE RANGE ***"
    if flag:
        all_clean = False
    log(f"{r['bucket']:<20} {pct:>10.1f} {n:>8}{flag}")

log()
if all_clean:
    log("LABELS CLEAN: All buckets within 45-55%. Proceeding.")
else:
    log("CRITICAL: Labels still bad! Stop immediately.")

log()
log("=" * 60)
log("STEP 2 — All experiment configs (most recent 20)")
log("=" * 60)

config_sql = """
SELECT experiment_id, name, status, updated_at
FROM `nfl-model-471509.platform.experiment_configs`
ORDER BY updated_at DESC
LIMIT 20
"""
config_rows = list(client.query(config_sql).result())
log(f"{'ID':<40} {'Name':<50} {'Status'}")
log("-" * 105)
for r in config_rows:
    log(f"{r['experiment_id']:<40} {r['name']:<50} {r['status']}")

log()

# Find test3 config
test3_config_id = None
a2_found = False
a3_found = False

for r in config_rows:
    name = r["name"].lower()
    eid  = r["experiment_id"]
    if eid == "6ec7deac-3c62-4954-a8d4-a7bfb21b410f":
        a2_found = True
        log(f"A2 config confirmed: {r['name']}")
    if eid == "decaa551-b991-43af-9a71-ab70b9580af7":
        a3_found = True
        log(f"A3 config confirmed: {r['name']}")
    if ("test3" in name or ("rush" in name and "shuffle" not in name and "faithful" not in name)):
        if test3_config_id is None:
            test3_config_id = eid
            log(f"test3 candidate: {r['name']} ({eid})")

log()
log(f"A2_CONFIG_ID = 6ec7deac-3c62-4954-a8d4-a7bfb21b410f  (found={a2_found})")
log(f"A3_CONFIG_ID = decaa551-b991-43af-9a71-ab70b9580af7  (found={a3_found})")
log(f"TEST3_CONFIG_ID = {test3_config_id}")
log()
log(f"LABELS_CLEAN = {all_clean}")

# Write results
OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")
print(f"\nResults written to {OUTPUT_FILE}")
