# PROMPT-PYTHON-TESTS-IN-CI — no Python test in this repo has ever run in CI

Start in: C:\Users\OEM\OneDrive\Desktop\nfl-prediction-app
Written: 2026-09-19 by PROJECT-LEAD. Stage B1-7 of `PLAN-BUCKET1-DATA-COVERAGE.md`.

## Why

`grep -rn pytest .github/workflows/` returns nothing. The frontend workflow runs `npm test`;
no workflow runs Python tests at all. So the 251 modeling tests, the data-pipeline tests, and
the 11 tests added with the injury capture on 2026-09-19 have only ever run when a person ran
them locally. Test counts are quoted in every handoff as evidence, and nothing enforces them.

This is the third instance of the same failure family in one week: line capture that never
ran for nine days, a freshness check whose crash was the only thing that surfaced a missing
IAM grant, and now a test suite that cannot fail a build. A test that does not run is
indistinguishable from a test that passes.

There is also a live symptom: `01-DATA-PIPELINE/scripts/test_snapshot_lines.py` fails to
import when `pytest` runs from the repo root (noted 2026-09-19, not fixed). There is no
`pytest.ini`, `pyproject.toml`, `setup.cfg` or root `conftest.py` anywhere in the repo, so
import resolution depends entirely on the directory a person happens to be standing in.
`snapshot_lines.py` is, of all things, the component whose silent failure started this.

## Task

Python tests run in CI on every push and pull request, and a failing test fails the build.

Two parts, in order:

1. **Make the suite runnable from the repo root.** Add the minimal pytest configuration that
   fixes import resolution — root config plus whatever `conftest.py` the layout needs. Do not
   restructure packages or move files to achieve it.
2. **Add a test workflow.** Run the suite on push and pull request. Do not bolt this onto
   `api-deploy.yml` or `frontend-deploy.yml`; a test failure should not be tangled with a
   deploy.

Known obstacle, already documented in `STATE.md`: 29 backend tests fail without GCP
credentials. Do not paper over that by granting CI credentials, and do not delete the tests.
Separate the suite into what can run without credentials and what cannot, get the first group
green and enforced, and report exactly which tests are excluded and why. A smaller enforced
suite beats a larger unenforced one.

Report the true count: how many tests exist, how many run in CI, how many are excluded.

## Read first
- `00-PROJECT-LEAD/PROJECT-CHARTER.md`, `STATE.md` (Decisions, and the pipeline/tests background items)
- `00-PROJECT-LEAD/context/talking-to-matt.md`
- `.github/workflows/frontend-deploy.yml` — the existing gating pattern to follow
- `06-TESTING-QA/instructions.md`
- `01-DATA-PIPELINE/scripts/test_snapshot_lines.py` — the live import symptom

## Scope
Allowed: a new test workflow, root pytest config, `conftest.py` files, `06-TESTING-QA/**`,
and marker/skip decorators on tests that need credentials.
Must not: change any test's assertions, delete or `xfail` a failing test to make CI green,
grant CI any GCP credentials, change production code to suit a test, or touch Terraform.

## Kill-switch
Stop, write to `00-PROJECT-LEAD/QUESTIONS.md`, and tell Matt if: getting the suite green would
need a change to production code or to an assertion; more than the known 29 tests fail without
credentials; fixing imports would need files moved or packages restructured; or the full suite
takes long enough in CI to be worth a discussion about cost.

## Acceptance (each line true or false)
- [ ] `pytest` runs from the repo root and collects `test_snapshot_lines.py` successfully.
- [ ] A test workflow runs on push and pull request, separate from both deploy workflows.
- [ ] A deliberately failing test fails the workflow — demonstrated, then reverted.
- [ ] Total test count, CI-run count, and excluded count are all reported, with the reason
      for each exclusion.
- [ ] No assertion changed, no test deleted, no test newly marked `xfail` to get green.
- [ ] No GCP credentials added to CI.

## Returns-with
`00-PROJECT-LEAD/HANDOFF-2026-09-<dd>-python-tests-in-ci.md`: goal achieved yes/no (first
line), commit SHA(s), the three test counts, the list of excluded tests with reasons, proof
that a failing test fails the build, and anything left open.
