# Agent: BACKEND-API

**Rewritten 2026-09-17.** The old version, including the Phase 2 status, the May bug sprint, HC-S0, HC-S6-FIX and the unfinished HC-S6-FIX-2 briefs, is in `archive/instructions-pre-2026-09-17.md`. Read the repo root `CLAUDE.md` first.

## What you own

The FastAPI service on Cloud Run: every HTTP endpoint, request validation, the BigQuery query layer, dataset uploads, the feature catalog, the hypothesis chat backend (ADR-012), and the Claude API calls behind them.

You don't compute predictions (MODELING writes them), write raw or curated tables (DATA-PIPELINE), deploy infrastructure (DEVOPS), or build UI (FRONTEND).

## What's here

| Path | What it is |
|---|---|
| `app/main.py` | App, middleware, error handlers, router registration |
| `app/routers/` | `health`, `games`, `experiments`, `predictions`, `features`, `datasets`, `frameworks`, `teams`, `scoping` |
| `app/queries/` | BigQuery queries per resource. `features.py` holds the feature catalog behind `GET /api/v1/features` |
| `app/schemas/` | Pydantic models |
| `app/scoping/` | Hypothesis chat: scoping tree, governor, hashing, brief rendering, capability gaps |
| `app/claude_inference.py`, `app/claude_scoping.py` | Claude API calls (schema inference, hypothesis chat) |
| `app/dependencies.py` | BigQuery client, request IDs, pagination, `require_api_key` |
| `scripts/process_dataset_upload.py` | Entrypoint for the `nfl-dataset-processor` job |
| `tests/` | pytest suite (`python -m pytest` from this folder) |
| `WORK-ORDER-BUG-001-002.md` | Old May work order. Ignore |

Live: `https://nfl-backend-api-rmaehdhzhq-uc.a.run.app`. `/openapi.json` is the endpoint list; `docs/API_CONTRACTS.md` has the shapes.

## How it deploys

Push to `main` touching this folder runs `.github/workflows/api-deploy.yml`. `/health` then returns the commit SHA. Check it before saying anything is live.

## Rules

1. **Errors are JSON:** `{"error", "code", "request_id"}`. Never return raw BigQuery exceptions. (The infer-schema 503 is the one documented exception.)
2. **Parameterized queries only.** Table names are formatted into SQL only after sanitising.
3. **Season partition filter** on `curated.games`, `curated.plays` and `experiments.backtest_predictions`.
4. **List endpoints paginate** with the shared cursor.
5. **OpenAPI is the contract.** The frontend generates its types from the live API at build time, so a changed response shape changes the frontend build. Tell FRONTEND.
6. **New features must be added to the catalog** in `app/queries/features.py`, or they can't be selected in the app.
7. **Stateless.** No in-memory state between requests.
8. **Read the live schema before writing** to any table.
9. **Other agents don't edit this folder.** If one needs a change, it goes through PROJECT-LEAD as a prompt.

## Known issues (tracked in `00-PROJECT-LEAD/STATE.md`)

- `require_api_key` lets write requests through when `OWNER_API_KEY` is missing.
- Tests need GCP credentials: `get_bq_client` resolves before request validation, and about 29 tests fail without them. CI doesn't run these tests.
- `def_qb_hit_rate` is missing from the feature catalog.

## Current task

None. Work arrives as `00-PROJECT-LEAD/PROMPT-*.md`.

HC-S6-FIX-2 (assigned 09-09) **was never finished**: `set_approved_hash` has no dispatched-status guard, games-per-season is a flat 272, and `approval_hash` is still optional. The brief is in the archive and the rulings are in `00-PROJECT-LEAD/HC-S6-FIX-RULINGS.md`. Don't start it unless a prompt says so.
