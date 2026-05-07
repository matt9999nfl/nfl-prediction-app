# Architecture

**Owner:** PROJECT-LEAD
**Status:** v0.2 — updated for platform vision
**Last updated:** 2026-05-04

---

## What This System Is

A self-service NFL prediction experimentation platform. You upload a dataset, configure an experiment (features, target, evaluation criteria), run it, and see results — all through the dashboard. No code written per experiment.

The platform has two modes that coexist:
- **Exploration:** upload new data, define new experiments, iterate on models
- **Production:** experiments that have cleared their own success criteria surface predictions for upcoming games

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Data Sources                                │
│   nflfastR/nflverse (scheduled)  •  User uploads (on-demand)        │
└────────────────────────┬──────────────────────┬─────────────────────┘
                         │                      │
                         ▼                      ▼
              ┌──────────────────┐   ┌──────────────────────┐
              │  DATA-PIPELINE   │   │  Dataset Registry    │
              │  nflfastR ingest │   │  Upload → BQ         │
              │  Scheduled jobs  │   │  Schema mapping      │
              └────────┬─────────┘   └──────────┬───────────┘
                       │                        │
                       ▼                        ▼
            ┌──────────────────────────────────────────┐
            │  BigQuery                                │
            │  raw_nflfastr.*   curated.*              │
            │  user_datasets.*  platform.datasets      │
            │  platform.dataset_columns                │
            └───────────────────┬──────────────────────┘
                                │
                                ▼
                  ┌─────────────────────────┐
                  │  Feature Store          │
                  │  curated.* + joined     │
                  │  user dataset columns   │
                  └─────────────┬───────────┘
                                │
                                ▼
                  ┌─────────────────────────┐
                  │  Experiment Runner      │
                  │  Cloud Run Job          │
                  │  Config-driven          │
                  │  Walk-forward harness   │
                  └─────────────┬───────────┘
                                │
                                ▼
                  ┌─────────────────────────┐
                  │  BigQuery               │
                  │  experiments.*          │
                  │  platform.frameworks    │
                  └─────────────┬───────────┘
                                │
                                ▼
                  ┌─────────────────────────┐
                  │  BACKEND-API            │
                  │  FastAPI / Cloud Run    │
                  │  Read + Write           │
                  └─────────────┬───────────┘
                                │
                                ▼
                  ┌─────────────────────────┐
                  │  FRONTEND               │
                  │  Dashboard              │
                  │  Upload • Configure     │
                  │  Run • View • Save      │
                  └─────────────────────────┘

Future:
  Claude API ←→ BACKEND-API  (dataset schema inference, data cleaning)
  DEVOPS ── deploys, schedules, monitors all of the above
  TESTING-QA ── verifies seams between layers
```

---

## Component Boundaries

| Layer | Reads from | Writes to | Triggered by |
|-------|------------|-----------|--------------|
| DATA-PIPELINE | External sources | `raw_nflfastr.*`, `curated.*` | Cloud Scheduler (weekly) |
| Dataset Registry | File upload (Cloud Storage) | `user_datasets.*`, `platform.datasets`, `platform.dataset_columns` | API (on user upload) |
| Feature Store | `curated.*`, `user_datasets.*` | — | Experiment Runner at job time |
| Experiment Runner | Feature Store, `platform.experiment_configs` | `experiments.backtest_runs`, `experiments.backtest_predictions` | API (on user trigger) |
| BACKEND-API | BigQuery (all read), File upload | `platform.*`, `experiments.*` (via jobs) | HTTPS |
| FRONTEND | BACKEND-API only | — | User |

No layer skips a level. The frontend never queries BigQuery directly. The API never runs scrapers. The pipeline never serves HTTP.

---

## BigQuery Dataset Structure

```
nfl-model-471509
│
├── raw_nflfastr
│   ├── pbp                     ← play-by-play, 2015–present
│   ├── schedules               ← game schedule + results + closing lines
│   └── rosters                 ← weekly rosters
│
├── curated
│   ├── games                   ← one row per REG season game
│   └── plays                   ← filtered play-by-play, key columns
│
├── user_datasets
│   └── {dataset_id}            ← one table per uploaded dataset, raw columns
│
├── platform
│   ├── datasets                ← dataset registry (metadata per upload)
│   ├── dataset_columns         ← column-level schema for each dataset
│   ├── experiment_configs      ← saved experiment definitions (JSON config)
│   └── frameworks              ← saved/named modeling frameworks
│
└── experiments
    ├── backtest_runs           ← one row per experiment run (metadata + metrics)
    └── backtest_predictions    ← one row per game per fold per run
```

---

## Dataset Registry

When a user uploads a new dataset, the following happens:

1. File (CSV/Excel/JSON) is uploaded via the API and written to Cloud Storage (`gs://nfl-model-471509-uploads/{dataset_id}/raw.*`)
2. A row is created in `platform.datasets` (metadata: name, description, upload date, join key type, license tag, status)
3. A Cloud Run Job parses the file, infers column types, and loads it into `user_datasets.{dataset_id}` in BigQuery
4. Columns are registered in `platform.dataset_columns` with their semantic mappings

**Schema mapping (Phase 1 — form-based):**
The user specifies through a form:
- What the join key is (game_id, or player_id + season + week, or team + season + week)
- What each column measures (free text description, used to name features in the experiment builder)
- License tag (open, licensed_commercial, personal_use_only)

