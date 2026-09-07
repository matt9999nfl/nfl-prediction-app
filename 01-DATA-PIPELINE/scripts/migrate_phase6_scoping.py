"""
Phase 6 Schema Migration — Hypothesis Chat
==========================================
Creates two new tables in the existing `platform` dataset:

    platform.scoping_sessions   one row per hypothesis-scoping conversation
    platform.capability_gaps    one row per thing the platform could not express

Work order:  00-PROJECT-LEAD/HYPOTHESIS-CHAT-BUILD-PLAN.md  (Stage 1)
Decision:    docs/DECISIONS.md ADR-012
Project:     nfl-model-471509

Usage:
    python scripts/migrate_phase6_scoping.py

Safe to re-run — table creation uses exists_ok=True and nothing is dropped,
altered, or backfilled.  This migration ADDS ONLY.  It must not touch any
existing table; the validation step at the end asserts that both new tables
exist and reports the schema it found, so a re-run is self-checking.

`config` and `slot_answers` are JSON on purpose.  Their shape is owned by
ExperimentCreateRequest and by app/scoping/scoping_tree.json respectively.
Flattening them into columns would create a second definition of a schema that
already has one, and the two would drift.
"""

import logging
import sys

sys.path.insert(0, ".")

from google.cloud import bigquery

from scripts.bq_utils import PROJECT, ensure_datasets, get_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

SCOPING_SESSIONS_SCHEMA = [
    bigquery.SchemaField("session_id",      "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("hypothesis_text", "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("slot_answers",    "JSON",      mode="NULLABLE"),
    bigquery.SchemaField("config",          "JSON",      mode="NULLABLE"),
    bigquery.SchemaField("config_hash",     "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("approved_hash",   "STRING",    mode="NULLABLE"),
    # scoping | assembled | approved | dispatched | abandoned
    bigquery.SchemaField("status",          "STRING",    mode="REQUIRED"),
    # FK → platform.experiment_configs.experiment_id (STRING, REQUIRED there).
    # Nullable here because it does not exist until dispatch.
    bigquery.SchemaField("experiment_id",   "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("created_at",      "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("updated_at",      "TIMESTAMP", mode="REQUIRED"),
]

CAPABILITY_GAPS_SCHEMA = [
    bigquery.SchemaField("gap_id",              "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("session_id",          "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("requested_concept",   "STRING",    mode="REQUIRED"),
    # which surface is missing it: feature_catalog | filter_schema | target
    bigquery.SchemaField("why_unavailable",     "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("nearest_expressible", "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("suggested_definition","STRING",    mode="NULLABLE"),
    # open | planned | built | declined
    bigquery.SchemaField("status",              "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("created_at",          "TIMESTAMP", mode="REQUIRED"),
]

NEW_TABLES = {
    "scoping_sessions": (SCOPING_SESSIONS_SCHEMA, ["status"]),
    "capability_gaps":  (CAPABILITY_GAPS_SCHEMA,  ["status"]),
}


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

def create_scoping_tables(client: bigquery.Client) -> None:
    for name, (schema, clustering) in NEW_TABLES.items():
        full_ref = f"{PROJECT}.platform.{name}"
        table = bigquery.Table(full_ref, schema=schema)
        if clustering:
            table.clustering_fields = clustering
        client.create_table(table, exists_ok=True)
        logger.info(f"Table ready: {full_ref} (clustered by {', '.join(clustering)})")


def validate(client: bigquery.Client) -> bool:
    """Assert both tables exist with the expected columns.  Returns all_passed."""
    all_passed = True
    for name, (schema, _) in NEW_TABLES.items():
        full_ref = f"{PROJECT}.platform.{name}"
        try:
            table = client.get_table(full_ref)
        except Exception as exc:
            logger.error(f"FAIL: {full_ref} not found ({exc})")
            all_passed = False
            continue

        found = {f.name: f for f in table.schema}
        expected = {f.name: f for f in schema}

        missing = sorted(set(expected) - set(found))
        extra = sorted(set(found) - set(expected))
        if missing:
            logger.error(f"FAIL: {full_ref} missing column(s): {missing}")
            all_passed = False
        if extra:
            logger.warning(f"NOTE: {full_ref} has extra column(s): {extra}")

        for col in sorted(set(expected) & set(found)):
            if found[col].field_type != expected[col].field_type:
                logger.error(
                    f"FAIL: {full_ref}.{col} type is {found[col].field_type}, "
                    f"expected {expected[col].field_type}"
                )
                all_passed = False

        if all_passed:
            logger.info(f"PASS: {full_ref} — {len(found)} columns as expected")

    # The FK type must match platform.experiment_configs.experiment_id.
    try:
        cfg = client.get_table(f"{PROJECT}.platform.experiment_configs")
        cfg_type = next(f.field_type for f in cfg.schema if f.name == "experiment_id")
        ses = client.get_table(f"{PROJECT}.platform.scoping_sessions")
        ses_type = next(f.field_type for f in ses.schema if f.name == "experiment_id")
        if cfg_type != ses_type:
            logger.error(
                f"FAIL: experiment_id type mismatch — experiment_configs={cfg_type}, "
                f"scoping_sessions={ses_type}"
            )
            all_passed = False
        else:
            logger.info(f"PASS: experiment_id type matches experiment_configs ({cfg_type})")
    except Exception as exc:
        logger.error(f"FAIL: could not compare experiment_id types ({exc})")
        all_passed = False

    return all_passed


def main() -> None:
    client = get_client()

    logger.info("Step 1/3 — Ensuring `platform` dataset exists")
    ensure_datasets(client, ["platform"])

    logger.info("Step 2/3 — Creating Phase 6 scoping tables")
    create_scoping_tables(client)

    logger.info("Step 3/3 — Validating")
    if not validate(client):
        sys.exit(1)

    logger.info("Phase 6 scoping migration complete.")


if __name__ == "__main__":
    main()
