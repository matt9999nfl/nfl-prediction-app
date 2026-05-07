# BACKEND-API Spec — Phase 2

**Owner:** PROJECT-LEAD
**Assigned to:** BACKEND-API
**Date:** 2026-05-03
**Status:** ✅ Complete — 2026-05-04 (all 5 steps delivered; 6 contract ambiguities resolved in API_CONTRACTS.md)

---

## Read These First

Before writing a line of code, read these documents in order:

1. `../03-BACKEND-API/instructions.md` — your role and scope
2. `../docs/ARCHITECTURE.md` — updated system design, component boundaries, BigQuery layout
3. `../docs/API_CONTRACTS.md` — the complete endpoint specs you implement

Everything you build must match `API_CONTRACTS.md` exactly. If you find an ambiguity, stop and flag it — do not make assumptions.

---

## What You Are Building

A FastAPI service running on Cloud Run that is the single interface between the frontend and everything in BigQuery. This is now a **read/write platform API** — not just a display layer. It:

- Serves game data, experiment results, and predictions (read)
- Accepts dataset file uploads and stores them in Cloud Storage + BigQuery (write)
- Accepts experiment configurations and stores them in `platform.experiment_configs` (write)
- Triggers the Experiment Runner Cloud Run Job when a user clicks "Run" (async trigger)
- Calls the Claude API for dataset schema inference (single call, one endpoint)

---

## BigQuery Tables Available to You

| Table | Read | Write | Notes |
|-------|------|-------|-------|
| `curated.games` | ✅ | ❌ | Game data for `/games` endpoints |
| `curated.plays` | ✅ | ❌ | Not directly served — used for feature queries if needed |
| `experiments.backtest_runs` | ✅ | ✅ | Write `experiment_config_id` and `success_criteria` on new runs |
| `experiments.backtest_predictions` | ✅ | ❌ | Predictions written by Experiment Runner only |
| `platform.datasets` | ✅ | ✅ | Dataset registry — you own all writes |
| `platform.dataset_columns` | ✅ | ✅ | Column schema — you own all writes |
| `platform.experiment_configs` | ✅ | ✅ | Experiment definitions — you own all writes |
| `platform.frameworks` | ✅ | ✅ | Saved frameworks — you own all writes |
| `user_datasets.*` | ✅ | ✅ | Read for feature queries; write on dataset load completion |
| `raw_nflfastr.*` | ❌ | ❌ | Pipeline layer — never touch |

---

## Build Order

Build in this sequence. Each step unblocks the next.

### Step 1 — Service scaffold + read endpoints (start here)

Get the service running and serving data from existing tables.

- FastAPI app with health endpoint (`GET /health`)
- BigQuery client setup (service account, project config)
- `GET /api/v1/games` and `GET /api/v1/games/{game_id}` from `curated.games`
- `GET /api/v1/experiments` and `GET /api/v1/experiments/{id}` from `platform.experiment_configs` + `experiments.backtest_runs`
- `GET /api/v1/experiments/{id}/predictions` from `experiments.backtest_predictions`
- `GET /api/v1/features` — union of nflfastR feature catalog (hardcoded list for now, see below) + `platform.dataset_columns WHERE status = 'ready'`

These endpoints touch only existing data. Ship this first so FRONTEND has something real to connect to.

---

### Step 2 — Dataset upload flow

Implement the full dataset upload pipeline.

**Flow:**
1. `POST /api/v1/datasets/upload` receives multipart file
2. Write raw file to Cloud Storage: `gs://nfl-model-471509-uploads/{dataset_id}/raw.{ext}`
3. Insert a row into `platform.datasets` with `status = 'uploading'`
4. Launch a background job (Cloud Run Job or async task) that:
   - Parses the file (CSV/Excel/JSON)
   - Loads it into BigQuery as `user_datasets.{dataset_id}`
   - Computes row count, column count, null rates per column
   - Inserts rows into `platform.dataset_columns` (one per column, with `semantic_name` and `description` null until schema mapping is submitted)
   - Updates `platform.datasets` with `status = 'mapping'`, row_count, column_count
5. Return 202 with `dataset_id` and `status = 'uploading'`

**File limits:** 50MB max. Supported types: CSV, Excel (.xlsx, .xls), JSON (array of objects).

**`GET /api/v1/datasets`** and **`GET /api/v1/datasets/{id}`** serve from `platform.datasets` + `platform.dataset_columns`.

**`PUT /api/v1/datasets/{id}/schema`** updates `platform.dataset_columns` semantic names and the `join_key_type` + `join_key_columns` on `platform.datasets`. Set `status = 'ready'` when schema is confirmed.

**`DELETE /api/v1/datasets/{id}`** — check for references in `platform.experiment_configs.features` before deleting. Return 409 if referenced.

---

### Step 3 — Experiment configuration and run trigger

**`POST /api/v1/experiments`** — validate the config (all referenced dataset columns exist and are `ready`), write to `platform.experiment_configs` with `status = 'draft'`.

**`POST /api/v1/experiments/{id}/run`** — trigger the Experiment Runner:
1. Validate experiment config is complete (not draft, all features resolvable)
2. Update `platform.experiment_configs.status = 'running'`
3. Trigger Cloud Run Job: `MODELING/backtests/run_phase1_backtest.py` (to be refactored by MODELING into a config-driven runner). Pass `experiment_id` as an environment variable or job argument.
4. Return 202 with `run_id` and `status = 'running'`

**`GET /api/v1/experiments/{id}/status`** — poll `platform.experiment_configs.status` and `experiments.backtest_runs` for the latest run.

