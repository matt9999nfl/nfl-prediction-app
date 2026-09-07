-- Phase 6 Stage 1 — Hypothesis Chat scoping tables
-- DERIVED from 01-DATA-PIPELINE/scripts/migrate_phase6_scoping.py (NEW_TABLES).
-- Run in the BigQuery console when gcloud credentials are not available.
-- Additive only: creates two new tables, alters and drops nothing.

CREATE TABLE IF NOT EXISTS `nfl-model-471509.platform.scoping_sessions` (
  session_id STRING NOT NULL,
  hypothesis_text STRING NOT NULL,
  slot_answers JSON,
  config JSON,
  config_hash STRING,
  approved_hash STRING,
  status STRING NOT NULL,
  experiment_id STRING,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
)
CLUSTER BY status;

CREATE TABLE IF NOT EXISTS `nfl-model-471509.platform.capability_gaps` (
  gap_id STRING NOT NULL,
  session_id STRING,
  requested_concept STRING NOT NULL,
  why_unavailable STRING NOT NULL,
  nearest_expressible STRING,
  suggested_definition STRING,
  status STRING NOT NULL,
  created_at TIMESTAMP NOT NULL
)
CLUSTER BY status;
