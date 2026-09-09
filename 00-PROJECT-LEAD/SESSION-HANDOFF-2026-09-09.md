# Session handoff — 2026-09-08/09

**Written by:** PROJECT-LEAD · **Covers:** one long session that began as Phase 6 planning and became a season-critical incident

---

## What this session was meant to be, and what it became

It opened as a planning session for the Hypothesis Chat — a Claude interface where Matt states a hypothesis in plain English and the platform scopes, briefs and runs it. That got built through stage 5.

Partway through, a routine season-readiness check found the 2026 ingest had been dead for 115 days. That took over, and it was the right call: the season starts 2026-09-10 and a hypothesis chat over a spine frozen at 8 May would have produced confident, wrong answers all season.

Both threads are now in a good place. Neither is finished.

---

## Part 1 — Phase 6: the Hypothesis Chat

**Built: stages 0-6.** A page where a prose hypothesis becomes an approved, running experiment.

Three structural commitments (ADR-012 in `../docs/DECISIONS.md`):

1. **The chat is a client of the existing write API.** It holds no BigQuery credential and executes no SQL; `dispatch` calls `create_experiment` and `trigger_run` — the wizard's own handlers. It cannot exceed the wizard because it runs the wizard's code. TESTING-QA attacked this with an AST parser and it held.
2. **The question sequence is declared data**, not a prompt. A CI test asserts every required config field is bound by exactly one slot, so a tree that could produce an invalid config fails the build.
3. **The brief is rendered from the config**, never authored alongside it. Approval binds to a hash; dispatch recomputes and refuses a mismatch.

**Stage 2 was deliberately built to work with `ANTHROPIC_API_KEY` unset**, so a complete feature existed before any model was in the loop.

### Then TESTING-QA read it cold and found six defects

91 backend tests were green. They validated the implementation against a model of the world the same author wrote. Running it against real BigQuery broke four things immediately.

| # | Finding | Why it survived |
|---|---|---|
| F1 | `update_answers` never clears `approved_hash` in SQL | The in-memory test `Store` clears it. **The fake was kinder than production**, so the test guarding the core guarantee stayed green while the guarantee was broken |
| F2 | The hash covers the config; the brief also renders three record-only slots | Change the falsifier after approving and the hash does not move. The test output prints two briefs, identical hash, differing in one line — directly beneath the brief's own sentence saying they cannot differ |
| F3 | Governor treats `test_seasons` as a per-fold multiplier; the runner uses it as the stride | They agree only at `test_seasons=1` — the one value the test asserted. At 2 it over-reports sample ~3.5x and clears under-powered experiments |
| F6 | `review` returns a clean 200 with no concerns when BigQuery is down | Fails open and silent, degrading toward a *larger* apparent sample |
| F9 | BigQuery JSON returns `2.0` as `2`; the hash design treats them as distinct | **No unit test could have found this.** Needed a real round-trip |
| F10 | Race between answer and approve attaches an approval to answers it was not computed from | Fails closed, wedges the session, says nothing |

All six are dispatched to BACKEND-API as **HC-S6-FIX**. Rulings and reasoning in `HC-S6-RULINGS.md`.

**HC-S7 (deploy) is blocked on that fix.** The backend is already live in production — an unrelated API rebuild on 2026-09-08 included the scoping router — so F1 and the open anonymous reads are live defects today, mitigated only by the frontend being undeployed and writes needing an API key.

---

## Part 2 — INC-002: the 2026 ingest was dead

Full write-up in `INC-002-ingest-blocked-by-closing-line-gate.md`. Resolved.

The scheduler auth fix applied on 2026-08-31 let the pipeline jobs run for the first time since May. They failed immediately, four times over, on **one bug wearing four faces: checks that describe a COMPLETED season, wired as gates on a live one.**

| Gate | Would have failed |
|---|---|
| Closing-line null rate > 5% | Every run, all season |
| `validate_pbp` requires ≥40,000 rows (week 1 is ~2,700) | **Every gameday run until ~week 15** |
| `build_curated_games` had no `EMPTY` tolerance | Every run until week 1 completed |
| `validate_and_report` applied completed-season thresholds per season | Every run, all season |

The second is the one worth remembering: it would not have announced itself. It would have failed quietly every Sunday until mid-December.

Fix principle throughout: **the current season warns; completed seasons still error.** No historical guarantee weakened.

**Also fixed:** `GET /api/v1/games` 500'd for every season with completed games — the SQL emitted `'complete'` while the schema, the contract and the frontend all say `'final'`. It hid because the list sorts `season DESC`, so once 2026 fixtures loaded the first page was all `scheduled` and the endpoint looked healthy.

**And alerting had never worked.** Neither policy declared a `trigger` block, so the API defaulted it to zero — enabled, correct-looking, structurally unable to fire. Fixed and **proven by a real email**.

---

## The pattern, stated once

Seven distinct defects in two days, all the same shape: **code that had never met real data, in a system where the thing that would have reported the problem was itself broken.**

The outage hid the bugs. Fixing it revealed them one at a time. The tests were green because they tested the author's model of the world.

Practical consequence: **treat the first weeks of the season as a shakeout, not steady state.** More of these will surface as games are played and columns that were null start carrying values.

---

## Verified working as of 2026-09-09

- `nfl-pipeline-full` and `nfl-pipeline-gameday` complete 7/7
- `raw_nflfastr.pbp` fresh (was frozen 122 days at 2026-05-08)
- 2026 fixtures live and queryable
- `GET /api/v1/games` returns 200 for every season
- Alerting fires and delivers email
- Scheduler runs unattended — **Thursday 2026-09-10 TNF is the first real test**
- 91 backend scoping tests + 56 TESTING-QA tests

## Not done

- **Four commits unpushed** — `42336b6`, `557d91e`, `9f45c18`, `97393d4`
- HC-S6-FIX (BACKEND-API), then HC-S7 (FRONTEND)
- Four HC-S5 findings still spec'd, not dispatched (`HC-FINDINGS-S5.md`)
- DEVOPS hardening: pre-container-failure alert, P4 freshness check, `/health` commit
- DATA-PIPELINE review of five files PROJECT-LEAD edited under time pressure

## Role-boundary deviations, recorded deliberately

PROJECT-LEAD edited five files in `01-DATA-PIPELINE` and one in `05-DEVOPS`, at Matt's explicit instruction during the incident. Both folders now carry a review task. **These should be reviewed, not inherited silently.**

## One operational note

`.git` accumulates stale lock files because the sandbox PROJECT-LEAD runs in cannot delete. An 8-day-old `index.lock` from the machine migration had been silently blocking every commit since 30 August. If git or VS Code reports *"another git process seems to be running"*, check `.git/*.lock`.
