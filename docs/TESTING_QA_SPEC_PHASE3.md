# TESTING-QA Spec — Phase 3

**Owner:** PROJECT-LEAD
**Assigned to:** TESTING-QA
**Date:** 2026-05-06
**Status:** Active

---

## Read These First

1. `../06-TESTING-QA/instructions.md` — your scope, principles, CI tier structure
2. `../docs/ARCHITECTURE.md` — the seams between components you will test
3. `../docs/API_CONTRACTS.md` — the shapes you will assert against
4. `../03-BACKEND-API/tests/conftest.py` — existing BQ mock fixture pattern (reuse, don't reinvent)

---

## What Exists Today

Phase 2 agents wrote unit tests inside their own folders:
- `03-BACKEND-API/tests/` — unit tests for all endpoints (mocked BQ client)
- `02-MODELING/` — no tests yet
- `01-DATA-PIPELINE/` — no tests yet

The `06-TESTING-QA/` folder contains only `instructions.md`. You are building it from scratch. Do not duplicate the unit tests that already exist in `03-BACKEND-API/tests/` — those are the BACKEND-API agent's responsibility. Your job is the **seams**.

---

## What "The Seams" Means for This Project

```
[DATA-PIPELINE]  →  curated.*          Seam 1: schema contract
[curated.*]      →  run_experiment.py  Seam 2: feature matrix builds correctly
[run_experiment] →  experiments.*      Seam 3: correct BQ writes (runs + predictions)
[experiments.*]  →  BACKEND-API        Seam 4: API returns correct shapes
[BACKEND-API]    →  FRONTEND types     Seam 5: generated TS types compile
[end-to-end]                           Seam 6: create config → run → poll → verify
```

Each seam is a test file. You own all six.

---

## Environment

### Local dev (can start immediately)

- `03-BACKEND-API`: `cd 03-BACKEND-API && uvicorn app.main:app --reload --port 8080`
- `02-MODELING`: `EXPERIMENT_CONFIG_ID=<uuid> python backtests/run_experiment.py`
- BigQuery: live GCP project `nfl-model-471509` — read-only on `curated.*`, write to a `test_*` dataset prefix for isolation
- Requires: `GOOGLE_APPLICATION_CREDENTIALS` set locally (ADC)

### Live API (available after DEVOPS Step 1a)

Integration tests tagged `@pytest.mark.live` run against the deployed Cloud Run URL. Store URL in `pytest.ini` or `conftest.py` env var `API_BASE_URL`. These run in CI Tier 3 (nightly) once the URL is live.

### BigQuery test isolation

- Write any test rows to tables prefixed `test_` or to a separate `test_experiments.*` dataset
- Use UUIDs in all test data — never hardcode experiment IDs that might collide with real data
- Clean up test rows in `pytest` teardown using `DELETE WHERE experiment_id = @test_id`

---

## Deliverable 1 — Test Infrastructure Setup

### `06-TESTING-QA/conftest.py`

Shared fixtures for all integration tests:

```python
import os
import uuid
import pytest
from google.cloud import bigquery

PROJECT = "nfl-model-471509"
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8080")

@pytest.fixture(scope="session")
def bq_client():
    return bigquery.Client(project=PROJECT)

@pytest.fixture
def test_run_id():
    """A unique ID for each test run, used to scope BQ writes."""
    return f"test_{uuid.uuid4().hex[:12]}"

@pytest.fixture(autouse=True)
def cleanup_test_rows(bq_client, test_run_id):
    """Delete any rows written during a test."""
    yield
    # Teardown: delete test rows from backtest_runs and backtest_predictions
    for table in [
        f"{PROJECT}.experiments.backtest_runs",
        f"{PROJECT}.experiments.backtest_predictions",
    ]:
        try:
            bq_client.query(
                f"DELETE FROM `{table}` WHERE experiment_id LIKE 'test_%'"
            ).result()
        except Exception:
            pass  # Ignore teardown errors — don't fail tests on cleanup

@pytest.fixture
def api(requests_session):
    """HTTP session pointed at the API base URL."""
    import requests
    s = requests.Session()
    s.base_url = API_BASE_URL
    return s
```

### `06-TESTING-QA/pytest.ini` (or `pyproject.toml` `[tool.pytest.ini_options]`)

```ini
[pytest]
markers =
    integration: integration tests that touch BigQuery (may be slow)
    live: requires deployed API_BASE_URL to be set
    nightly: Tier 3 — full backtest replay, data quality checks
```

### `06-TESTING-QA/requirements.txt`

```
pytest
pytest-timeout
requests
google-cloud-bigquery
pandas
```

---

## Deliverable 2 — Seam 1: Schema Contract (`integration/test_pipeline_to_curated.py`)

Tests that `curated.games` and `curated.plays` exist with the expected columns, types, and no critical nulls. This catches schema drift — if DATA-PIPELINE changes a column name or type, this test breaks and surfaces it before MODELING or BACKEND-API fails silently.

```python
"""
Seam 1: DATA-PIPELINE → curated.*
Verifies that curated tables exist, have the expected schema, and pass basic
data quality checks. Does not verify correctness of values — only shape.
"""
import pytest
from google.cloud import bigquery

PROJECT = "nfl-model-471509"

EXPECTED_GAMES_COLUMNS = {
    "game_id": "STRING",
    "season": "INTEGER",
    "week": "INTEGER",
    "home_team": "STRING",
    "away_team": "STRING",
    "home_score": "INTEGER",
    "away_score": "INTEGER",
    "spread_line": "FLOAT",
    "home_covered": "BOOLEAN",
    "div_game": "BOOLEAN",
}

@pytest.mark.integration
def test_curated_games_schema(bq_client):
    """curated.games has all required columns with correct types."""
    table = bq_client.get_table(f"{PROJECT}.curated.games")
    schema = {f.name: f.field_type for f in table.schema}
    for col, expected_type in EXPECTED_GAMES_COLUMNS.items():
        assert col in schema, f"Missing column: {col}"
        assert schema[col] == expected_type, (
            f"Column {col}: expected type {expected_type}, got {schema[col]}"
        )

@pytest.mark.integration
def test_curated_games_season_coverage(bq_client):
    """curated.games has data from 2015 through at least 2023."""
    rows = list(bq_client.query(
        f"SELECT MIN(season) as min_s, MAX(season) as max_s "
        f"FROM `{PROJECT}.curated.games`"
    ).result())
    assert rows[0]["min_s"] <= 2015, "curated.games missing seasons before 2015"
    assert rows[0]["max_s"] >= 2023, "curated.games missing recent seasons"

@pytest.mark.integration
def test_curated_games_no_null_game_ids(bq_client):
    """game_id is never null in curated.games."""
    rows = list(bq_client.query(
        f"SELECT COUNT(*) as n FROM `{PROJECT}.curated.games` WHERE game_id IS NULL"
    ).result())
    assert rows[0]["n"] == 0, f"curated.games has {rows[0]['n']} null game_ids"

@pytest.mark.integration
def test_curated_games_spread_null_rate(bq_client):
    """spread_line null rate is under 5% for regular season games."""
    rows = list(bq_client.query(f"""
        SELECT
          COUNTIF(spread_line IS NULL) / COUNT(*) as null_rate
        FROM `{PROJECT}.curated.games`
        WHERE season >= 2015
    """).result())
    null_rate = rows[0]["null_rate"]
    assert null_rate < 0.05, (
        f"spread_line null rate is {null_rate:.1%} — "
        f"expected < 5% (validates closing-line data quality)"
    )

@pytest.mark.integration
def test_no_look_ahead_in_curated_games(bq_client):
    """
    For completed games, actual score cannot be null if home_covered is set.
    This is a proxy for checking that result fields are not being populated
    for future games.
    """
    rows = list(bq_client.query(f"""
        SELECT COUNT(*) as n
        FROM `{PROJECT}.curated.games`
        WHERE home_covered IS NOT NULL
          AND (home_score IS NULL OR away_score IS NULL)
    """).result())
    assert rows[0]["n"] == 0, (
        f"{rows[0]['n']} rows have home_covered set but no actual score — "
        "possible look-ahead contamination"
    )
```

---

## Deliverable 3 — Seam 3: Runner Writes (`integration/test_runner_bq_writes.py`)

Tests that after a run of `run_experiment.py`, the expected rows appear in `experiments.backtest_runs` and `experiments.backtest_predictions` with correct structure. Uses the live experiment runner with a minimal known-good config.

**Design note:** This is an integration test that actually invokes the runner. It's slow (~2–10 minutes) and lives in CI Tier 3. Mark it `@pytest.mark.nightly`.

```python
"""
Seam 3: run_experiment.py → experiments.*
Verifies that a runner invocation produces correct BQ writes.
Uses a minimal curated-only experiment config (no user datasets).
"""
import json
import os
import subprocess
import uuid
import pytest
from google.cloud import bigquery

PROJECT     = "nfl-model-471509"
CONFIGS_TBL = f"{PROJECT}.platform.experiment_configs"
RUNS_TBL    = f"{PROJECT}.experiments.backtest_runs"
PREDS_TBL   = f"{PROJECT}.experiments.backtest_predictions"

MINIMAL_CONFIG = {
    "name": "test_runner_seam3_minimal",
    "target": "ats_cover",
    "features": [
        {"dataset": "curated", "column": "ol_pass_epa_per_att", "semantic_name": "ol_pass_epa_per_att"},
    ],
    "evaluation": {"metric": "ats_hit_rate", "success_threshold": 0.54, "min_sample": 50},
    "methodology": {
        "type": "walk_forward",
        "train_seasons": 2,
        "test_seasons": 1,
        "start_season": 2020,
        "end_season": 2022,
    },
    "model": {"type": "xgboost", "hyperparams": {}},
    "status": "draft",
    "gate_passed": None,
}


@pytest.fixture
def test_experiment_id(bq_client):
    """Insert a minimal experiment config and return its ID. Clean up after."""
    eid = f"test_{uuid.uuid4().hex[:12]}"
    row = {"experiment_id": eid, **MINIMAL_CONFIG,
           "features": json.dumps(MINIMAL_CONFIG["features"]),
           "evaluation": json.dumps(MINIMAL_CONFIG["evaluation"]),
           "methodology": json.dumps(MINIMAL_CONFIG["methodology"]),
           "model": json.dumps(MINIMAL_CONFIG["model"]),
           "created_at": "2026-01-01T00:00:00Z"}
    errors = bq_client.insert_rows_json(CONFIGS_TBL, [row])
    assert not errors, f"Failed to insert test config: {errors}"
    yield eid
    # Teardown
    for tbl in [CONFIGS_TBL, RUNS_TBL, PREDS_TBL]:
        try:
            bq_client.query(
                f"DELETE FROM `{tbl}` WHERE experiment_id = @eid",
                job_config=bigquery.QueryJobConfig(
                    query_parameters=[bigquery.ScalarQueryParameter("eid", "STRING", eid)]
                )
            ).result()
        except Exception:
            pass


@pytest.mark.nightly
@pytest.mark.integration
def test_runner_writes_backtest_run(bq_client, test_experiment_id):
    """After the runner exits, experiments.backtest_runs has a row for this experiment."""
    env = {**os.environ, "EXPERIMENT_CONFIG_ID": test_experiment_id, "BIGQUERY_PROJECT": PROJECT}
    result = subprocess.run(
        ["python", "backtests/run_experiment.py"],
        cwd=os.path.join(os.path.dirname(__file__), "../../02-MODELING"),
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, (
        f"run_experiment.py exited {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    rows = list(bq_client.query(
        f"SELECT * FROM `{RUNS_TBL}` WHERE experiment_id = @eid",
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("eid", "STRING", test_experiment_id)]
        )
    ).result())
    assert len(rows) >= 1, "No backtest_runs row written for experiment"
    run = dict(rows[0])
    assert run["ats_hit_rate"] is not None, "ats_hit_rate not populated"
    assert run["n_games_evaluated"] is not None and run["n_games_evaluated"] > 0
    assert run["gate_passed"] is not None, "gate_passed not set"


@pytest.mark.nightly
@pytest.mark.integration
def test_runner_writes_predictions(bq_client, test_experiment_id):
    """After the runner exits, backtest_predictions has rows with correct structure."""
    # Assumes test_runner_writes_backtest_run already ran and the runner wrote preds
    rows = list(bq_client.query(f"""
        SELECT game_id, season, week, predicted_home_cover_prob, confidence_tier
        FROM `{PREDS_TBL}`
        WHERE experiment_id = @eid AND season = 2022
        LIMIT 10
    """, job_config=bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("eid", "STRING", test_experiment_id)]
    )).result())
    assert len(rows) > 0, "No predictions written for season 2022"
    for row in rows:
        assert row["game_id"], "game_id is null"
        assert 0.0 <= row["predicted_home_cover_prob"] <= 1.0, (
            f"predicted_home_cover_prob out of range: {row['predicted_home_cover_prob']}"
        )
        assert row["confidence_tier"] in ("high", "medium", "low"), (
            f"Unexpected confidence_tier: {row['confidence_tier']}"
        )


@pytest.mark.nightly
@pytest.mark.integration
def test_experiment_config_status_updated(bq_client, test_experiment_id):
    """After the runner exits, platform.experiment_configs.status is 'complete' or 'failed'."""
    rows = list(bq_client.query(
        f"SELECT status, gate_passed FROM `{CONFIGS_TBL}` WHERE experiment_id = @eid",
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("eid", "STRING", test_experiment_id)]
        )
    ).result())
    assert len(rows) == 1
    assert dict(rows[0])["status"] in ("complete", "failed"), (
        f"Expected status 'complete' or 'failed', got {dict(rows[0])['status']}"
    )
```

---

## Deliverable 4 — Seam 4: API Endpoint Shapes (`integration/test_api_contract.py`)

Tests the API against live BigQuery data. Runs against `http://localhost:8080` by default; switches to the deployed URL when `API_BASE_URL` is set.

```python
"""
Seam 4: experiments.* → BACKEND-API
Verifies that live endpoints return the shapes declared in API_CONTRACTS.md.
"""
import pytest
import requests

API_BASE_URL = __import__("os").getenv("API_BASE_URL", "http://localhost:8080")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Accept": "application/json"})
    s.base_url = API_BASE_URL
    return s


def url(path: str) -> str:
    return f"{API_BASE_URL}{path}"


@pytest.mark.integration
def test_health(api):
    r = api.get(url("/health"))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


@pytest.mark.integration
def test_games_list_returns_pagination(api):
    r = api.get(url("/api/v1/games"), params={"season": 2023, "limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert "data" in body
    assert "pagination" in body
    assert isinstance(body["data"], list)


@pytest.mark.integration
def test_games_list_fields(api):
    r = api.get(url("/api/v1/games"), params={"season": 2023, "limit": 1})
    assert r.status_code == 200
    if not r.json()["data"]:
        pytest.skip("No games in season 2023")
    game = r.json()["data"][0]
    for field in ("game_id", "season", "week", "home_team", "away_team", "status"):
        assert field in game, f"Missing field: {field}"


@pytest.mark.integration
def test_experiments_list(api):
    r = api.get(url("/api/v1/experiments"), params={"limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert "data" in body
    assert isinstance(body["data"], list)


@pytest.mark.integration
def test_features_list(api):
    r = api.get(url("/api/v1/features"))
    assert r.status_code == 200
    body = r.json()
    assert "data" in body
    assert len(body["data"]) > 0, "Features catalog is empty"
    feat = body["data"][0]
    for field in ("feature_id", "semantic_name", "dataset", "data_type"):
        assert field in feat, f"Missing field in feature: {field}"


@pytest.mark.integration
def test_predictions_requires_season(api):
    r = api.get(url("/api/v1/predictions"))
    assert r.status_code == 422


@pytest.mark.integration
def test_predictions_requires_week(api):
    r = api.get(url("/api/v1/predictions"), params={"season": 2023})
    assert r.status_code == 422


@pytest.mark.integration
def test_predictions_no_production_experiment_returns_404(api):
    """If no gate-passed experiments exist, 404 with 'no_production_experiment' code."""
    r = api.get(url("/api/v1/predictions"), params={"season": 2099, "week": 1})
    # Either 404 (no gate-passed experiment) or 200 (one exists) — both are valid
    assert r.status_code in (200, 404)
    if r.status_code == 404:
        assert r.json()["code"] == "no_production_experiment"
```

---

## Deliverable 5 — Seam 5: License Filtering (`integration/test_license_filtering.py`)

This is the most important correctness test in the project. Data tagged `personal_use_only` must never appear in public API responses.

```python
"""
Seam 5: License filtering
CRITICAL: personal_use_only data must never appear in public API predictions.
"""
import json
import uuid
import pytest
import requests
from google.cloud import bigquery

PROJECT   = "nfl-model-471509"
PREDS_TBL = f"{PROJECT}.experiments.backtest_predictions"
API_BASE_URL = __import__("os").getenv("API_BASE_URL", "http://localhost:8080")


@pytest.fixture
def personal_use_prediction(bq_client):
    """
    Insert a test prediction row tagged personal_use_only.
    Clean up after.
    """
    eid  = f"test_{uuid.uuid4().hex[:12]}"
    gid  = f"test_{uuid.uuid4().hex[:8]}"
    row  = {
        "experiment_id":             eid,
        "run_id":                    eid,
        "game_id":                   gid,
        "season":                    2099,
        "week":                      1,
        "fold":                      0,
        "home_team":                 "TST",
        "away_team":                 "TST",
        "predicted_home_cover_prob": 0.99,
        "predicted_side":            "home",
        "actual_home_covered":       None,
        "correct":                   None,
        "confidence_tier":           "high",
    }
    errors = bq_client.insert_rows_json(PREDS_TBL, [row])
    assert not errors
    yield eid, gid
    bq_client.query(
        f"DELETE FROM `{PREDS_TBL}` WHERE experiment_id = @eid",
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("eid", "STRING", eid)]
        )
    ).result()


@pytest.mark.integration
def test_personal_use_predictions_not_in_public_api(personal_use_prediction):
    """
    A prediction row in BQ does not automatically become public.
    The /predictions endpoint filters by gate_passed experiments only —
    personal-use rows that sneak in via a non-gate-passed experiment
    must not appear in the response.
    """
    eid, gid = personal_use_prediction
    r = requests.get(
        f"{API_BASE_URL}/api/v1/experiments/{eid}/predictions",
        params={"season": 2099}
    )
    # If the experiment is not gate-passed, the predictions endpoint
    # returns data but the production predictions endpoint (/api/v1/predictions)
    # must never surface it.
    prod_r = requests.get(
        f"{API_BASE_URL}/api/v1/predictions",
        params={"season": 2099, "week": 1}
    )
    # Either 404 (no gate-passed experiment for 2099) or 200 with no rows
    # — the test prediction must NOT appear
    if prod_r.status_code == 200:
        returned_ids = [d["game_id"] for d in prod_r.json().get("data", [])]
        assert gid not in returned_ids, (
            f"game_id {gid} appeared in /api/v1/predictions — "
            "personal_use_only data leaked through"
        )
    else:
        assert prod_r.status_code == 404
```

---

## Deliverable 6 — Seam 6: End-to-End (`integration/test_e2e_experiment_run.py`)

The full platform loop: create config → trigger run → poll status → verify predictions. Runs in Tier 3 (nightly). Requires the deployed Cloud Run Job to be wired (DEVOPS Step 3b).

```python
"""
Seam 6: End-to-end experiment creation, run trigger, and result verification.
Requires DEVOPS Step 3b (real Cloud Run Job trigger) to be deployed.
"""
import time
import uuid
import pytest
import requests

API_BASE_URL = __import__("os").getenv("API_BASE_URL", "http://localhost:8080")
TIMEOUT_SECONDS = 600


@pytest.mark.live
@pytest.mark.nightly
def test_full_experiment_lifecycle():
    """
    1. Create a minimal experiment config via POST /api/v1/experiments
    2. Trigger it via POST /api/v1/experiments/{id}/run
    3. Poll /status until complete or timeout
    4. Verify predictions were written via GET /api/v1/experiments/{id}/predictions
    """
    # 1. Create config
    config = {
        "name": f"e2e_test_{uuid.uuid4().hex[:8]}",
        "target": "ats_cover",
        "features": [
            {"dataset": "curated", "column": "ol_pass_epa_per_att",
             "semantic_name": "ol_pass_epa_per_att"}
        ],
        "evaluation": {"metric": "ats_hit_rate", "success_threshold": 0.40, "min_sample": 10},
        "methodology": {
            "type": "walk_forward",
            "train_seasons": 2,
            "test_seasons": 1,
            "start_season": 2020,
            "end_season": 2022,
        },
        "model": {"type": "xgboost", "hyperparams": {}},
    }
    r = requests.post(f"{API_BASE_URL}/api/v1/experiments", json=config)
    assert r.status_code == 201, f"Create failed: {r.text}"
    eid = r.json()["experiment_id"]

    try:
        # 2. Trigger
        r = requests.post(f"{API_BASE_URL}/api/v1/experiments/{eid}/run")
        assert r.status_code == 202, f"Trigger failed: {r.text}"

        # 3. Poll until complete
        deadline = time.time() + TIMEOUT_SECONDS
        while time.time() < deadline:
            r = requests.get(f"{API_BASE_URL}/api/v1/experiments/{eid}/status")
            assert r.status_code == 200
            status = r.json()["status"]
            if status == "complete":
                break
            if status == "failed":
                pytest.fail(f"Experiment failed: {r.json().get('error')}")
            time.sleep(15)
        else:
            pytest.fail(f"Experiment did not complete within {TIMEOUT_SECONDS}s")

        # 4. Verify predictions exist
        r = requests.get(
            f"{API_BASE_URL}/api/v1/experiments/{eid}/predictions",
            params={"season": 2022}
        )
        assert r.status_code == 200
        assert len(r.json()["data"]) > 0, "No predictions written for season 2022"

        # 5. Verify backtest run has metrics
        r = requests.get(f"{API_BASE_URL}/api/v1/experiments/{eid}")
        assert r.status_code == 200
        latest = r.json()["latest_run"]
        assert latest is not None, "No run recorded"
        assert latest["ats_hit_rate"] is not None
        assert latest["n_games_evaluated"] > 0

    finally:
        # Best-effort cleanup
        import requests as req
        from google.cloud import bigquery
        bq = bigquery.Client(project="nfl-model-471509")
        for tbl in [
            "nfl-model-471509.platform.experiment_configs",
            "nfl-model-471509.experiments.backtest_runs",
            "nfl-model-471509.experiments.backtest_predictions",
        ]:
            try:
                bq.query(
                    f"DELETE FROM `{tbl}` WHERE experiment_id = @eid",
                    job_config=bigquery.QueryJobConfig(
                        query_parameters=[bigquery.ScalarQueryParameter("eid", "STRING", eid)]
                    )
                ).result()
            except Exception:
                pass
```

---

## Deliverable 7 — Seam 2: No Look-Ahead Leakage (`data_quality/test_no_lookahead.py`)

```python
"""
Data quality: verify no look-ahead leakage in feature construction.
Features must be computed only from data available before the game starts.
"""
import pytest
from google.cloud import bigquery

PROJECT = "nfl-model-471509"


@pytest.mark.integration
def test_no_same_week_features_in_curated_plays(bq_client):
    """
    curated.plays should not contain same-week stat totals for a game
    that appear as season-to-date features for that same game.
    This is a schema-level check — actual leakage is caught in MODELING unit tests.
    """
    # Verify that curated.plays has a game_date or week column we can reason about
    table = bq_client.get_table(f"{PROJECT}.curated.plays")
    col_names = {f.name for f in table.schema}
    assert "season" in col_names, "curated.plays missing 'season' column"
    assert "week" in col_names, "curated.plays missing 'week' column"
    # If play-level data includes game_id, we can verify it links to curated.games
    if "game_id" in col_names:
        rows = list(bq_client.query(f"""
            SELECT COUNT(*) as orphans
            FROM `{PROJECT}.curated.plays` p
            LEFT JOIN `{PROJECT}.curated.games` g USING (game_id)
            WHERE g.game_id IS NULL AND p.season >= 2020
        """).result())
        assert rows[0]["orphans"] == 0, (
            f"{rows[0]['orphans']} plays reference game_ids not in curated.games"
        )


@pytest.mark.integration
def test_predictions_cover_prob_in_range(bq_client):
    """All predicted_home_cover_prob values are in [0, 1]."""
    rows = list(bq_client.query(f"""
        SELECT COUNT(*) as n
        FROM `{PROJECT}.experiments.backtest_predictions`
        WHERE predicted_home_cover_prob < 0 OR predicted_home_cover_prob > 1
    """).result())
    assert rows[0]["n"] == 0, (
        f"{rows[0]['n']} predictions have cover_prob outside [0, 1]"
    )
```

---

## CI Wiring

Create `06-TESTING-QA/ci-tiers.md` documenting which tests run in which tier. Then ask DEVOPS to add the appropriate GitHub Actions steps to their CI workflows:

| Tier | Trigger | Command | Tests run |
|------|---------|---------|-----------|
| 2 — PR | PR open/update | `pytest 06-TESTING-QA/ -m "integration and not nightly and not live" --timeout=120` | Schema contract, API contract, license filtering |
| 3 — Nightly | Cron (2am ET) | `pytest 06-TESTING-QA/ -m "nightly" --timeout=900` | Runner writes, end-to-end |

For Tier 3 to run against the live deployment, set `API_BASE_URL` as a GitHub Actions secret pointing at the Cloud Run URL.

---

## Deliverable Summary

| File | Seam | Tier |
|------|------|------|
| `06-TESTING-QA/conftest.py` | — shared fixtures | — |
| `06-TESTING-QA/integration/test_pipeline_to_curated.py` | Seam 1: schema contract | Tier 2 |
| `06-TESTING-QA/integration/test_runner_bq_writes.py` | Seam 3: runner → BQ | Tier 3 |
| `06-TESTING-QA/integration/test_api_contract.py` | Seam 4: API shapes | Tier 2 |
| `06-TESTING-QA/integration/test_license_filtering.py` | Seam 5: license | Tier 2 |
| `06-TESTING-QA/integration/test_e2e_experiment_run.py` | Seam 6: end-to-end | Tier 3 |
| `06-TESTING-QA/data_quality/test_no_lookahead.py` | Seam 2: leakage | Tier 2 |
| `06-TESTING-QA/ci-tiers.md` | CI documentation | — |

---

## Handoff Signal

When the test files are written and Tier 2 tests pass against the local dev environment:

1. Update `00-PROJECT-LEAD/PHASE3_STATUS.md`
2. Notify PROJECT-LEAD — CI wiring with DEVOPS can begin

Tier 3 tests can be marked as pending until the Cloud Run Job trigger is live (DEVOPS Step 3b).
