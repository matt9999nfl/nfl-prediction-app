# BACKEND-API Spec — Phase 3

**Owner:** PROJECT-LEAD
**Assigned to:** BACKEND-API
**Date:** 2026-05-06
**Status:** Active

---

## Read These First

1. `../03-BACKEND-API/instructions.md` — your scope, tech stack, current endpoint inventory
2. `../docs/API_CONTRACTS.md` — the contract you are extending
3. `../docs/ARCHITECTURE.md` — component boundaries (relevant: who writes predictions, what `gate_passed` means)

---

## What Phase 2 Delivered

All Phase 2 steps are complete. You are running a full FastAPI service with every endpoint from `docs/API_CONTRACTS.md` implemented, tested, and working locally. The Phase 3 Cloud Run deployment is handled by DEVOPS — you do not need to touch deployment config.

---

## Phase 3 Deliverable: One New Endpoint

### `GET /api/v1/predictions?season=N&week=N`

This is the production predictions surface: it returns per-game predictions for the current (or any given) week, sourced from the most recent experiment that has cleared its success gate. FRONTEND uses this to power game-card prediction overlays on the dashboard home page.

**Signal for "production":** `gate_passed = true` on `experiments.backtest_runs`. No separate `is_production` flag exists or is needed. The most recent run across all experiments where `gate_passed = true` is the production source.

#### Query params

| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `season` | int | Yes | Year (e.g. 2024). Required — partition filter on `backtest_predictions`. 422 if omitted. |
| `week` | int | Yes | Week number (1–18 regular season, 19–22 playoffs). 422 if omitted. |
| `experiment_id` | string | No | Override — if provided, use this specific experiment instead of auto-selecting the most recent gate-passed one. 404 if not found or not gate-passed. |

#### Response 200

```json
{
  "experiment_id": "uuid",
  "experiment_name": "string",
  "season": 2024,
  "week": 5,
  "generated_at": "ISO 8601",
  "data": [
    {
      "game_id": "string",
      "week": 5,
      "home_team": "string",
      "away_team": "string",
      "predicted_home_cover_prob": 0.61,
      "predicted_side": "home",
      "actual_home_covered": null,
      "correct": null,
      "confidence_tier": "high"
    }
  ]
}
```

`actual_home_covered` and `correct` are null for upcoming games; populated for completed games.

`generated_at` is the `completed_at` timestamp from `experiments.backtest_runs` for the selected run — it tells the frontend when these predictions were last refreshed.

#### Response 404

If no gate-passed experiment exists yet:
```json
{ "error": "No gate-passed experiment found", "code": "no_production_experiment", "request_id": "..." }
```

#### Response 422

If `season` or `week` is omitted.

#### BigQuery implementation

Two queries:

**Step 1 — find the production experiment:**
```sql
SELECT
  r.experiment_id,
  r.run_id,
  r.completed_at,
  c.name AS experiment_name
FROM `nfl-model-471509.experiments.backtest_runs` r
JOIN `nfl-model-471509.platform.experiment_configs` c
  ON r.experiment_id = c.experiment_id
WHERE r.gate_passed = true
  AND c.gate_passed = true
ORDER BY r.completed_at DESC
LIMIT 1
```

If `experiment_id` override param is provided, add `AND r.experiment_id = @experiment_id` and skip the `ORDER BY / LIMIT 1`.

**Step 2 — fetch predictions for that run:**
```sql
SELECT
  game_id, week, home_team, away_team,
  predicted_home_cover_prob, predicted_side,
  actual_home_covered, correct, confidence_tier
FROM `nfl-model-471509.experiments.backtest_predictions`
WHERE experiment_id = @experiment_id
  AND season = @season        -- partition filter — required
  AND week   = @week
ORDER BY game_id
```

#### File locations

- **Router:** `app/routers/predictions.py` (new file) — or add to `app/routers/experiments.py` if you prefer to keep prediction routes together. New file is cleaner.
- **Query layer:** `app/queries/predictions.py` (new file)
- **Schema:** Add `ProductionPredictionItem` and `ProductionPredictionsResponse` to `app/schemas/experiments.py` or a new `app/schemas/predictions.py`
- **Register router:** Add to `app/main.py`

#### Tests

Add `tests/test_predictions.py`:

- Happy path: mock BQ returns a gate-passed run + predictions, assert 200 shape
- No gate-passed experiment: mock BQ returns empty, assert 404 + `no_production_experiment` code
- `season` omitted: assert 422
- `week` omitted: assert 422
- `experiment_id` override: mock BQ returns predictions for specified experiment, assert 200
- `experiment_id` override where experiment is not gate-passed: assert 404

Follow the same mocking pattern as `tests/conftest.py` (the `mock_bq` fixture).

---

## Also Do: Update API_CONTRACTS.md

Add the new endpoint shape to `docs/API_CONTRACTS.md` under a new `### Production Predictions` section between `### Teams` and `### Error Codes`. The full shape is the response contract above. Make this the canonical source of truth — FRONTEND reads contracts from this file.

---

## Also Do: Enforce X-API-Key Authentication

`app/config.py` already has `owner_api_key: str | None = os.getenv("OWNER_API_KEY")`. Phase 3 is when enforcement goes live.

Implement a `require_api_key` dependency in `app/dependencies.py`:

```python
from fastapi import Header, HTTPException
from app.config import settings

def require_api_key(x_api_key: str = Header(None)) -> None:
    if not settings.owner_api_key:
        return  # key not configured → open (dev mode)
    if x_api_key != settings.owner_api_key:
        raise HTTPException(
            status_code=401,
            detail={"error": "Missing or invalid API key", "code": "unauthorized", "request_id": ""},
        )
```

Apply it to all **write** endpoints (POST/PUT/DELETE) and to `POST /experiments/{id}/run`. Read endpoints stay open — this is a single-user personal tool and unauthenticated reads are fine.

Add `tests/test_auth.py` with: key missing → 401, key present → passes through, key not configured (dev mode) → open.

---

## Explicitly Out of Scope for This Spec

- `GET /api/v1/teams/{team}/ol-rating` — deferred until after MODELING delivers feature importance scores and weekly prediction refresh is running (separate future spec)
- Rate limiting — not needed pre-launch for single-user tool
- Deployment — DEVOPS owns this

---

## Handoff Signal

When the new endpoint is implemented and tests pass locally:

1. Update `00-PROJECT-LEAD/PHASE3_STATUS.md` — mark BACKEND-API deliverable complete
2. Notify PROJECT-LEAD — FRONTEND unblocks from this endpoint
