# API Contracts (v1)

**Owner:** PROJECT-LEAD + BACKEND-API
**Consumers:** FRONTEND, future integrations
**Base URL:** `https://api.{domain}/api/v1`
**Auth:** `X-API-Key` header (optional for read endpoints, required for write endpoints)
**Last updated:** 2026-05-04

All responses are JSON. All timestamps are ISO 8601 UTC. All errors follow the `Error` shape below.

---

## Common Types

```
Game {
  game_id: string               // nflfastR canonical id e.g. "2024_01_GB_CHI"
  season: int
  week: int
  game_date: string             // ISO 8601
  home_team: string             // 3-letter nflfastR code
  away_team: string
  home_score: int | null
  away_score: int | null
  status: "scheduled" | "final"
  home_spread_close: float | null   // home perspective, negative = home favored
  total_close: float | null
  home_covered: bool | null
  div_game: bool | null
  roof: string | null
  temp: float | null
  wind: float | null
}

Dataset {
  dataset_id: string
  name: string
  description: string
  upload_date: string           // ISO 8601
  join_key_type: "game_id" | "player_season_week" | "team_season_week"
  row_count: int
  column_count: int
  license_tag: "open" | "licensed_commercial" | "personal_use_only"
  status: "uploading" | "mapping" | "ready" | "error"
  schema_source: "form" | "ai_assisted"
}

DatasetColumn {
  dataset_id: string
  column_name: string           // raw column name from uploaded file
  semantic_name: string         // human-readable feature name for experiment builder
  description: string
  data_type: "numeric" | "categorical" | "boolean"
  is_join_key: bool
  null_rate: float              // 0..1
}

ExperimentConfig {
  experiment_id: string
  name: string
  created_at: string
  target: "ats_cover" | "outright_winner" | "total_over" | "team_total_yards"
  features: [{ dataset: string, column: string, semantic_name: string }]
  evaluation: {
    metric: "ats_hit_rate" | "accuracy" | "log_loss" | "rmse"
    success_threshold: float
    min_sample: int
  }
  methodology: {
    type: "walk_forward"
    train_seasons: int
    test_seasons: int
    start_season: int
    end_season: int
    game_universe: GameUniverseFilter | null   // optional; null = all regular-season games
  }

GameUniverseFilter {
  field:    "div_game" | "week"
  operator: "eq" | "gte" | "lte" | "ne"
  value:    bool | int          // bool for div_game, int for week
}

// Preset values the UI exposes (FRONTEND constructs these; API validates them):
//   All games           → game_universe: null
//   Divisional only     → { field: "div_game", operator: "eq",  value: true  }
//   Late season W15-18  → { field: "week",     operator: "gte", value: 15    }
//   Custom              → any valid field/operator/value combination
  model: {
    type: "xgboost" | "logistic_regression" | "random_forest"
    hyperparams: object
  }
  status: "draft" | "running" | "complete" | "failed"
  gate_passed: bool | null
}

BacktestRun {
  run_id: string                // unique ID for this run (from experiments.backtest_runs)
  experiment_id: string         // FK → platform.experiment_configs.experiment_id
  name: string
  run_at: string
  model_type: string
  features: string[]
  ats_hit_rate: float | null
  n_games_evaluated: int | null
  gate_passed: bool | null
  notes: string | null
}

Framework {
  framework_id: string
  name: string
  description: string
  created_at: string
  updated_at: string
  base_experiment_id: string | null   // experiment this was saved from
  config: ExperimentConfig            // the full saved config
}

Error {
  error: string                 // human-readable
  code: string                  // machine-readable
  request_id: string
}

Pagination {
  next_cursor: string | null
  has_more: bool
}
```

---

## Endpoints

### Service

#### `GET /health`
Service status. Public.

**Response 200**
```json
{ "status": "ok", "version": "0.1.0", "commit": "abc1234" }
```

---

### Games

#### `GET /api/v1/games`
List games with optional filters.

**Query params:** `season`, `week`, `team`, `status`, `limit` (default 50, max 200), `cursor`

