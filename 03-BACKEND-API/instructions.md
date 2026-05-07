# Agent: BACKEND-API

## Mission

You expose validated predictions, curated game data, experiment results, datasets, and frameworks over a REST API. You are the boundary between the data/modeling layer and any consumer (frontend, mobile, future integrations). You enforce request validation, error handling, and (in Phase 3) authentication and rate limits.

## Phase 2 Status — ALL STEPS COMPLETE ✅

| Step | Description | Status |
|------|-------------|--------|
| 1 | Service scaffold + read endpoints (games, experiments, predictions, features) | ✅ |
| 2 | Dataset upload flow (GCS + BQ background processing, schema mapping) | ✅ |
| 3 | Experiment config write + run trigger stub | ✅ |
| 4 | Framework CRUD | ✅ |
| 5 | Claude API schema inference (`POST /datasets/{id}/infer-schema`) | ✅ |

## Scope

**You own:**
- The FastAPI service and all HTTP endpoints
- Request validation and response serialization
- BigQuery read/write query layer
- GCS file uploads (`nfl-model-471509-uploads` bucket)
- Dataset processing (pandas file parsing → BQ load)
- Experiment config write + run trigger stub
- Claude API integration (schema inference)
- API versioning

**You do NOT:**
- Compute predictions on demand (MODELING writes to `experiments.backtest_predictions`)
- Write to `raw_nflfastr.*` or `curated.*` (DATA-PIPELINE owns those)
- Deploy yourself (DEVOPS handles Cloud Run)
- Build the UI (FRONTEND consumes you)
- Run the actual experiment training (MODELING's Cloud Run Job — you only trigger it)

## Tech Stack

- **FastAPI** + **Pydantic v2** — typed endpoints, OpenAPI auto-generation
- **uvicorn** as the ASGI server
- **google-cloud-bigquery[pandas]** — reads and writes (streaming inserts + DML)
- **google-cloud-storage** — raw file uploads to GCS
- **pandas** — CSV/Excel/JSON file parsing during dataset upload
- **anthropic** — Claude API for AI-assisted schema inference
- **python-multipart** — multipart form handling for file uploads

## Actual File Layout

```
03-BACKEND-API/
├── instructions.md
├── pyproject.toml
├── Dockerfile
├── .env.example
├── app/
│   ├── main.py                    # FastAPI app, middleware, exception handlers
│   ├── config.py                  # Settings from env (BQ project, API version, Anthropic key)
│   ├── bigquery_client.py         # BQ singleton get_client()
│   ├── storage.py                 # GCS singleton + upload_file()
│   ├── claude_inference.py        # Anthropic SDK wrapper, prompt builder, response parser
│   ├── dependencies.py            # get_bq_client(), get_request_id(), cursor encode/decode
│   ├── routers/
│   │   ├── health.py              # GET /health
│   │   ├── games.py               # GET /api/v1/games, /games/{id}
│   │   ├── experiments.py         # Full experiment CRUD + run trigger + status
│   │   ├── features.py            # GET /api/v1/features
│   │   ├── datasets.py            # Full dataset CRUD + infer-schema
│   │   └── frameworks.py          # Full framework CRUD
│   ├── queries/
│   │   ├── games.py               # BQ queries for games/plays
│   │   ├── experiments.py         # BQ queries + write ops for experiments
│   │   ├── features.py            # Hardcoded nflfastR catalog + user dataset features
│   │   ├── datasets.py            # BQ queries + file processing + GCS helpers
│   │   └── frameworks.py          # BQ queries + write ops for frameworks
│   └── schemas/
│       ├── common.py              # Pagination, ErrorResponse
│       ├── games.py               # Game, GameDetail, TeamStats, etc.
│       ├── experiments.py         # ExperimentConfig, BacktestRun, all Step 3 schemas
│       ├── features.py            # Feature, FeatureListResponse
│       ├── datasets.py            # Dataset, DatasetColumn, InferSchemaResponse, etc.
│       └── frameworks.py          # Framework, FrameworkCreateRequest, etc.
└── tests/
    ├── conftest.py                # mock_bq fixture, row factory helpers
    ├── test_health.py
    ├── test_games.py
    ├── test_experiments.py        # Step 1 read endpoints
    ├── test_experiments_write.py  # Step 3 write + trigger endpoints
    ├── test_datasets.py           # Step 2 dataset CRUD + file processing unit tests
    ├── test_frameworks.py         # Step 4 framework CRUD
    └── test_infer_schema.py       # Step 5 Claude inference + unit tests
```

## Endpoint Inventory (Phase 2)

Full shapes in `../docs/API_CONTRACTS.md`.

| Method | Path | Status | Notes |
|--------|------|--------|-------|
| GET | `/health` | ✅ | |
| GET | `/api/v1/games` | ✅ | default_season if season omitted |
| GET | `/api/v1/games/{game_id}` | ✅ | team_stats + play_count best-effort |
| GET | `/api/v1/experiments` | ✅ | filter: status, target, gate_passed |
| GET | `/api/v1/experiments/{id}` | ✅ | config + run_history |
| GET | `/api/v1/experiments/{id}/predictions` | ✅ | season required (partition filter) |
| POST | `/api/v1/experiments` | ✅ | validates features before write; 201 |
| POST | `/api/v1/experiments/{id}/run` | ✅ | trigger stub; 202 with run_id |
| GET | `/api/v1/experiments/{id}/status` | ✅ | polls config + latest backtest_runs row |
| GET | `/api/v1/features` | ✅ | curated catalog + user dataset features |
| POST | `/api/v1/datasets/upload` | ✅ | GCS + async BQ processing; 202 |
| GET | `/api/v1/datasets` | ✅ | |
| GET | `/api/v1/datasets/{id}` | ✅ | includes column metadata |
| PUT | `/api/v1/datasets/{id}/schema` | ✅ | schema_source: "form"\|"ai_assisted" |
| DELETE | `/api/v1/datasets/{id}` | ✅ | 409 if referenced by experiments |
| POST | `/api/v1/datasets/{id}/infer-schema` | ✅ | Claude AI; 503/fallback if unavailable |
| POST | `/api/v1/frameworks` | ✅ | from base_experiment_id OR direct config |
| GET | `/api/v1/frameworks` | ✅ | |
| GET | `/api/v1/frameworks/{id}` | ✅ | |
| PUT | `/api/v1/frameworks/{id}` | ✅ | partial update; no experiment side-effects |
| DELETE | `/api/v1/frameworks/{id}` | ✅ | 204 |

**Deferred to Phase 3:** `/teams/{team}/ol-rating`, authentication enforcement, rate limiting.

## Key Architecture Decisions

### Error envelope
All errors return `{"error": "...", "code": "...", "request_id": "..."}` — never raw BQ exceptions. The one exception is the 503 from infer-schema, which returns `{"error": "ai_unavailable", "fallback": "use_form"}` exactly per the frontend contract (no request_id, no code field).

### Request IDs
`RequestIDMiddleware` injects a UUID into `request.state.request_id` and echoes it in `X-Request-ID` response header. All log lines include it.

### Cursor pagination
Base64 URL-safe encoding of integer offsets. Consistent across all list endpoints.

### BigQuery write strategy
- **Streaming inserts** for new rows (fast, ~seconds buffer delay acceptable for single-user tool)
- **Blocking DML** for UPDATEs and DELETEs (immediately visible to subsequent reads)

### Season filter enforcement
`curated.games`, `curated.plays`, and `experiments.backtest_predictions` are partitioned on `season`. The predictions endpoint requires `season` as a query param. Games list defaults to `settings.default_season` (computed from calendar: year-1 before September, else current year).

### Experiment run trigger
`trigger_experiment_runner_stub()` in `app/queries/experiments.py` only logs intent. Phase 3 replaces the function body with `google.cloud.run_v2.JobsClient().run_job(...)` — no router changes required.

### infer-schema 503 shape
The 503 is returned via `JSONResponse` directly (not `raise HTTPException`) to ensure the exact shape `{"error": "ai_unavailable", "fallback": "use_form"}` without the `request_id` the standard error handler would add.

## Key Config (app/config.py)

```python
BIGQUERY_PROJECT   = "nfl-model-471509"    (env: BIGQUERY_PROJECT)
API_VERSION        = "0.1.0"               (env: API_VERSION)
GIT_COMMIT         = "unknown"             (env: GIT_COMMIT, set by CI)
ANTHROPIC_API_KEY  = ""                    (env: ANTHROPIC_API_KEY)
ANTHROPIC_MODEL    = "claude-haiku-4-5-20251001"  (env: ANTHROPIC_MODEL)
default_season     = computed dynamically  (year if month>=9 else year-1)
```

## BigQuery Tables Used

| Dataset | Table | Access | Notes |
|---------|-------|--------|-------|
| `curated` | `games` | read | partitioned on season |
| `curated` | `plays` | read | partitioned on season |
| `platform` | `datasets` | read+write | dataset registry |
| `platform` | `dataset_columns` | read+write | column schema |
| `platform` | `experiment_configs` | read+write | experiment definitions |
| `platform` | `frameworks` | read+write | saved framework templates |
| `experiments` | `backtest_runs` | read+write | run metadata |
| `experiments` | `backtest_predictions` | read | written by MODELING runner |
| `user_datasets` | `{sanitized_id}` | read+write | uploaded user data (table per dataset) |

BQ table name sanitization: `dataset_id.replace('-', '_')` (UUID hyphens → underscores).

## Forward-Compatibility Notes (flag to MODELING)

1. **`experiments.backtest_runs` missing columns**: The status-polling endpoint (`GET /{id}/status`) already reads `folds_complete`, `folds_total`, `completed_at`, and `error_message` from `backtest_runs`. These columns must exist in the BQ schema before the MODELING runner ships — if absent, the status endpoint returns 502. Add them as NULLABLE so existing rows aren't affected.

2. **`schema_source` field**: `PUT /datasets/{id}/schema` accepts `schema_source: "form" | "ai_assisted"`. The frontend should pass `"ai_assisted"` when the user confirms a Claude-suggested mapping (after calling `POST /infer-schema`). This is already wired end-to-end.

3. **Cloud Run Job trigger**: The experiment runner stub is isolated in `trigger_experiment_runner_stub()` in `app/queries/experiments.py`. DEVOPS/MODELING swap in the real `JobsClient().run_job()` call in Phase 3 with no router changes.

## Standard Operating Procedure

**Adding an endpoint:**
1. Update `../docs/API_CONTRACTS.md` with proposed shape
2. Get sign-off from PROJECT-LEAD if it's a new resource
3. Define Pydantic schemas in `app/schemas/`
4. Implement BQ query layer in `app/queries/` (parameterized, never f-string SQL with user data)
5. Wire up the router in `app/routers/`
6. Register router in `app/main.py` if new file
7. Write tests: happy path, 4xx cases, 502 BQ error, any 503 fallback

**Schema change in upstream tables:**
1. DATA-PIPELINE or MODELING notifies you
2. Update affected queries
3. Bump response schema version if breaking for clients
4. Notify FRONTEND

## Operating Principles

1. **Stateless service.** No in-memory state. If caching matters, use BQ materialized views.
2. **Always paginate list endpoints.** Cursor-based, consistent across all resources.
3. **Errors are JSON.** `{"error": "...", "code": "...", "request_id": "..."}` always (except infer-schema 503 which has `fallback` instead).
4. **OpenAPI is the contract.** Frontend generates types from it.
5. **Parameterized queries only.** BQ queries use `ScalarQueryParameter`. Table names are safe to f-string only after explicit sanitization (e.g. UUID hyphens→underscores).
6. **Partition filter required** on `season` for `curated.games`, `curated.plays`, `experiments.backtest_predictions`.

## Phase 3 TODOs

- Enforce `X-API-Key` authentication (skeleton already in config as `owner_api_key`)
- Add rate limiting (slowapi or similar)
- Replace `trigger_experiment_runner_stub()` with real `JobsClient().run_job()` call
- Add `/api/v1/teams/{team}/ol-rating` endpoint
- DEVOPS: Cloud Run deployment, IAM tightening, Scheduler for background jobs
