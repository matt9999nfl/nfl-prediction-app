# CI Tier Structure — Testing-QA Phase 3

## Overview

This document defines which tests run in which CI tier and the commands for each.

---

## Tier 2 — Pull Requests (Tier 2)

**Trigger:** On PR open/update

**Purpose:** Fast feedback loop during development (< 5 minutes). Validates seams with live BigQuery data but no long-running runners.

**Command:**
```bash
pytest 06-TESTING-QA/ \
  -m "integration and not nightly and not live" \
  --timeout=120
```

**Tests included:**
- `test_pipeline_to_curated.py` — Seam 1: schema contract
- `test_api_contract.py` — Seam 4: API endpoint shapes  
- `test_license_filtering.py` — Seam 5: license filtering (critical)
- `data_quality/test_no_lookahead.py` — Seam 2: data quality checks

**Expected duration:** 2–3 minutes

**Allowed failures:** None (all are correctness-critical)

---

## Tier 3 — Nightly (Full Integration)

**Trigger:** Cron schedule (2:00 AM ET)

**Purpose:** Comprehensive validation with slow runner invocations and end-to-end flows. Validates the full platform loop.

**Command:**
```bash
pytest 06-TESTING-QA/ \
  -m "nightly" \
  --timeout=900 \
  -v
```

**Tests included:**
- `integration/test_runner_bq_writes.py` — Seam 3: runner → BQ writes
- `integration/test_e2e_experiment_run.py` — Seam 6: end-to-end (requires Cloud Run Job live)

**Expected duration:** 10–15 minutes

**Environment:**
- `API_BASE_URL`: If set, tests run against deployed Cloud Run URL. Otherwise defaults to `http://localhost:8080`.
- Must have `GOOGLE_APPLICATION_CREDENTIALS` set to a service account with BQ write access to `test_*` dataset prefixes.

**Allowed failures:** `test_e2e_experiment_run.py` can be marked `@pytest.mark.skip` until DEVOPS Step 3b (Cloud Run Job trigger) is live.

---

## GitHub Actions Configuration

### Tier 2 Step (PR)

```yaml
- name: Run Tier 2 Tests (PR)
  run: |
    cd nfl-prediction-app
    pip install -r 06-TESTING-QA/requirements.txt
    pytest 06-TESTING-QA/ \
      -m "integration and not nightly and not live" \
      --timeout=120 \
      -v
```

### Tier 3 Step (Nightly)

```yaml
- name: Run Tier 3 Tests (Nightly)
  if: github.event_name == 'schedule'
  env:
    GOOGLE_APPLICATION_CREDENTIALS: ${{ secrets.GCP_SA_CREDENTIALS }}
    API_BASE_URL: ${{ secrets.API_BASE_URL }}
  run: |
    cd nfl-prediction-app
    pip install -r 06-TESTING-QA/requirements.txt
    pytest 06-TESTING-QA/ \
      -m "nightly" \
      --timeout=900 \
      -v
```

---

## Test Responsibility Matrix

| Seam | Test File | Tier | Owner | Status |
|------|-----------|------|-------|--------|
| 1 (pipeline → curated) | `test_pipeline_to_curated.py` | 2 | DATA-PIPELINE | ✓ Runs every PR |
| 2 (no look-ahead) | `test_no_lookahead.py` | 2 | TESTING-QA | ✓ Runs every PR |
| 3 (runner → BQ) | `test_runner_bq_writes.py` | 3 | TESTING-QA | ✓ Nightly only |
| 4 (API contract) | `test_api_contract.py` | 2 | TESTING-QA | ✓ Runs every PR |
| 5 (license filtering) | `test_license_filtering.py` | 2 | TESTING-QA | ✓ Runs every PR |
| 6 (end-to-end) | `test_e2e_experiment_run.py` | 3 | TESTING-QA | ⏳ Pending DEVOPS Step 3b |

---

## Local Development

### Run Tier 2 locally (fast):
```bash
cd 06-TESTING-QA
pytest -m "integration and not nightly and not live" --timeout=120 -v
```

### Run a single test:
```bash
pytest integration/test_api_contract.py::test_health -v
```

### Run with live API (if deployed):
```bash
API_BASE_URL=https://your-cloud-run-url pytest -m "live" -v
```

---

## Debugging Failed Tests

1. **Tier 2 failures:** Always block PR merge. Check BigQuery connectivity and table schemas.
2. **Tier 3 failures:** Do not block releases (if using scheduled retries). Investigate in next nightly run.
3. **License filtering failure (critical):** Stop all deployments. This indicates data leak risk.

---

## Future Extensions

- Add `@pytest.mark.flaky` for network-dependent tests if needed
- Add `@pytest.mark.performance` for throughput/latency assertions
- Add `@pytest.mark.security` for CORS, auth, and input validation tests
