# NFL Prediction App

An app for running experiments on NFL data. A hypothesis gets stated, scoped, run, measured and recorded, without hand-editing code. The app also makes live weekly picks for the 2026 season and grades them.

Finding an edge is active work, done through the app: backtests, reverse experiments and per-game explanations of why the model made each pick. The project started from an offensive-line hypothesis; that was tested and is now one finished experiment, not the project's goal. See `00-PROJECT-LEAD/PROJECT-CHARTER.md`.

*Rewritten 2026-09-17. The previous version is in `00-PROJECT-LEAD/archive/README-pre-2026-09-17.md`.*

## Live

| | |
|---|---|
| Dashboard | `http://34.49.20.115` |
| API | `https://nfl-backend-api-rmaehdhzhq-uc.a.run.app` (`/health` shows the deployed commit) |
| GCP project | `nfl-model-471509` |

## How the repo is organised

Work is split across seven agent folders. Each has an `instructions.md` saying what it owns.

| Folder | Owns |
|---|---|
| `00-PROJECT-LEAD` | Plans, task prompts, reviews, decisions, current state (`STATE.md`) |
| `01-DATA-PIPELINE` | nflverse data and line snapshots into BigQuery, validation |
| `02-MODELING` | Features, models, the experiment runner, backtests, live picks |
| `03-BACKEND-API` | FastAPI service, feature catalog, hypothesis chat backend |
| `04-FRONTEND` | React dashboard |
| `05-DEVOPS` | Cloud Run, Scheduler, Terraform, CI/CD, alerting |
| `06-TESTING-QA` | Cross-agent and data-quality tests |

Shared design documents are in `docs/`: `ARCHITECTURE.md`, `API_CONTRACTS.md`, `DECISIONS.md` (ADR log), `DATA_SOURCES.md`.

## How work gets done

1. Matt and PROJECT-LEAD (a Cowork session in `00-PROJECT-LEAD`) agree what to build.
2. PROJECT-LEAD writes a task prompt to `00-PROJECT-LEAD/PROMPT-<slug>.md`.
3. Matt starts a Claude Code session at the repo root and points it at the prompt. `CLAUDE.md` at the root gives that session the standing rules.
4. The session writes `00-PROJECT-LEAD/HANDOFF-<date>-<slug>.md` when done, or a question to `00-PROJECT-LEAD/QUESTIONS.md` if stuck.

## Architecture in one picture

```
nflverse data (scheduled) + uploaded datasets
        ↓
DATA-PIPELINE jobs → BigQuery (raw_nflfastr, raw_lines, curated, platform, experiments)
        ↓
Experiment runner + weekly production refresh (Cloud Run jobs)
        ↓
FastAPI on Cloud Run → React dashboard (Cloud Storage + CDN)
```

Details: `docs/ARCHITECTURE.md`.

## Principles

- **Experiments run through the app,** as recorded configs and runs, not as one-off scripts (ADR-011).
- **Each experiment sets its own success criteria.** There is no project-level gate (ADR-006).
- **Features are named for what they measure,** not for the vendor they came from.
- **Remote-friendly.** Anything weekly runs on a schedule or from an endpoint.
- **Respect data source terms.** Rate limits, robots.txt, and license tags on anything served publicly.