**Response 200**
```json
{ "data": [Game], "pagination": Pagination }
```

#### `GET /api/v1/games/{game_id}`
Single game with full detail.

**Response 200:** `Game` extended with:
```
play_count: int
team_stats: {
  home: {
    score: int | null
    pass_yards: int | null
    rush_yards: int | null
    total_yards: int | null
    pass_attempts: int | null
    rush_attempts: int | null
  }
  away: { same fields }
}
```
`team_stats` is derived from `curated.plays` at query time. Fields are null if play data is unavailable for the game.

**Response 404:** `Error`

---

### Datasets

#### `POST /api/v1/datasets/upload`
Upload a new dataset file. Accepts `multipart/form-data`.

**Request body (multipart):**
- `file` — CSV, Excel (.xlsx), or JSON file
- `name` — dataset name (string)
- `description` — what this dataset contains (string)
- `license_tag` — "open" | "licensed_commercial" | "personal_use_only"

**Response 202** — accepted, processing async
```json
{
  "dataset_id": "uuid",
  "status": "uploading",
  "schema_job_id": "uuid"
}
```

**Response 400:** file type not supported, file too large (>50MB)

---

#### `GET /api/v1/datasets`
List all registered datasets.

**Query params:** `status`, `license_tag`, `limit` (default 50), `cursor`

**Response 200**
```json
{ "data": [Dataset], "pagination": Pagination }
```

#### `GET /api/v1/datasets/{dataset_id}`
Single dataset with full metadata.

**Response 200:** `Dataset` extended with `columns: [DatasetColumn]`
**Response 404:** `Error`

---

#### `PUT /api/v1/datasets/{dataset_id}/schema`
Submit or update the column schema mapping for a dataset. Used by the form-based flow (Phase 1) and to confirm AI-suggested mappings (Phase 2).

**Request body**
```json
{
  "join_key_type": "game_id" | "player_season_week" | "team_season_week",
  "join_key_columns": {
    "game_id": "column_name_in_file"
    // or for player_season_week:
    // "player_id": "...", "season": "...", "week": "..."
    // or for team_season_week:
    // "team": "...", "season": "...", "week": "..."
  },
  "columns": [
    {
      "column_name": "raw_column_name",
      "semantic_name": "receiver_separation_avg",
      "description": "Average separation (yards) at time of target, per receiver per game",
      "data_type": "numeric"
    }
  ]
}
```

**Response 200:** `Dataset` (updated)
**Response 400:** invalid join key mapping, unknown column names

---

#### `POST /api/v1/datasets/{dataset_id}/infer-schema`
Trigger AI-assisted schema inference via Claude API. Returns suggested mappings for user review. Does not apply mappings — use `PUT /schema` to confirm.

**Response 200**
```json
{
  "suggested_join_key_type": "player_season_week",
  "suggested_join_key_columns": { "player_id": "gsis_id", "season": "year", "week": "week_num" },
  "suggested_columns": [DatasetColumn],
  "data_quality_flags": [
    { "column": "separation_yards", "issue": "12% null rate", "severity": "warning" }
  ],
  "confidence": 0.91
}
```

**Response 503:** Claude API unavailable — fall back to form-based mapping

---

#### `DELETE /api/v1/datasets/{dataset_id}`
Remove a dataset and its BigQuery table. Fails if any experiment configs reference this dataset.

**Response 204:** deleted
**Response 409:** dataset referenced by existing experiments

---

### Experiments

#### `POST /api/v1/experiments`
Create a new experiment configuration. Does not run it.

**Request body:** `ExperimentConfig` (without `experiment_id`, `created_at`, `status`, `gate_passed`)

**Response 201**
```json
{ "experiment_id": "uuid", "status": "draft" }
```

**Response 400:** unknown feature columns, invalid target/metric combination

---

#### `GET /api/v1/experiments`
List experiment configs.

**Query params:** `status`, `target`, `gate_passed`, `limit` (default 50), `cursor`

