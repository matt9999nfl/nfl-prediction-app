# Pre-Season Status — 10 Days to Kickoff

**Owner:** PROJECT-LEAD
**Date:** 2026-08-31
**Season starts:** ~2026-09-10
**Purpose:** One consolidated view of platform state ahead of the season, the decisions taken today, and the ordered pre-kickoff work. Written because status was spread across six documents with three different "current phase" claims.

**Does not duplicate:** live data inventory (`docs/DATA_STOCKTAKE_2026-08-31.md`), automation remediation detail (`SEASON_AUTOMATION_PLAN.md`), hypothesis-chat design (`HYPOTHESIS-CHAT-BUILD-PLAN.md`). This document cross-references them and does not restate their contents.

---

## 1. Verified state

Read from files and live GCP checks on 2026-08-31, not from memory or from status docs alone.

### The platform works

Phases 1–5 are built and deployed. Frontend at `http://34.49.20.115`, API at `https://nfl-backend-api-rmaehdhzhq-uc.a.run.app`. The Phase 5 polish sprint closed 2026-05-24: routes corrected, `per_fold` in the experiment detail response, feature-importance endpoint live, dataset delete + stuck-upload reconciliation shipped, write path unblocked after the `OWNER_API_KEY` rotation.

Evidence the app is genuinely in use, not just deployed: `experiments.backtest_runs` (35 rows) and `platform.experiment_configs` (13 rows) were both last written 2026-08-15, from a live-app experiment run.

### Four honest negatives

No experiment has passed its gate. This is recorded plainly because it drives §3.

| Experiment | Result | Verdict |
|---|---|---|
| `ol_xgb_v1` | 48.7% ATS | Baseline |
| `ol_xgb_v2` (52 features) | 49.6% ATS | Baseline |
| Rush features (test1/2/3) | 48.8% on correct labels | ❌ NO-GO — the 58–61% was label inversion (INC-001) |
| `sit_div` (divisional only) | 47.95%, 1/7 folds >54% | ❌ NO-GO |
| `sit_late` (weeks 15–18) | 48.13%, 2/7 folds >54% | ❌ NO-GO — always-home baseline beats it |

Infrastructure verdict from the Tier 1 audit stands: runner faithful, shuffled-label test clean, no leakage. The platform is measuring correctly and the answer is that these feature sets carry no edge. That is a working platform, not a failing one.

### The data spine is half-fixed

The scheduler auth bug (115 days of silent total failure) was fixed and verified live yesterday. Both forced runs created real Cloud Run Job executions for the first time ever, and `raw_nflfastr.schedules` picked up the full 2026 REG schedule — 3,028 → 3,300 rows, the first live 2026 data in BigQuery.

That fix uncovered a second, previously-latent bug: the closing-lines audit in `run_pipeline.py` hard-gates every run at Step 2/7 because the in-progress 2026 season has no posted lines yet. **Fixed in source, not deployed.** Until the image is rebuilt, `pbp`, `rosters`, `curated.games` and `curated.plays` will not refresh once during the season.

---

## 2. The gap nobody owned

Stated plainly because it is the most consequential finding in this review.

**Nothing in the current plan produces a prediction for a 2026 game.**

Every experiment in the platform is a walk-forward backtest over completed seasons. There is no prediction object for an upcoming game, no scheduled path that emits one, and no page that displays one. `nfl-production-refresh` — the job that would push predictions — queries for `gate_passed` experiments, and per §1 there are none, so even a fully-healthy pipeline produces nothing to show.

`HYPOTHESIS-CHAT-BRAINSTORM.md` D-5 scoped live forward prediction out as "a separate project in a separate session." That session was never opened. The deferral was correct for that build's scope; the consequence is that the capability has no owner and no plan, ten days out.

---

## 3. Decisions taken 2026-08-31

**DEC-A — Live forward prediction is now an active project.** Matt's call. The app should produce and display predictions for upcoming 2026 games during the season, not only backtests over closed ones. This reverses the *deferral* in D-5, not the *reasoning* — D-5 correctly kept it out of the hypothesis-chat build's scope. It now gets its own scope.

**DEC-B — This project is a new build and follows `agent-methodology/01-new-build-protocol.md` from Phase 1.** No spec, no scope, no code until an approved one-sentence "what done looks like" exists. Phase 1 has not started. Given the calendar, the honest position is that a designed-and-built forward prediction path is unlikely to be live for Week 1; a deliberately narrow first version might be.

