# DATA-PIPELINE Schema Migration — Phase 2

**Owner:** PROJECT-LEAD
**Assigned to:** DATA-PIPELINE
**Date:** 2026-05-03
**Status:** ✅ Complete — 2026-05-04 (58/58 checks passed; BACKEND-API and MODELING unblocked)

---

## Purpose

Create the new BigQuery tables that support the platform's dataset registry, experiment configuration, and framework storage. These tables do not exist yet. Nothing else can be built until they do.

No existing tables are modified. This is additive only.

---

## New BigQuery Datasets

Create the following datasets in project `nfl-model-471509` if they do not already exist:

| Dataset | Purpose |
|---------|---------|
| `platform` | Registry tables for datasets, columns, experiment configs, frameworks |
| `user_datasets` | One table per uploaded user dataset (tables created at upload time by BACKEND-API — DATA-PIPELINE creates the dataset container only) |

The `experiments` dataset already exists. Two columns need to be added to `experiments.backtest_runs` (see below).

---

## Tables to Create

### `platform.datasets`

Registry of all user-uploaded datasets.

| Column | Type | Mode | Notes |
|--------|------|------|-------|
| `dataset_id` | STRING | REQUIRED | UUID, primary key |
| `name` | STRING | REQUIRED | Human-readable name |
| `description` | STRING | NULLABLE | What this dataset contains |
| `upload_date` | TIMESTAMP | REQUIRED | When file was received |
| `file_path` | STRING | NULLABLE | Cloud Storage URI of raw uploaded file |
| `join_key_type` | STRING | NULLABLE | `game_id` \| `player_season_week` \| `team_season_week` |
| `row_count` | INT64 | NULLABLE | Set after load completes |
| `column_count` | INT64 | NULLABLE | Set after load completes |
| `license_tag` | STRING | NULLABLE | `open` \| `licensed_commercial` \| `personal_use_only` |
| `status` | STRING | REQUIRED | `uploading` \| `mapping` \| `ready` \| `error` |
| `schema_source` | STRING | NULLABLE | `form` \| `ai_assisted` |
| `error_message` | STRING | NULLABLE | Populated if status = `error` |
| `created_at` | TIMESTAMP | REQUIRED | |
| `updated_at` | TIMESTAMP | REQUIRED | |

Partitioned by `DATE(upload_date)`. No clustering needed at this scale.

---

### `platform.dataset_columns`

One row per column per dataset. Stores the semantic mapping that makes columns usable in the experiment builder.

| Column | Type | Mode | Notes |
|--------|------|------|-------|
| `dataset_id` | STRING | REQUIRED | FK → platform.datasets |
| `column_name` | STRING | REQUIRED | Raw column name from uploaded file |
| `semantic_name` | STRING | NULLABLE | Feature name for experiment builder (e.g. `receiver_separation_avg`) |
| `description` | STRING | NULLABLE | What this column measures |
| `data_type` | STRING | NULLABLE | `numeric` \| `categorical` \| `boolean` |
| `is_join_key` | BOOL | REQUIRED | True if this column is part of the join key |
| `join_key_role` | STRING | NULLABLE | `game_id` \| `player_id` \| `team` \| `season` \| `week` — which part of the join key |
| `null_rate` | FLOAT64 | NULLABLE | Fraction of null values, computed at load time |
| `sample_values` | STRING | NULLABLE | JSON array of up to 5 sample values (for display in UI) |
| `created_at` | TIMESTAMP | REQUIRED | |
| `updated_at` | TIMESTAMP | REQUIRED | |

Clustered by `dataset_id`.

---

### `platform.experiment_configs`

One row per saved experiment configuration. This is the config the Experiment Runner reads to know what to build and run.

| Column | Type | Mode | Notes |
|--------|------|------|-------|
| `experiment_id` | STRING | REQUIRED | UUID, primary key |
| `name` | STRING | REQUIRED | |
| `description` | STRING | NULLABLE | |
| `created_at` | TIMESTAMP | REQUIRED | |
| `updated_at` | TIMESTAMP | REQUIRED | |
| `target` | STRING | REQUIRED | `ats_cover` \| `outright_winner` \| `total_over` \| `team_total_yards` |
| `features` | JSON | REQUIRED | Array of `{dataset, column, semantic_name}` objects |
| `evaluation` | JSON | REQUIRED | `{metric, success_threshold, min_sample}` |
| `methodology` | JSON | REQUIRED | `{type, train_seasons, test_seasons, start_season, end_season}` |
| `model` | JSON | REQUIRED | `{type, hyperparams}` |
| `status` | STRING | REQUIRED | `draft` \| `running` \| `complete` \| `failed` |
| `gate_passed` | BOOL | NULLABLE | Set by Experiment Runner on completion |
| `latest_run_id` | STRING | NULLABLE | FK → experiments.backtest_runs.experiment_id |
| `run_count` | INT64 | REQUIRED | Default 0, incremented on each run |

No partitioning needed. Clustered by `status`.

---

### `platform.frameworks`

Named, saveable experiment configs for reuse and iteration.

| Column | Type | Mode | Notes |
|--------|------|------|-------|
| `framework_id` | STRING | REQUIRED | UUID, primary key |
| `name` | STRING | REQUIRED | |
| `description` | STRING | NULLABLE | |
| `created_at` | TIMESTAMP | REQUIRED | |
| `updated_at` | TIMESTAMP | REQUIRED | |
| `base_experiment_id` | STRING | NULLABLE | FK → platform.experiment_configs — the experiment this was saved from |
| `config_snapshot` | JSON | REQUIRED | Full ExperimentConfig JSON at time of save |

No partitioning needed.

---

## Existing Table — `experiments.backtest_runs` (add columns)

Two columns need to be added to the existing table. Use `ALTER TABLE ... ADD COLUMN` in BigQuery.

| Column to add | Type | Mode | Notes |
|---------------|------|------|-------|
| `experiment_config_id` | STRING | NULLABLE | FK → platform.experiment_configs.experiment_id. Null for runs created before Phase 2 (ol_xgb_v1, ol_xgb_v2). |
| `success_criteria` | JSON | NULLABLE | Snapshot of evaluation criteria at time of run: `{metric, success_threshold, min_sample}`. Null for pre-Phase 2 runs. |

Existing rows are not backfilled. Nulls are acceptable for historical runs.

---

## Validation Checklist

Run these checks after creating all tables. Do not hand off until all pass.

- [x] `platform` dataset exists in `nfl-model-471509`
- [x] `user_datasets` dataset exists in `nfl-model-471509`
- [x] `platform.datasets` table exists with all columns and correct types
- [x] `platform.dataset_columns` table exists with all columns and correct types
- [x] `platform.experiment_configs` table exists with all columns and correct types
- [x] `platform.frameworks` table exists with all columns and correct types
- [x] `experiments.backtest_runs` has `experiment_config_id` and `success_criteria` columns
- [x] All JSON columns accept valid JSON (INSERT + `JSON_VALUE` extraction confirmed)
- [x] `user_datasets` dataset is empty (no tables yet — that's correct, tables are created at upload time)

**Completed 2026-05-04. 58/58 checks passed. BACKEND-API and MODELING are unblocked.**

---

## Out of Scope

- Populating any of these tables (BACKEND-API handles writes)
- Creating individual `user_datasets.{id}` tables (created dynamically at upload time)
- Any changes to `raw_nflfastr.*` or `curated.*` tables