**Response 200**
```json
{ "data": [ExperimentConfig], "pagination": Pagination }
```

#### `GET /api/v1/experiments/{experiment_id}`
Full experiment config + latest run results + per-fold breakdown.

**Response 200**
```json
{
  "config": ExperimentConfig,
  "latest_run": BacktestRun | null,
  "run_history": [BacktestRun],
  "per_fold": [
    {
      "season": 2024,
      "wins": 167,
      "losses": 105,
      "pushes": 4,
      "hit_rate": 0.614,
      "n_games": 272
    }
  ]
}
```

`per_fold` is sourced from `experiments.backtest_predictions` grouped by `season` for the experiment's `latest_run_id`. Returns `[]` if no run exists or no predictions are recorded.

**Response 404:** `Error`

---

#### `GET /api/v1/experiments/{experiment_id}/feature-importance`
Feature importances for the most recent run of an experiment.

Sourced from the `feature_importances` JSON column in `experiments.backtest_runs` for the `latest_run_id`. Returns importances sorted descending.

**Response 200**
```json
{
  "run_id": "uuid | null",
  "features": [
    { "feature": "home_ol_rush_epa_per_att", "importance": 0.0842 },
    { "feature": "away_ol_pass_epa_per_att", "importance": 0.0601 }
  ]
}
```

Returns `{ "run_id": null, "features": [] }` if no run exists or no importance data has been recorded.

**Response 404:** `Error`

---

#### `POST /api/v1/experiments/{experiment_id}/run`
Trigger an experiment run. Launches the Experiment Runner Cloud Run Job.

**Response 202**
```json
{ "run_id": "uuid", "status": "running", "estimated_duration_seconds": 120 }
```

**Response 409:** experiment already running
**Response 400:** experiment config incomplete (still in draft with unmapped features)

---

#### `GET /api/v1/experiments/{experiment_id}/status`
Poll experiment run status.

**Response 200**
```json
{
  "experiment_id": "uuid",
  "run_id": "uuid",
  "status": "running" | "complete" | "failed",
  "progress": { "folds_complete": 3, "folds_total": 6 },
  "started_at": "ISO 8601",
  "completed_at": "ISO 8601 | null",
  "error": "string | null"
}
```

---

#### `GET /api/v1/experiments/{experiment_id}/predictions`
Per-game predictions from the latest completed run.

**Query params:** `season` *(required — partition filter, 422 if omitted)*, `fold`, `ol_mismatch_flag`, `limit` (default 100, max 500), `cursor`

Notes on optional filters: `fold` is a standard column in all walk-forward experiment outputs. `ol_mismatch_flag` is present only in Phase 1 OL-experiment runs; apply this filter only if the column exists in `experiments.backtest_predictions` for the given run. If the column is absent and the filter is requested, return 400 with code `unsupported_filter` rather than letting BigQuery error through.

**Response 200**
```json
{
  "data": [
    {
      "game_id": "string",
      "season": int,
      "week": int,
      "fold": int,
      "home_team": "string",
      "away_team": "string",
      "predicted_home_cover_prob": float,
      "predicted_side": "home" | "away",
      "actual_home_covered": bool | null,
      "correct": int | null,
      "confidence_tier": "high" | "medium" | "low"
    }
  ],
  "pagination": Pagination
}
```

---

### Production Predictions

#### `GET /api/v1/predictions`
Production predictions for a given season/week — sourced from the most recent experiment that has cleared its success gate. Used by FRONTEND to power game-card prediction overlays on the dashboard.

**Query params:**
- `season` (int, required): Season year (e.g. 2024). 422 if omitted.
- `week` (int, required): Week number (1-18 regular season, 19-22 playoffs). 422 if omitted.
- `experiment_id` (string, optional): Override — if provided, use this specific experiment instead of auto-selecting the most recent gate-passed one. 404 if not found or not gate-passed.

