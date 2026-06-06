"""
Insert A2 and A3 experiment configs into platform.experiment_configs using
load_table_from_dataframe for immediate DML consistency.
"""
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from features.ol_metrics import ALL_TEAM_RATE_FEATURES
from features.comprehensive import ALL_ADDITIONAL_TEAM_FEATURES
from features.situational import SITUATIONAL_TEAM_FEATURES

PROJECT = "nfl-model-471509"
TABLE   = f"{PROJECT}.platform.experiment_configs"

client  = bigquery.Client(project=PROJECT)

now = datetime.now(timezone.utc)

all_base = ALL_TEAM_RATE_FEATURES + ALL_ADDITIONAL_TEAM_FEATURES + SITUATIONAL_TEAM_FEATURES
features_a2 = [{"dataset": "curated", "column": c, "semantic_name": c} for c in all_base]

test3_base = [
    "ol_rush_epa_per_att",
    "ol_rush_yards_per_att",
    "rush_explosive_rate",
    "def_rush_epa_allowed_per_att",
    "def_explosive_rush_allowed_rate",
]
features_a3 = [{"dataset": "curated", "column": c, "semantic_name": c} for c in test3_base]

A2_ID = "6ec7deac-3c62-4954-a8d4-a7bfb21b410f"
A3_ID = "decaa551-b991-43af-9a71-ab70b9580af7"

configs = [
    {
        "experiment_id": A2_ID,
        "name": "v2-23base-faithfulness-check",
        "description": "Reproduce v2 result via config-driven runner. Phase 4 A2 runner faithfulness check.",
        "created_at": now,
        "updated_at": now,
        "target": "home_covered",
        "features": json.dumps(features_a2),
        "evaluation": json.dumps({
            "success_threshold": 0.54, "min_sample": 250, "metric": "ats_hit_rate",
        }),
        "methodology": json.dumps({
            "start_season": 2016, "end_season": 2025,
            "train_seasons": 4, "test_seasons": 1,
            "random_seed": 42, "shuffle_labels": False,
        }),
        "model": json.dumps({"type": "xgboost"}),
        "status": "pending",
        "gate_passed": False,
        "run_count": 0,
    },
    {
        "experiment_id": A3_ID,
        "name": "test3-shuffle-labels-leakage-test",
        "description": "test3 rush features with shuffle_labels=True. Phase 4 A3 leakage detection. [SHUFFLE_LABELS=True]",
        "created_at": now,
        "updated_at": now,
        "target": "home_covered",
        "features": json.dumps(features_a3),
        "evaluation": json.dumps({
            "success_threshold": 0.54, "min_sample": 250, "metric": "ats_hit_rate",
        }),
        "methodology": json.dumps({
            "start_season": 2016, "end_season": 2025,
            "train_seasons": 4, "test_seasons": 1,
            "random_seed": 42, "shuffle_labels": True,
        }),
        "model": json.dumps({"type": "xgboost"}),
        "status": "pending",
        "gate_passed": False,
        "run_count": 0,
    },
]

df = pd.DataFrame(configs)

schema = [
    bigquery.SchemaField("experiment_id", "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("name",          "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("description",   "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("created_at",    "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("updated_at",    "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("target",        "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("features",      "JSON",      mode="REQUIRED"),
    bigquery.SchemaField("evaluation",    "JSON",      mode="REQUIRED"),
    bigquery.SchemaField("methodology",   "JSON",      mode="REQUIRED"),
    bigquery.SchemaField("model",         "JSON",      mode="REQUIRED"),
    bigquery.SchemaField("status",        "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("gate_passed",   "BOOLEAN",   mode="NULLABLE"),
    bigquery.SchemaField("run_count",     "INTEGER",   mode="REQUIRED"),
]

job_config = bigquery.LoadJobConfig(
    schema=schema,
    write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
)

job = client.load_table_from_dataframe(df, TABLE, job_config=job_config)
job.result()
print(f"Inserted {len(configs)} rows into {TABLE}")
print(f"A2 ID: {A2_ID}")
print(f"A3 ID: {A3_ID}")

# Verify
rows = list(client.query(f"SELECT experiment_id, name, status FROM `{TABLE}` WHERE experiment_id IN ('{A2_ID}', '{A3_ID}')").result())
print(f"Verification ({len(rows)} rows found):")
for r in rows:
    print(dict(r))
