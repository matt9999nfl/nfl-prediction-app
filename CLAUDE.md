# NFL Prediction App — read this first

Loaded by every Claude Code session in this repo. Written 2026-09-17 by PROJECT-LEAD. Keep it under 80 lines.

## What this project is

An app for running experiments on NFL data (GCP project `nfl-model-471509`). Finding an edge is active work, done through the app. It is not a project about proving the offensive-line hypothesis, and there is no project-level 54% gate. Full framing: `00-PROJECT-LEAD/PROJECT-CHARTER.md`.

## Before you start

1. Read the task prompt you were given (usually `00-PROJECT-LEAD/PROMPT-*.md`) in full.
2. Read the Decisions section of `00-PROJECT-LEAD/STATE.md`. Those are standing rulings; don't re-ask them.
3. Before changing files in an agent folder, read that folder's `instructions.md`:
   `01-DATA-PIPELINE` · `02-MODELING` · `03-BACKEND-API` · `04-FRONTEND` · `05-DEVOPS` · `06-TESTING-QA`
4. Skip old `archive/` folders and dated status documents unless the prompt names them. Several are wrong about the current state.

## Standing rules

- `n_jobs=1` on every model. Parallelise across runs, never inside one.
- Any run whose numbers must match production or count as evidence (reproductions, backtests, grids) runs in the production Linux image, not on Windows. Windows and Linux give different numbers even with identical library versions (found 2026-09-17).
- Existing feature columns never change meaning. New things are new columns.
- Never rewrite a pick or explanation for a game that has kicked off.
- Don't run "Generate predictions" between a week's first kickoff and the end of that week's games.
- May 2026 experiment runs are never used as comparisons or evidence.
- Experiments and backtests go through platform config records and `02-MODELING/backtests/run_experiment.py` (ADR-011), not one-off scripts.
- Code that writes to BigQuery reads the live schema first (`preflight()` in `predict_upcoming.py` is the pattern). Don't write from a remembered schema.
- Fix the code before the data. A table rebuilt without fixing its builder gets undone by the next scheduled run.
- Don't comment on how good the current model is unless Matt asks. Report what results show, neutrally.

## How things deploy (committing is not deploying)

- API: push to `main` touching `03-BACKEND-API/**` runs `.github/workflows/api-deploy.yml`. Check: `/health` returns the commit.
- Frontend: push to `main` touching `04-FRONTEND/**` runs `.github/workflows/frontend-deploy.yml` (typecheck and `npm test` must pass). Check: the `assets/index-*.js` name at `http://34.49.20.115/`.
- Modeling: `02-MODELING` ships in `gcr.io/nfl-model-471509/nfl-experiment-runner`, built by hand with `gcloud builds submit --config cloudbuild.yaml .` from `02-MODELING`. Jobs must then be pointed at the new image digest.
- Data pipeline: `gcr.io/nfl-model-471509/nfl-data-pipeline`, built from `01-DATA-PIPELINE/cloudbuild.yaml`.
- A claim that something is deployed names the commit SHA, bundle name or image digest.

## Working with Matt

- Follow `00-PROJECT-LEAD/context/talking-to-matt.md`: result first, then actions, then explanation.
- Matt is on Windows. Commands you hand him use `cmd.exe` syntax, runnable lines only, with the stop condition under the block.
- Ask before anything that changes production, needs his credentials, or can't be undone.

## When stuck

Write the question to `00-PROJECT-LEAD/QUESTIONS.md` (what you were doing, what you tried), tell Matt, and stop. Don't guess forward.

## When done

Write `00-PROJECT-LEAD/HANDOFF-<date>-<slug>.md`. First line: whether the goal was achieved. Then commits, deploy evidence, experiment or run IDs, test counts before and after, and anything left open.

## Git hygiene

Don't leave `.git/*.lock` files behind. Don't commit `__pycache__/`, `*.pyc`, build output or scratch logs.