**Response 200**
```json
{
  "experiment_id": "string (uuid)",
  "experiment_name": "string",
  "season": 2024,
  "week": 5,
  "generated_at": "string (ISO 8601)",
  "data": [
    {
      "game_id": "string",
      "week": 5,
      "home_team": "string",
      "away_team": "string",
      "predicted_home_cover_prob": 0.61,
      "predicted_side": "home" | "away",
      "actual_home_covered": bool | null,
      "correct": bool | null,
      "confidence_tier": "high" | "medium" | "low"
    }
  ]
}
```

`actual_home_covered` and `correct` are null for upcoming games; populated for completed games.

`generated_at` is the `completed_at` timestamp from `experiments.backtest_runs` for the selected run.

**Response 404**
```json
{ "error": "No gate-passed experiment found", "code": "no_production_experiment", "request_id": "..." }
```

**Response 422**
If `season` or `week` is omitted.

---

### Frameworks

#### `POST /api/v1/frameworks`
Save an experiment config as a named framework.

**Request body**
```json
{
  "name": "OL mismatch ATS baseline",
  "description": "Starting point for OL-focused ATS experiments",
  "base_experiment_id": "uuid"   // optional — save from existing experiment
}
```

**Response 201:** `Framework`

---

#### `GET /api/v1/frameworks`
List saved frameworks.

**Response 200**
```json
{ "data": [Framework], "pagination": Pagination }
```

#### `GET /api/v1/frameworks/{framework_id}`
Single framework with full config.

**Response 200:** `Framework`

#### `PUT /api/v1/frameworks/{framework_id}`
Update a framework's config or metadata. Creates a new experiment from the updated config (does not mutate past runs).

**Response 200:** `Framework` (updated)

#### `DELETE /api/v1/frameworks/{framework_id}`
**Response 204:** deleted

---

### Available Features

#### `GET /api/v1/features`
List all features available to the experiment builder — both nflfastR-derived and from registered user datasets.

**Query params:** `dataset`, `data_type`, `join_key_type`

**Response 200**
```json
{
  "data": [
    {
      "feature_id": "curated.home_ol_pass_epa_per_att",
      "semantic_name": "home_ol_pass_epa_per_att",
      "description": "Home team mean EPA per pass attempt, season-to-date",
      "dataset": "curated",
      "data_type": "numeric",
      "join_key_type": "game_id",
      "license_tag": "open"
    }
  ]
}
```

---

### Teams (read-only)

#### `GET /api/v1/teams/{team}/ol-rating`
Cumulative season-to-date OL rating history for a team, computed directly from `curated.plays`.

For each (season, week) where the team appeared as the offensive team, returns the running average of `ol_rush_epa_per_att` and `ol_pass_epa_per_att` across all plays from week 1 through that week of that season. Matches the look-ahead-safe cumulation logic used by the MODELING layer.

**Query params:** `season` (int, optional — restricts to a single season)

**Response 200**
```json
{
  "team": "KC",
  "ratings": [
    { "season": 2024, "week": 1, "ol_rush_epa_per_att": 0.12, "ol_pass_epa_per_att": 0.08 },
    { "season": 2024, "week": 2, "ol_rush_epa_per_att": 0.14, "ol_pass_epa_per_att": 0.10 }
  ]
}
```

`ol_rush_epa_per_att` and `ol_pass_epa_per_att` may be null for weeks with no qualifying plays. Returns `{ "team": "KC", "ratings": [] }` if the team has no play history.

**Response 400:** invalid team code format
**Response 502:** `Error`

---

## Error Codes

| Code | HTTP | Meaning |
|------|------|---------|
| `not_found` | 404 | Resource doesn't exist |
| `invalid_params` | 400 | Validation failed |
| `conflict` | 409 | State conflict (experiment running, dataset in use) |
| `unauthorized` | 401 | Missing or invalid API key |
| `rate_limited` | 429 | Too many requests |
| `upstream_error` | 502 | Claude API or BigQuery unavailable |
| `internal_error` | 500 | Unexpected server error |

---

## Versioning

Breaking changes bump `/v1` to `/v2`. Additive changes (new optional fields, new endpoints) ship in `/v1`.
