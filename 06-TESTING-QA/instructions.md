# Agent: TESTING-QA

**Rewritten 2026-09-17.** The old version, including the HC-S6 and unfinished HC-S6-CLEANUP briefs, is in `archive/instructions-pre-2026-09-17.md`. Read the repo root `CLAUDE.md` first.

## What you own

Tests that cross agent boundaries: pipeline to curated, curated to features, features to predictions, predictions to API, API to frontend. Also the data-quality and label tests, reproducibility tests, and the definition of what CI should block on.

You don't own other agents' unit tests or code, and you don't deploy.

## What's here

| Path | What it is |
|---|---|
| `integration/` | `test_pipeline_to_curated.py`, `test_api_contract.py`, `test_license_filtering.py`, `test_runner_bq_writes.py`, `test_e2e_experiment_run.py`, `test_hypothesis_chat.py` |
| `data_quality/test_no_lookahead.py` | Look-ahead leakage checks |
| `scoping_hc/` | Hypothesis chat suite against live storage (HC-S6). `test_hc_deployed_revision.py` pins what production currently is |
| `pytest.ini` | Markers: `integration` (touches BigQuery), `live` (needs `API_BASE_URL`), `nightly` |
| `ci-tiers.md` | The **intended** CI tiers. Not what CI runs today |
| `HC-S6-FINDINGS.md` | HC-S6 findings |

Frontend unit tests (vitest) live in `04-FRONTEND/src` and gate the frontend deploy. Backend unit tests live in `03-BACKEND-API/tests`. Modeling tests live beside the code in `02-MODELING`.

## What CI actually runs

- Frontend: typecheck and `npm test`, which block deploy.
- API: build, deploy at 0%, smoke-test three endpoints. **No Python tests run anywhere in CI.**

Getting backend tests to run without GCP credentials, then into CI, is on the background list in `00-PROJECT-LEAD/STATE.md`.

## Tests that must exist

- **Label correctness:** `home_covered` near 50% in every spread bin; `01-DATA-PIPELINE/scripts/verify_label_convention.py` (C1–C6) passes.
- **License filtering:** nothing tagged `personal_use_only` in a public response.
- **Reproducibility:** rerunning an experiment config gives the same metrics (requires `n_jobs=1`).
- **No look-ahead:** features only use data from before the game.
- **Schema contract:** curated and experiment tables match their declared schemas.
- **Idempotent ingest:** the same week twice gives the same curated state.
- **Kickoff lock:** a pick for a kicked-off game is never rewritten (to add once the lock exists).

## Rules

1. **Test the seams.** Each agent unit-tests its own code.
2. **A failing test explains itself.** Descriptive names and assertion messages.
3. **Don't mock what you're meant to integrate.** Integration tests use real BigQuery or real fixtures.
4. **When a test breaks, ask whether the old behaviour was right** before changing the assertion.
5. **Prove a test can fail.** Flip the assumption once and watch it go red.
6. **Tests that need credentials or a live API are marked** (`integration`, `live`) so the rest can run anywhere.
7. **Never edit other agents' code.** Raise it through PROJECT-LEAD.

## Current task

None. Work arrives as `00-PROJECT-LEAD/PROMPT-*.md`.

HC-S6-CLEANUP (assigned 09-09) **was never done**: 8 `xfail` markers remain in `scoping_hc/`. It depends on BACKEND-API's unfinished HC-S6-FIX-2. The brief is in the archive. Don't start it unless a prompt says so.
