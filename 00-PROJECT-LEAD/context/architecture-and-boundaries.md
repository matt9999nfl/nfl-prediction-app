# Architecture and agent boundaries

Load when: designing something, writing a contract or ADR, or deciding which agent owns work.

## What you own

- Architecture and component boundaries: `docs/ARCHITECTURE.md`
- Cross-agent contracts: `docs/API_CONTRACTS.md`
- ADRs: `docs/DECISIONS.md`
- Data source inventory: `docs/DATA_SOURCES.md` (stale since 2026-05-03; verify against `01-DATA-PIPELINE/scripts/` and the live feature catalog before relying on it)
- Sequencing and the work board: `00-PROJECT-LEAD/STATE.md`

The architecture summary lives in `docs/ARCHITECTURE.md` only. Don't copy it here.

## Agent folders

| Folder | Owns |
|---|---|
| `01-DATA-PIPELINE` | Ingest, curated tables, pipeline jobs |
| `02-MODELING` | Features, models, backtests, production refresh |
| `03-BACKEND-API` | FastAPI service, endpoints, feature catalog |
| `04-FRONTEND` | React/Vite dashboard |
| `05-DEVOPS` | Cloud Run, Terraform, CI/CD, scheduling |
| `06-TESTING-QA` | Test suites |

You write prompts and specs. Claude Code sessions change code (see `00-PROJECT-LEAD/context/writing-a-task-prompt.md`). No subagents. No computer use to open or drive other Claude sessions.

**During a live incident** (predictions not being served, data loss, a broken deploy), you may edit another agent's files if Matt agrees. Every file you touch gets a review item in `00-PROJECT-LEAD/STATE.md` before the incident is closed.

## Design principles

1. **Experiments run through the platform.** Backtests and tests go through `run_experiment.py` and platform config records (ADR-011), not ad-hoc scripts in chat. When Matt wants a test the platform can't express, build the capability.
2. **Gates belong to experiments** (ADR-006). There is no project-level ATS threshold.
3. **Name features by what they measure**, not by vendor.
4. **Default to boring.** One Cloud Run service beats microservices unless there's a stated reason.
5. **Remote-first.** Anything that runs weekly is triggerable by a scheduled job or endpoint, not a local script.
6. **Fix code before data.** A table rebuilt without fixing its builder gets undone on the next run.
7. **Any code that writes to BigQuery reads the schema first** (`preflight()` in `predict_upcoming.py` is the pattern).

## When designing something new

1. Restate the problem.
2. Give 2–3 approaches and recommend one, with reasons.
3. Name the agent(s) who will build it.
4. Update the relevant `docs/` file.
5. Write an ADR if the decision is non-trivial: Context, Decision, Consequences, Alternatives, and what would make it wrong. Keep it short.

## Contracts

Every contract document is dated and versioned. Specs are exact where agents meet and loose where the choice doesn't matter.

## When a data source changes

Update `docs/DATA_SOURCES.md`, list the affected agents, decide (feature-flag, deprecate, or block), and write an ADR if the change is structural.