**Schema mapping (Phase 2 — Claude API-assisted):**
When a dataset is uploaded, the API calls Claude with the column names and a sample of rows. Claude infers column meanings, suggests join key mappings, flags data quality issues, and proposes feature names. The user reviews and confirms. This replaces the manual form for most cases while keeping the form as a fallback.

The Claude API integration point is a single service call in the upload handler — it does not affect any other part of the architecture.

---

## Experiment Configuration

An experiment is a JSON config object. It is created through the dashboard, saved to `platform.experiment_configs`, and executed by the Experiment Runner.

```json
{
  "experiment_id": "uuid",
  "name": "receiver_separation_ats_v1",
  "created_at": "ISO 8601",
  "target": "ats_cover" | "outright_winner" | "total_over" | "team_total_yards",
  "features": [
    { "dataset": "curated", "column": "home_ol_pass_epa_per_att" },
    { "dataset": "user_datasets.abc123", "column": "home_receiver_separation_avg" }
  ],
  "evaluation": {
    "metric": "ats_hit_rate" | "accuracy" | "log_loss" | "rmse",
    "success_threshold": 0.54,
    "min_sample": 250
  },
  "methodology": {
    "type": "walk_forward",
    "train_seasons": 4,
    "test_seasons": 1,
    "start_season": 2015,
    "end_season": 2024
  },
  "model": {
    "type": "xgboost" | "logistic_regression" | "random_forest",
    "hyperparams": {}
  },
  "status": "draft" | "running" | "complete" | "failed",
  "gate_passed": null | true | false
}
```

**Target variables supported (Phase 2):**
- `ats_cover` — did the home team cover the closing spread? (binary)
- `outright_winner` — did the home team win? (binary)
- `total_over` — did the game go over the closing total? (binary)
- `team_total_yards` — team total offensive yards, over/under a threshold (binary or regression)

---

## Experiment Runner

The Experiment Runner is a Cloud Run Job (not a service — it starts, runs, and exits). It is triggered by the API when a user clicks "Run" in the dashboard.

**Inputs:** experiment config JSON from `platform.experiment_configs`
**Process:**
1. Reads config to determine features, target, methodology, and date range
2. Dynamically builds the feature matrix by joining `curated.*` and any `user_datasets.*` tables specified in the config
3. Executes the walk-forward or hold-out evaluation
4. Writes results to `experiments.backtest_runs` and `experiments.backtest_predictions`
5. Updates `platform.experiment_configs.status` and `gate_passed`

**Key constraint:** The runner is config-driven. No code is written per experiment. Adding a new dataset to an experiment is a config change, not a code change.

---

## Saved Frameworks

A framework is a named, saved experiment config that the user wants to reuse or iterate on. Stored in `platform.frameworks`.

Examples:
- "OL mismatch ATS baseline" — the ol_xgb_v2 config, saved as a starting point
- "Receiver separation test template" — a config pre-wired for receiver-side features, target = ats_cover
- "Full model v3" — the current best-performing config

Frameworks are editable in the dashboard. Editing a framework creates a new experiment (it does not overwrite the original run's results).

---

## Data Flow Cadence

**Scheduled (DATA-PIPELINE, weekly):**
- Tuesday 6am ET — nflfastR ingest (full season refresh)
- Tuesday 9am ET — Experiment Runner re-runs any "production" experiments (gate_passed = true) with updated data to generate current-week predictions
- Post-game (Sun/Mon/Thu) — nflfastR gameday refresh

**On-demand (user-triggered via dashboard):**
- Dataset upload → schema mapping → BigQuery load
- Experiment create → configure → run → view results
- Save framework → edit → re-run

---

## Claude API Integration ✅ Delivered in Phase 2

The Claude API is called in one place: the dataset upload handler (`POST /api/v1/datasets/{id}/infer-schema`). When a file is uploaded, the backend sends column names + sample rows to Claude and receives back:
- Inferred column descriptions
- Suggested join key (game_id, player+week+season, team+week+season)
- Data quality flags (nulls, outliers, encoding issues)
- Suggested feature names for the experiment builder

The user reviews Claude's suggestions in the dashboard before confirming. Nothing is auto-applied without review.

This is a single API call in the upload endpoint — it has no architectural dependencies beyond the BACKEND-API calling out to `api.anthropic.com`. It does not affect the runner, BigQuery schemas, or frontend routing.

---

## Technology Choices

- **GCP project:** `nfl-model-471509` (ADR-001)
- **BigQuery:** single warehouse, all data (ADR-004)
- **Cloud Run (service):** BACKEND-API, scale-to-zero (ADR-003)
- **Cloud Run (jobs):** Experiment Runner, DATA-PIPELINE ingest
- **Cloud Storage:** raw file uploads, nflfastR source cache
- **Cloud Scheduler:** weekly ingest + prediction refresh
- **FastAPI + Pydantic:** REST layer
- **TypeScript + React + Vite:** frontend
- **Claude API:** dataset schema inference — `claude-haiku-4-5-20251001`, 503 fallback to manual form (delivered Phase 2)
- **Python 3.11+:** all backend and ML code

---

## Non-Goals (v1)

- User accounts and multi-tenancy (single user / personal tool)
- Real-time / streaming predictions
- Live in-game updates
- Mobile native apps
- Sharing experiments publicly
- Natural language query interface (beyond dataset schema inference)