When the Experiment Runner completes, it writes to `experiments.backtest_runs` and updates `platform.experiment_configs.status` and `gate_passed` directly. The API does not need to poll — it reads the current state on demand.

---

### Step 4 — Framework CRUD

Straightforward CRUD on `platform.frameworks`. No async work — all synchronous reads and writes.

`POST /api/v1/frameworks` — if `base_experiment_id` is provided, copy the config from `platform.experiment_configs` as the `config_snapshot`. Otherwise use the provided config.

`PUT /api/v1/frameworks/{id}` — update metadata and config. Does NOT re-run the experiment. Does NOT mutate past runs.

---

### Step 5 — Claude API schema inference (last)

`POST /api/v1/datasets/{id}/infer-schema` — call Claude API with column names and sample values from `user_datasets.{dataset_id}`. Parse response into `suggested_join_key_type`, `suggested_columns`, and `data_quality_flags`. Return as JSON for the frontend to display — do not auto-apply.

**Claude API call shape:**
```python
# Pseudo-code — BACKEND-API implements the actual call
prompt = f"""
You are analyzing an NFL dataset uploaded by a user.
Column names: {column_names}
Sample rows (first 5): {sample_rows_json}

Return JSON with:
- suggested_join_key_type: "game_id" | "player_season_week" | "team_season_week"
- suggested_join_key_columns: {{role: column_name}} mapping
- suggested_columns: [{{"column_name": str, "semantic_name": str, "description": str, "data_type": str}}]
- data_quality_flags: [{{"column": str, "issue": str, "severity": "warning"|"error"}}]
- confidence: float 0..1
"""
```

Handle `503` gracefully — if Claude API is unavailable, return `{"error": "ai_unavailable", "fallback": "use_form"}` and let the frontend fall back to the manual mapping form.

---

## nflfastR Feature Catalog (for `GET /api/v1/features`)

Until MODELING delivers a dynamic feature registry, hardcode this list in the API. These are the features computed by MODELING in ol_xgb_v2 and available in `experiments.backtest_predictions`.

Each entry has: `feature_id`, `semantic_name`, `description`, `dataset: "curated"`, `data_type: "numeric"`, `join_key_type: "game_id"`, `license_tag: "open"`.

**Per-team features (prefix `home_` and `away_` for each):**
- `ol_sack_rate` — Sacks allowed per pass attempt, season-to-date
- `ol_qb_hit_rate` — QB hits allowed per pass attempt, season-to-date
- `ol_pressure_proxy_rate` — (Sacks + QB hits) per pass attempt, season-to-date
- `ol_pass_epa_per_att` — Mean EPA per pass attempt, season-to-date
- `ol_rush_epa_per_att` — Mean EPA per rush attempt, season-to-date
- `ol_rush_yards_per_att` — Mean rush yards per attempt, season-to-date
- `qb_epa_per_dropback` — Mean EPA per dropback, season-to-date
- `qb_cpoe` — Mean completion % over expected, season-to-date
- `qb_epa_under_pressure` — Mean EPA on pressured dropbacks, season-to-date
- `pass_explosive_rate` — % of pass plays gaining 20+ yards
- `rush_explosive_rate` — % of rush plays gaining 10+ yards
- `def_epa_per_play` — Mean EPA allowed per play, season-to-date
- `def_pass_epa_allowed_per_att` — Mean EPA allowed per pass attempt
- `def_rush_epa_allowed_per_att` — Mean EPA allowed per rush attempt
- `def_pressure_proxy_rate` — (Sacks + QB hits generated) per opponent pass attempt
- `def_sack_rate` — Sacks generated per opponent pass attempt
- `def_explosive_pass_allowed_rate` — % of opponent pass plays allowing 20+ yards
- `def_explosive_rush_allowed_rate` — % of opponent rush plays allowing 10+ yards
- `rest_days` — Days since last game
- `prior_week_margin` — Score margin in most recent game
- `rolling_3wk_epa_trend` — Mean team EPA per play over last 3 games
- `season_win_pct` — Season-to-date win percentage

**Game context features (no home/away prefix):**
- `rest_differential` — home_rest_days minus away_rest_days
- `div_game` — Divisional matchup flag
- `roof_dome` — 1 if dome/retractable closed
- `temp` — Game-time temperature (°F)
- `wind` — Wind speed (mph)

---

## Implementation Notes

**BigQuery queries must be partition-aware.** Always filter by `season` when querying `curated.games`, `curated.plays`, or `experiments.backtest_predictions`. Unfiltered full-table scans will be slow and expensive.

**Cloud Storage bucket:** `nfl-model-471509-uploads` — create if it doesn't exist. Use uniform bucket-level access, not per-object ACLs.

**Async jobs:** For dataset loading (Step 2) and experiment running (Step 3), the API triggers a job and returns 202 immediately. The frontend polls the status endpoint. Do not block the API response waiting for BigQuery jobs to complete.

**Error handling:** All 500-level errors must include a `request_id` in the response. Log the full error server-side with the same `request_id` for traceability.

**Service account:** Use the existing project service account. DEVOPS will tighten IAM in Phase 3 — for now, use whatever has BigQuery read/write access.

---

## Out of Scope for Phase 2

- User authentication / API keys (single-user tool for now)
- Rate limiting (add in Phase 3)
- The teams OL-rating endpoint (`/teams/{team}/ol-rating`) — defer to Phase 3
- Any DEVOPS work (Cloud Run deployment, Scheduler) — that's Phase 3
- Writing to `raw_nflfastr.*` or `curated.*` — those are DATA-PIPELINE's tables
