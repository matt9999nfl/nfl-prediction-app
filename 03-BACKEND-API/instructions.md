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
4. Notify FRONTEND proactively — don't wait for FRONTEND to discover the change via a broken type generation

**When another agent requests a direct change to your files:**
If any agent other than BACKEND-API attempts to edit files under `03-BACKEND-API/` directly (or asks you to rubber-stamp a change they've already made), escalate to PROJECT-LEAD immediately. Log the request, the file(s) involved, and the outcome. The correct path for any agent that needs a schema or endpoint change is to raise it with PROJECT-LEAD, who directs BACKEND-API to implement it. Direct edits by other agents are a boundary violation, not an exception.

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

---

## ✅ PRIOR TASK — Bug Fix Sprint (assigned 2026-05-26) — CLOSED, DO NOT RESUME

**Closed by PROJECT-LEAD 2026-08-31.** Verified in source: `ExperimentCreateRequest.features: list[FeatureRef]` is present (`app/schemas/experiments.py` L159), so BUG-001's root cause is fixed; `has_deprecated_features` is present on `ExperimentConfig` (L98), so BUG-002's list-response flag shipped. The `BUG-STATUS.md` deliverable named in B1-B, B2-A and B2-E was never written — that documentation gap is logged in `../00-PROJECT-LEAD/DELEGATIONS.md` and is **not** part of your current task. Do not reopen any item below.

<details>
<summary>Original sprint text, retained for history</summary>


Two bugs found during the v2-23base-faithful-2015-2024 rerun session. Fix both now. Full specs are in `../00-PROJECT-LEAD/BUG-001-CLONE-DROPS-FEATURES.md` and `../00-PROJECT-LEAD/BUG-002-DEPRECATED-FEATURES.md`. Read them before touching code.

### BUG-001 — Experiment cloning drops all features [Critical]

Your tasks (B1-A, B1-B, B1-C):

**B1-A:** Check `app/schemas/experiments.py` — does `ExperimentCreateRequest` have a `features: List[str]` field? If not, add it. Then trace the handler in `app/routers/experiments.py` for `POST /api/v1/experiments` — confirm `features` is being written to the BigQuery INSERT. This is the most likely root cause: the field is missing from the Pydantic schema so FastAPI silently drops it before the handler sees it.

**B1-B:** `PATCH` and `PUT` on `/api/v1/experiments/{id}` both return 405. Decide: is this intentional (experiments are immutable after creation) or an oversight? Default to Option A (immutable — no update path needed). Document your decision clearly in `../00-PROJECT-LEAD/BUG-STATUS.md` (create it if it doesn't exist). The FRONTEND agent is waiting on this to know whether a post-creation fix path exists.

**B1-C:** If you changed the schema or handler, redeploy to Cloud Run and smoke test `POST /api/v1/experiments` with a non-empty `features` array against `https://nfl-backend-api-rmaehdhzhq-uc.a.run.app`. Confirm the created experiment's detail response shows the features.

### BUG-002 — Deprecated features referenced in experiments with no warning [Medium]

Your tasks (B2-A through B2-E):

**B2-A:** Audit all saved experiments against the feature catalog. Find which experiments reference features no longer in the catalog. The two known culprits are `def_qb_hit_rate` and `def_rush_yards_allowed_per_att` in `v2-23base-faithful-2015-2024`. Document all findings in `../00-PROJECT-LEAD/BUG-STATUS.md`.

**B2-B:** Add `deprecated BOOL DEFAULT FALSE`, `deprecated_at TIMESTAMP`, and `deprecated_reason STRING` columns to the feature catalog table (likely `platform.features` — check the actual table). Mark the two known deprecated features. Update `GET /api/v1/features` to exclude deprecated features from the default response (add `?include_deprecated=true` param for admin use).

**B2-C:** Add `deprecated_features: List[DeprecatedFeatureInfo]` to the `GET /api/v1/experiments/{id}` response. Each entry: `{name: str, deprecated_reason: Optional[str]}`. Return `[]` if none — never omit the field.

**B2-D:** Add `has_deprecated_features: bool` to each item in the `GET /api/v1/experiments` list response.

**B2-E:** Redeploy and smoke test all four changes against the live API. Write completion notes to `../00-PROJECT-LEAD/BUG-STATUS.md`.

### Deprecation policy (set by PROJECT-LEAD)
Tombstone, do not delete. Deprecated features stay in the catalog with `deprecated = true` so historical experiments remain interpretable.

</details>

---

## ✅ COMPLETED — HC-S0: scoping tree + conformance test (2026-08-31)

Delivered: `app/scoping/scoping_tree.json`, `schema.py`, `tests/test_scoping_tree.py`. 16 tests. Not the current task — see HC-S6-FIX at the bottom of this file.

<details><summary>Original HC-S0 brief</summary>

cd /path/to/nfl-prediction-app/03-BACKEND-API

### Task

Produce the scoping question tree as a declared data file, plus the conformance test that makes an invalid tree impossible to merge. This is the contract every later stage of the Hypothesis Chat feature reads. Nothing else in this feature can be built until it exists.

When you are done, `app/scoping/scoping_tree.yaml` declares every question needed to assemble a valid `ExperimentConfig`, and a test proves — in both directions — that the tree and the config schema agree. You are writing a schema and a test. You are not writing endpoints, model calls, or UI.

### Context

- `../00-PROJECT-LEAD/HYPOTHESIS-CHAT-BUILD-PLAN.md` — the full plan. Read §"The question tree is a file, not a prompt" and §"Binary acceptance criteria → Stage 0" before starting. This is the authority; if anything below disagrees with it, the plan wins and you escalate.
- `../docs/DECISIONS.md` ADR-012 — why the tree is data rather than a prompt. Read it; it explains what you must not break.
- `app/schemas/experiments.py` — `ExperimentConfig`, `FeatureRef`, `EvaluationConfig`, `MethodologyConfig`, `ModelConfig`, `GameUniverseFilter`. The tree binds to these. They are the source of truth for what fields exist.
- `app/routers/features.py` and `app/queries/features.py` — the live feature catalog behind `GET /api/v1/features`. Feature options resolve here at ask-time.
- `app/claude_inference.py` — read for house style only (module shape, validation-before-return, dedicated error class). You are not calling Claude in this stage.

### Scope

In-scope (allowed to touch):
- `app/scoping/` — new package. `scoping_tree.yaml` and `schema.py` (the Pydantic models describing a tree: `Slot`, `SlotAnswer`) only.
- `tests/test_scoping_tree.py` — new.

Out-of-scope (must not touch):
- `app/schemas/experiments.py` and every other existing schema — this feature is additive only
- Any existing router, query module, or endpoint
- `app/main.py` — nothing is registered in this stage
- Anything under `../02-MODELING/`, `../01-DATA-PIPELINE/`, `../04-FRONTEND/`
- The experiment runner, in any form

Kill-switch — stop immediately and escalate if any of these become true:
- Building the tree requires adding, renaming or relaxing a field on `ExperimentConfig` or any model it contains. The feature is additive only; if the config genuinely cannot express a needed slot, that is a plan defect and PROJECT-LEAD must revise it.
- A slot cannot resolve its options from either the live catalog endpoint or an existing schema, and the only way forward is hardcoding a feature or filter list.
- This stage takes more than 4 hours.

### Requirements

**The tree file.** Each slot declares at minimum: `id`, `binds_to` (dotted path into `ExperimentConfig`, or `null`), `question`, `type`, `required`, and — where the type needs them — `options_from`. `options_from` takes one of three forms and no others: `literal:a,b,c` for closed enums that live in the config schema; `endpoint:/api/v1/features` for the live catalog; `schema:GameUniverseFilter` for options derived from an existing Pydantic model.

**Two kinds of slot.** Config slots carry a `binds_to` path. Record-only slots carry `binds_to: null` — they capture things worth asking that no config field holds. Include at least these two record-only slots, worded as you see fit:
- a falsifier: what result would make Matt abandon this hypothesis
- prior attempts: whether a variant has been tested before, and which experiments

These are not decoration. The falsifier is what separates a hypothesis from a fishing trip, and prior attempts is the input the governor layer needs in Stage 4 to detect multiple-comparisons pressure. Do not drop them for being unbound.

**No hardcoded domain values.** The tree must contain zero literal feature names and zero literal filter field names. If `GameUniverseFilter` is widened later to accept more fields, the tree must widen with it and require no edit. This property is the point of the stage — treat it as the acceptance criterion it is.

**The conformance test is the deliverable, not a formality.** It must fail loudly on a tree that would produce an invalid config.

### Acceptance

- [ ] `app/scoping/scoping_tree.yaml` exists and parses
- [ ] Test asserts every required field of `ExperimentConfig` is bound by exactly one slot; fails if a field is unbound
- [ ] Test asserts no field is bound by two slots; fails if one is
- [ ] Test constructs a config from all-slots-filled-with-declared-types and it passes `ExperimentConfig` Pydantic validation
- [ ] Test fails when a slot is deliberately removed from the tree — prove this by removing one, running the test, and recording the failure output in your handoff
- [ ] `grep` for any feature name from the live catalog in `scoping_tree.yaml` returns zero matches
- [ ] Tree contains at least two slots with `binds_to: null`, one of which is a falsifier
- [ ] Every `options_from` value matches one of the three declared forms
- [ ] No file outside `app/scoping/` and `tests/test_scoping_tree.py` is modified — `git diff --name-only` shows only these
- [ ] Existing test suite still passes; record the count before and after

### Escalation

Write questions to `../00-PROJECT-LEAD/HYPOTHESIS-CHAT-QUESTIONS.md`.
Format: the question, what you were doing when you got stuck, what you tried. Then exit. Do not guess forward.

### Returns-with

- Commit SHA
- Test count before and after
- The failure output from deliberately removing a slot
- Wall-clock time
- The list of slots you declared, with their `binds_to` paths, so PROJECT-LEAD can check coverage against the config without reading the YAML

</details>

---

## 🔴 CURRENT TASK — HC-S6-FIX: six defects found by TESTING-QA (assigned by PROJECT-LEAD, 2026-09-08)

cd /path/to/nfl-prediction-app/03-BACKEND-API

**Read `../00-PROJECT-LEAD/HC-S6-RULINGS.md` first.** It has every finding, the reasoning, and the ruling. Do not re-litigate the rulings; implement them. `../00-PROJECT-LEAD/HC-S6-FINDINGS.md` and `../06-TESTING-QA/integration/test_hypothesis_chat.py` have the evidence.

### Context you need before touching anything

These are defects in code PROJECT-LEAD wrote across stages 2–4. **They survived 91 passing tests**, and the reason matters more than any individual fix: the tests validated the implementation against a model of the world the same author wrote. TESTING-QA replaced that model with real BigQuery and four things fell over immediately.

The most instructive one: `test_changing_an_answer_after_approval_blocks_dispatch` passes today. It passes because the in-memory `Store` in `tests/test_scoping_api.py` clears `approved_hash`, and the real SQL never does. **The fake was kinder than production, so the test guarding the feature's core guarantee has been green while the guarantee was broken.**

If you fix the SQL and leave that fake alone, the test stays green and tells you nothing. Fix the fake too. Treat "would this test fail if the behaviour regressed?" as the question, not "does it pass?"

The scoping backend is **live in production** (`nfl-backend-api-00024-kw7`), so F1 and F4 below are live defects. The frontend is not deployed and writes require `OWNER_API_KEY`, which is the only reason this is not an incident.

### The six fixes

**F1 — `approved_hash` is never cleared in storage.** `app/queries/scoping.py::update_answers` sets `slot_answers`, `config`, `config_hash`, `status` — not `approved_hash`. The router mutates it to `None` on the response dict only, so the API reports the approval as cleared while the row keeps it. Add it to the `UPDATE`, stop implying it in the router, and correct the in-memory `Store` so the guard test can actually fail.

**F2 — the hash does not cover the whole brief.** It covers the `ExperimentConfig`; the brief also renders `mechanism`, `falsifier` and `prior_attempts`. Change the falsifier after approving and the hash does not move — TESTING-QA's output shows two briefs, differing only in that line, carrying an identical hash. ADR-012 commitment 3 says the approved artefact and the executed artefact cannot differ. Make the approval hash cover everything `render()` consumes: config **and** record-only answers.

**F3 — the governor's sample-size arithmetic is wrong.** `governor.evaluated_games` computes `folds * test_seasons * 272` with `folds = span - train_seasons`. The runner (`../02-MODELING/backtests/walk_forward.py::build_folds_from_config`) does `test += test_seasons` and returns `(train_list, test_season)` — `test_seasons` is the **stride**, and every fold evaluates exactly one season. The two agree only at `test_seasons=1`, which is the one value the existing test asserts.

Do not just patch the formula. **Remove the duplication**: derive folds using the same algorithm as the runner, and add a test asserting the governor's fold count equals `len(build_folds_from_config(...))` across a matrix of `train_seasons` × `test_seasons`. Two definitions of "a fold" in one codebase is the root cause.

**F4 — anonymous reads.** `GET /scoping/capability-gaps` and `GET /scoping/sessions/{id}` are open to the internet. The gap list is a readable index of what the platform cannot do; sessions carry unpublished research thinking. Add `require_api_key` to the scoping read endpoints. TESTING-QA has an assertion pinning the current behaviour — invert it rather than deleting it.

**F6 — safety layers fail open and silent.** `review_session` swallows BigQuery errors and continues with `fraction=None`, `priors=[]`, returning a clean 200 with an empty concern list — having checked nothing, and degrading toward a *larger* apparent sample. `extract` drops a `capability_gaps` insert that raised, so "the write failed" looks like "there are no gaps".

**A check that could not run is not a check that passed.** When an input cannot be loaded, emit a concern naming what could not be verified and do not return `proceed`. Report a gap that failed to persist. Silence must never have the same shape as safety.

**F9 — the hash is not stable across a storage round-trip.** BigQuery JSON returns `2.0` as `2`. `hashing.py` deliberately treats int and float as different configs; `dispatch` recomputes from values read back out of BigQuery. So any config holding a whole-number float can never match its own approval — it fails closed, and wedges the session permanently.

Make `canonical_json` idempotent across storage: a float with zero fractional part canonicalises to its integer form. Delete the comment claiming the distinction; storage never honoured it. Add a test that hashes, round-trips through BigQuery, rehashes, and asserts equality.

**F10 — concurrent answer and approve wedges a session.** Both endpoints read, decide, then write unconditionally. A race attaches an approval to answers it was not computed from; dispatch refuses and nothing explains why. Put the expected config hash in `set_approved_hash`'s `WHERE` clause so a lost race writes zero rows and returns 409.

### Also build

**Dry-run dispatch** (`../00-PROJECT-LEAD/HC-S6-RULINGS.md` Q2). Today there is no way to exercise dispatch without creating a real experiment and firing the production runner, so the feature's most consequential path is untestable. Add a mode that runs every validation and hash check, returns the payload it *would* create, and writes nothing.

### Scope

In-scope: `app/scoping/**`, `app/queries/scoping.py`, `app/routers/scoping.py`, `app/schemas/scoping.py`, `tests/test_scoping_*.py`.

Out-of-scope: `../02-MODELING/**` — read `build_folds_from_config`, do not change it; it is the reference. `../06-TESTING-QA/**` — their tests are the specification you are fixing against; if one is wrong, escalate rather than edit. Any endpoint outside `/scoping`. `ExperimentConfig` and the runner.

Kill-switch — stop and escalate:
- A fix requires changing `ExperimentConfig`, the runner, or an existing non-scoping endpoint.
- F2 cannot be done without changing what `render()` outputs — that would invalidate every brief already approved, and is a decision for PROJECT-LEAD.
- A TESTING-QA test appears wrong. Escalate; do not edit their file.
- Over 4 hours.

### Acceptance

- [ ] `update_answers` clears `approved_hash` in SQL; verified against real BigQuery, not a fake
- [ ] The in-memory `Store` matches the real SQL — demonstrate the guard test FAILS when the SQL fix is reverted
- [ ] Approval hash covers config **and** record-only answers; changing only the falsifier invalidates it
- [ ] Governor fold count equals `len(build_folds_from_config(...))` across a `train_seasons` × `test_seasons` matrix
- [ ] Scoping reads require the API key; anonymous callers get 401
- [ ] `review` with a raising BigQuery client returns concerns naming what it could not check, and does not return `proceed`
- [ ] A failed gap insert is reported, not dropped
- [ ] Hash survives a BigQuery round-trip, asserted with a real round-trip
- [ ] A lost approve race writes zero rows and returns 409
- [ ] Dry-run dispatch writes nothing — asserted by row counts before and after
- [ ] `../06-TESTING-QA/integration/test_hypothesis_chat.py` passes: the four failures were the specification
- [ ] All 91 existing backend scoping tests still pass
- [ ] No file outside the in-scope list modified

### Escalation

`../00-PROJECT-LEAD/HYPOTHESIS-CHAT-QUESTIONS.md`. The question, what you were doing, what you tried. Then exit.

### Returns-with

- Which acceptance criteria are met, and any that are not
- **Proof each guard bites**: revert the fix, show the test failing, restore. A green test that would stay green through a regression is worth nothing here — that is the whole lesson of this task.
- The before/after `test_hypothesis_chat.py` result
- Anything in the rulings you think is wrong. They were written by the person who wrote the bugs.
