"""Verify BigQuery connectivity and create datasets if they don't exist."""
from google.cloud import bigquery
import sys

PROJECT = "nfl-model-471509"
DATASETS = ["raw_nflfastr", "raw_lines", "curated"]

client = bigquery.Client(project=PROJECT)
print(f"Connected to project: {PROJECT}")

for ds_id in DATASETS:
    full_id = f"{PROJECT}.{ds_id}"
    try:
        ds = client.get_dataset(full_id)
        print(f"  Dataset {ds_id}: EXISTS")
    except Exception:
        ds_ref = bigquery.Dataset(full_id)
        ds_ref.location = "US"
        client.create_dataset(ds_ref, exists_ok=True)
        print(f"  Dataset {ds_id}: CREATED")

print("GCP setup complete.")
