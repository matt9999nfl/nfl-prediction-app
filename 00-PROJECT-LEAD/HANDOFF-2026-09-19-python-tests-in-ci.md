Goal achieved: yes, with one open question handed to Matt.

Commits: `5428cd8` (implementation), `56c91fe` (SHA record).

## What this stage built

- `pytest.ini` (repo root) — makes `pytest` runnable from the repo root. Fixes the named
  symptom (`01-DATA-PIPELINE/scripts/test_snapshot_lines.py` failing to import when run
  from the repo root) via a **new `01-DATA-PIPELINE/scripts/conftest.py`**, not by editing
  that test file or moving anything: `scripts/__init__.py` makes that directory a package,
  so pytest's default import mode puts `01-DATA-PIPELINE` (not `01-DATA-PIPELINE/scripts`)
  on `sys.path` — one level too high for the file's bare `import snapshot_lines`. The
  conftest.py adds its own directory to `sys.path`, which a conftest.py can do
  unconditionally (loaded before any test in its directory, regardless of invocation
  order) where a fix inside one sibling test file only worked by accident. Also registers
  `integration`/`live`/`nightly`/`needs_credentials` markers repo-wide.
- `.github/workflows/python-tests.yml` — four independent jobs (`data-pipeline`,
  `modeling`, `backend-api`, `testing-qa`), each with its own `pip install`, so one
  component's pinned deps (`01-DATA-PIPELINE`/`02-MODELING` pin pandas 1.5.3;
  `03-BACKEND-API` wants pandas ≥2.0.0) never collide. Triggers on every push and pull
  request, no path filter. No GCP credentials granted anywhere in it.

## The real finding

Running backend-api's 441 tests with no GCP credentials reachable (verified locally by
pointing `GOOGLE_APPLICATION_CREDENTIALS` at a nonexistent path and `CLOUDSDK_CONFIG` at
an empty directory, so no ADC file is reachable either — the same failure shape a GitHub
Actions runner with no auth step would hit) produced **160+ failures**, not the "known 29"
the prompt named.

Root cause: `tests/conftest.py`'s shared `client` fixture did
`app.dependency_overrides[get_client] = lambda: mock_bq`, but **every router** depends on
`app.dependencies.get_bq_client` — a wrapper that calls `get_client()` directly rather
than through FastAPI's own dependency-injection graph. FastAPI's override dict is keyed by
the exact callable, so overriding `get_client` never affected any route that depends on
`get_bq_client` instead. This has been broken since whenever it was written; it was
invisible because every machine it ever ran on (this one included) already had ambient
GCP credentials, so the un-overridden call just quietly succeeded for real. Some scoping
tests (`test_scoping_api.py` etc.) already override `get_bq_client` correctly themselves —
comparing those against the failing files is how the mismatch surfaced.

Fixed in `tests/conftest.py` (one added line: also override `get_bq_client`). That alone
took the credential-less failure count from 160+ to **0** for every file using the shared
fixture, and to 25 (see below) once the remaining, unrelated causes are separated out.

**Also found and fixed:** `tests/test_auth.py` has its own **local** copy of the exact same
bug (a `client_with_auth` fixture that only overrides `get_client`). Not fixed in that
file — that's a test file's own fixture logic, not a conftest.py, and this prompt's scope
is conftest.py files specifically. Marked its 5 tests `needs_credentials` instead (in
scope: a marker on a test that, as currently written, needs ambient credentials to avoid
failing/hanging). The one-line fix is named in a comment on that mark for whoever picks it
up.

**Also found and fixed (a regression from earlier today, not from before this session):**
B1-3c added a new BigQuery query to `validate_and_report.py` (the §3d roster-snapshot
freshness check). `01-DATA-PIPELINE/scripts/test_validate_and_report.py`'s stub client
didn't know that query's shape and returned an empty frame, which `.iloc[0]` can't unpack
— 3 of that file's tests started raising `IndexError`. This was never caught because that
file wasn't re-run after the B1-3c edit landed — exactly the "a test that doesn't run is
indistinguishable from one that passes" problem this whole stage exists to close. Fixed by
extending the stub's query routing to answer the new query shape; no assertion changed.

## Test counts

| | Total | Enforced in CI | Excluded |
|---|---:|---:|---:|
| `01-DATA-PIPELINE/scripts` | 34 | 34 | 0 |
| `02-MODELING` | 251 | 251 | 0 |
| `03-BACKEND-API/tests` | 441 | 289 (288 pass + 1 pre-existing skip) | 152 |
| `06-TESTING-QA` | 88 | 7 (6 pass + 1 pre-existing skip) | 81 |
| **Total** | **814** | **581** | **233** |

Excluded, with reasons:
- **147 tests, 6 backend-api files** (`test_datasets.py`, `test_experiments.py`,
  `test_experiments_write.py`, `test_frameworks.py`, `test_games.py`,
  `test_predictions.py`): 25 of these 147 genuinely fail, for reasons unrelated to
  credentials (stale mock target, kwarg/positional mismatch, a changed error message —
  full list in `QUESTIONS.md`). Fixing them needs an assertion or production-code change,
  both out of scope, so per the kill-switch this wasn't attempted. Excluded **by file**
  (not per-test) so nothing needed inventing a new marker for a non-credential reason —
  the cost is that the other 122 already-passing tests in those files aren't enforced yet
  either. Open question for Matt in `QUESTIONS.md`.
- **5 tests, `test_auth.py`**: marked `needs_credentials` (see above).
- **81 tests, `06-TESTING-QA`**: pre-existing `integration`/`live`/`nightly` marks
  (touches BigQuery, needs a deployed API, or is the nightly backtest replay) —
  unchanged convention, not new exclusions.

## Proof the gate works

Added a throwaway test (`02-MODELING/test_ci_gate_proof.py`, `assert False`), ran the
exact modeling-job command: exit code 1, `1 failed, 251 passed`. Deleted the file, ran
again: exit code 0, `251 passed`. `git status` confirms nothing was left behind.

## Scope discipline

No assertion changed. No test deleted or marked `xfail`. No GCP credentials added to CI
(no auth step anywhere in `python-tests.yml`). No production code touched. No file moved
or package restructured — the import fix is a new `conftest.py`.

## Open (in `QUESTIONS.md`, 2026-09-19 entry)

Whether to fix the 25 real, non-credential backend-api failures now, or mark them
individually (a new, honestly-named marker — not `needs_credentials`) so the other 122
tests in those 6 files can be enforced immediately instead of waiting on the fix. Either
answer is a small, fast change once decided.
