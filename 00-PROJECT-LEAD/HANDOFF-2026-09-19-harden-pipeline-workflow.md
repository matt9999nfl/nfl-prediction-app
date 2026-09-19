Goal achieved: yes.

Commit: `d4329fd` — fix: harden pipeline-deploy.yml before first dispatch (B1-2b follow-up)

## The three fixes

**A — kill-switch didn't cover a hang.**
Before: no `timeout-minutes` anywhere; GitHub's 6-hour default applied. Revert step
was `if: steps.verify.outcome == 'failure'`, which a cancelled/timed-out job skips.
After: `timeout-minutes: 30` on the `deploy` job (comment justifies it — checkout/
auth/setup ~1-2min + build ~2-4min + push ~1-2min + repoint instant + the
verification run's historical ~12min = ~20-25min worst case observed; 30 leaves
headroom). Revert condition changed to `always() && steps.verify.outcome != 'success'`,
so a cancel or timeout now reverts too. `continue-on-error: true` on the verify step
was left untouched — it's still what lets the revert run after an ordinary failure.

**B — window guard measured dispatch time, not finish time.**
Before: all four scheduled windows used a 30-minute `before` buffer against a
workflow that itself runs ~20-25 minutes — the same arithmetic error as the
2026-09-18 incident (QUESTIONS.md), just relocated.
After: raised `before` to 90 minutes on all four windows (chose "raise the buffer"
over "re-check the clock before verification" — it's a one-line change to numbers
already being computed correctly, versus duplicating the window-check logic in a
second step; 90 clears the workflow's own worst-case runtime with real margin).
`after` buffers unchanged (not flagged as a defect).

**C — `docker build` ignores `.gcloudignore`.**
Before: no `.dockerignore`; `docker build` doesn't read `.gcloudignore`, so
`new_sources_staging/` (29MB parquet), `__pycache__/`, `*.pyc`, `*.log` all landed
in the build context and image again — exactly what INC-002 (2026-09-07) fixed for
the Cloud Build path only.
After: added `01-DATA-PIPELINE/.dockerignore` mirroring `.gcloudignore`'s patterns
exactly, plus a sync-note comment in both files pointing at each other.

Build-context size (measured by directory size, not an actual `docker build` —
scope forbade building any image): **~30.13 MB before → ~0.26 MB after** (29.67MB
`new_sources_staging/`, 174KB `__pycache__/`, 25KB `*.log` excluded; no `.git/`
present under `01-DATA-PIPELINE/` to begin with).

## Verification

- Both workflow copies (`​.github/workflows/pipeline-deploy.yml`,
  `05-DEVOPS/ci/pipeline-deploy.yml`) parse as valid YAML (checked with `pyyaml`).
- `diff` between the two copies exits 0 — byte-identical.
- `continue-on-error: true` still present on the "Execute verification run" step.
- Nothing dispatched, built, repointed, or executed — all changes are static file
  edits, verified by directory-size measurement only.

## Tests before/after

No test suite covers this workflow file; none run. N/A.

## Open

None from this prompt. First dispatch is unblocked — the three named defects are
fixed and nothing else in the workflow was touched.

## Note

`00-PROJECT-LEAD/PLAN-BUCKET1-DATA-COVERAGE.md` was already modified (uncommitted)
at session start, unrelated to this prompt — left as-is, not touched or committed.