**DEC-C — Gate-passing is not a prerequisite for forward prediction, but the honest-evaluation banner is.** A model with no demonstrated edge can still emit a weekly prediction, provided the app never presents it as validated. `nfl-production-refresh`'s `gate_passed` filter is the current structural block on that, and resolving it is a Phase 1 question, not an implementation detail to route around.

---

## 4. Open items

| # | Item | Owner | Since | State |
|---|---|---|---|---|
| O-1 | P0b — rebuild + redeploy pipeline image so the closing-lines gate fix goes live | DEVOPS / DATA-PIPELINE | 2026-08-31 | Fixed in source, not deployed. **Blocks all in-season data.** |
| O-2 | Live forward prediction — Phase 1 brainstorm | PROJECT-LEAD + Matt | 2026-08-31 | Not started. See DEC-B. |
| O-3 | BUG-001 — cloning silently drops all features | BACKEND-API + FRONTEND | 2026-05-26 | Open, delegated, no completion recorded in 97 days |
| O-4 | BUG-002 — deprecated features referenced with no warning | BACKEND-API + FRONTEND | 2026-05-26 | Open, delegated, no completion recorded |
| O-5 | `nfl-experiment-runner` failed on the 2026-08-15 live-app run | BACKEND-API / MODELING | 2026-08-15 | Never investigated. Unrelated to the ingest bugs. |
| O-6 | P4 — scheduler-level alert + data-freshness check | DEVOPS | 2026-08-31 | Proposed. The gap that let 115 days pass unnoticed. |
| O-7 | P1 — load 13 staged OL/advanced sources to BigQuery | DATA-PIPELINE | 2026-08-31 | Blocked: staging machine has no `gcloud` and no service-account key |
| O-8 | P2 — fold in-season feeds into the gameday job | DATA-PIPELINE | 2026-08-31 | Proposed, depends on O-1 |
| O-9 | Gameday mode runs all 7 steps (`--start-at 1`) contrary to its own comment | DATA-PIPELINE | 2026-08-31 | Needs a decision on what gameday mode should do |
| O-10 | Hypothesis chat stages 0–7 | multiple | 2026-08-31 | Plan approved, ADR-012 logged, **not dispatched** |
| O-11 | Phase 4 Track 5 Go/No-Go — formal decision | PROJECT-LEAD | 2026-05-17 | Results unambiguous (both NO-GO); decision never formally recorded |
| O-12 | Doc drift — `ROADMAP.md` (says Phase 5 active), `docs/DATA_SOURCES.md` (silent on 13 new sources) | PROJECT-LEAD | — | Stale |
| O-13 | P3 — split Sunday gameday trigger; P5 — true live in-game feed | PROJECT-LEAD + Matt | 2026-08-31 | Scope decisions, additive, do not block kickoff |

---

## 5. Ordered pre-kickoff work

Order is by what unblocks what, not by size.

1. **O-1 — redeploy the pipeline image.** Half a day. Nothing in-season works until a run reaches Step 7 and `curated.*` timestamps advance. Verify by force-running `nfl-pipeline-full-weekly` and checking the execution reaches Succeeded, not merely Created.
2. **O-2 — open Phase 1 on live forward prediction.** Conversation, not a build. The output is one approved sentence. Starting this late is worse than starting it narrow.
3. **O-6 — P4 alerting.** Small, and the reason a 115-day outage cost 115 days. Do it before the season generates the data that would hide the next one.
4. **O-3 — BUG-001.** Pull forward if config cloning is part of the in-season iteration loop; a clone that silently runs an empty feature matrix produces a result that looks like a modelling finding.
5. **O-7 → O-8 → O-9 — the OL source backfill and its in-season cadence.** O-7 is a credentials task, not an engineering one.
6. **O-11, O-12 — record the Track 5 decision, refresh the two stale docs.** An hour, and it stops the next session from re-deriving all of this.
7. **O-10 — hypothesis chat stages 0–2.** The deterministic core ships a complete, usable feature with zero AI. Deliberately last: it is the only item here that adds capability rather than protecting what exists.

---

## 6. Standing note

"Improvements before the season" decomposes into two projects that are easy to conflate: making the **platform** trustworthy and useful, and finding an **edge**. §1 shows the first is close and the second has not happened. Live forward prediction (DEC-A) belongs to the first — it makes the platform do a thing it cannot currently do. It does not, on its own, make any model better, and the app must not imply otherwise (DEC-C).

---

## 7. Delegation status

Nothing in §4 has been dispatched from this document. Per `instructions.md`, dispatch happens by appending a `## CURRENT TASK` block to the owning agent's `instructions.md`, on Matt's explicit instruction, and not before.
