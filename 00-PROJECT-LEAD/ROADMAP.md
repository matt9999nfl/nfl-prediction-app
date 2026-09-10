# ROADMAP — NFL Prediction App

**Owner:** PROJECT-LEAD
**Last updated:** 2026-09-10
**Framing:** Read `PROJECT-CHARTER.md` first. This is a **platform-building
project**; modelling happens later, through the platform. This document does not
restate that — it assumes it.

**Current status:** Phases 1–5 complete. **Phase 7 (In-Season Operations) is
active** and, as of 2026-09-10, live. Phase 6 (Hypothesis Chat) is built but
undeployed, blocked behind the season freeze.

> **Rewritten 2026-09-10.** The previous version claimed three different things
> at once: the header said "Phase 5 complete / Phase 6 active", the phase table
> said Phase 4 ✅ Complete, and the Phase 4 section said "🔄 IN PLANNING, not yet
> started". It also predated INC-002 and the 2026-09-09/10 sprint entirely. It is
> the first document a cold session reads, which made it the most expensive stale
> document in the repo. Historical phase detail has been compressed to summaries;
> the full records live in the phase status documents named below.

---

## Phase overview

| Phase | Name | Gate | Status |
|-------|------|------|--------|
| 1 | Foundation & Validation | Infrastructure built, pipeline validated | ✅ Complete 2026-05-03 |
| 2 | Service Layer | Full self-service platform built | ✅ Complete 2026-05-06 |
| 3 | Productionize | App deployed and running in GCP | ✅ Complete 2026-05-07 |
| 4 | Validation & Improvements | App does what it says; results are trustworthy | ✅ Complete 2026-05-17 |
| 5 | Polish Sprint | App is camera-ready for public launch | ✅ Complete 2026-05-24 |
| 6 | Hypothesis Chat | A hypothesis stated in prose is scoped, briefed and run | 🟠 Built, **undeployed** |
| 7 | **In-Season Operations** | The app predicts, serves and grades real upcoming games, unattended | 🔄 **ACTIVE — live** |

**Live URLs**

| Service | URL | Verified |
|---------|-----|----------|
| BACKEND-API | `https://nfl-backend-api-rmaehdhzhq-uc.a.run.app` | 2026-09-10, `commit: 3cbf12f` |
| FRONTEND | `http://34.49.20.115` | 2026-09-10 |

---

## Phase 7 — In-Season Operations 🔄 ACTIVE

**Start date:** 2026-08-31 (DEC-A) · **First live:** 2026-09-10
**Records:** `SPRINT-REVIEW-2026-09-10.md`, `REVIEW-2026-09-10.md`,
`SESSION-HANDOFF-2026-09-09-PM.md` · **Decisions:** DEC-A, DEC-B, DEC-C in
`PRE_SEASON_STATUS_2026-08-31.md` §3

### What Phase 7 is

The platform can run a backtest over completed seasons. Phase 7 is it doing the
other thing: **producing, serving and grading a prediction for a game that has
not been played yet**, on a schedule, without anyone watching.

`PRE_SEASON_STATUS_2026-08-31.md` §2 stated the gap plainly: *"Nothing in the
current plan produces a prediction for a 2026 game."* DEC-A made closing it an
active project on 2026-08-31. It was not dispatched, and the capability was built
under deadline on 2026-09-09/10 instead.

### What is built and live

| Capability | Where | State |
|---|---|---|
| Forward prediction for unplayed games | `02-MODELING/backtests/predict_upcoming.py` | ✅ Live — 16 games, 2026 wk 1 |
| Weekly grade-then-predict automation | `02-MODELING/backtests/run_production_refresh.py` | ✅ Live, Tue 14:00 UTC |
| Ungated serving with honest banner | `03-BACKEND-API/app/queries/predictions.py` | ✅ Live, `gate_passed` served not assumed |
| Manual refresh trigger | `POST /api/v1/predictions/refresh` + dashboard button | ✅ Live |
| Deploy pipeline that actually shifts traffic | `.github/workflows/api-deploy.yml` | ✅ Fixed |
| `/health` reports the running commit | `app/config.py` + `Dockerfile` | ✅ Live |
| Cross-machine reproducibility | `models/ol_xgb.py`, `models/xgb_v2.py` — `n_jobs=1` | ✅ Fixed, max delta 2.8e-8 |
| Market line change-log | `raw_lines.line_snapshots` | ✅ Shipped |
| Frontend error boundary | `04-FRONTEND` route wrapper | ✅ Shipped |

### Phase 7 complete when

- [x] A prediction exists for an unplayed 2026 game and is served by the API
- [x] The dashboard renders it, with the honest-evaluation banner driven by served data
- [x] Deploys shift traffic and the running commit is identifiable
- [x] The same numbers are produced on any machine
- [ ] **The weekly job completes an unattended grade-then-predict transition** — first attempt Tue 15 Sep. Verified only on a week-1 predict so far.
- [ ] CI runs the test suite before a deploy reaches production
- [ ] A week's picks are graded and the running record is visible in the app

### Known open items

Full list and ordering in `REVIEW-2026-09-10.md` §6. The blocking ones:

1. Backend tests cannot run without GCP credentials — gates everything below
2. CI never runs the 91 existing tests
3. Traffic shifts to `LATEST`, not the smoke-tested revision
4. `require_api_key` fails open when `OWNER_API_KEY` is absent
5. Terraform and CI both declare the Cloud Run service spec
6. The retired 54% gate is still written into the database on every run
7. No frontend test framework exists

---

## Phase 6 — Hypothesis Chat 🟠 BUILT, UNDEPLOYED

**Start date:** 2026-08-31 · **Plan:** `HYPOTHESIS-CHAT-BUILD-PLAN.md` ·
**Phase 1 record:** `HYPOTHESIS-CHAT-BRAINSTORM.md` · **Tracking:**
`DELEGATIONS.md` · **Decision:** ADR-012

A page where Matt types a hypothesis in plain English, answers a fixed sequence
of scoping questions while a governor layer challenges whether the experiment is
worth running, approves a brief rendered from the exact `ExperimentConfig` that
will execute, and has the existing runner run it — producing an experiment
indistinguishable in `experiments.*` from a wizard-built one. A hypothesis the
platform cannot currently express ends in a written capability-gap record rather
than a workaround. Single user. Not public.

**The constraint that shapes it:** the chat is a *client of the write API that
already exists* — `POST /api/v1/experiments` and
`POST /api/v1/experiments/{id}/runs`. It holds no BigQuery credential and cannot
execute SQL or generated code, so ADR-011 is enforced by an absent capability
rather than by a rule. The runner is unmodified; MODELING has no work in this
phase.

**Build order:** stages 0–7 (declared question tree → tables → deterministic core
→ extractor → governor → frontend → tests → deploy). Stage 2 is load-bearing:
after it the feature works end to end with no model in the loop, so stages 3–4
are enhancement rather than completion.

**Status:** HC-S6-FIX accepted 13/13. `HC-S6-FIX-2`, `HC-S6-CLEANUP`, `DO-HARDEN`
and `HC-S7` are on the board in `DELEGATIONS.md`. **Nothing is deployed** — the
scoping backend live at `nfl-backend-api-00024-kw7` is behind the repo, and the
deploy is held behind the season freeze (`REVIEW-2026-09-10.md` §0).

---

## Completed phases — summary record

Detail is preserved in the status documents. Do not re-derive it from here.

### Phase 1 — Foundation & Validation ✅ 2026-05-03
**Detail:** `GATE_REVIEW_PHASE1.md`, `docs/MODELING_SPEC_PHASE1.md`,
`docs/PIPELINE_SPEC_PHASE1.md`

nflfastR play-by-play, schedules and rosters loaded to BigQuery
(`raw_nflfastr.*`, `curated.*`) for 2015–present. Closing lines from nflverse
`spread_line`. PR-001 fixed the `home_covered` sign convention. Walk-forward
experiment framework: 6-fold harness, leakage guards, BigQuery output to
`experiments.*`. Two baselines: `ol_xgb_v1` (48.7% ATS), `ol_xgb_v2` (49.6%, 52
features).

**Phase 1 completed on infrastructure, not on a model result** — ADR-006 retired
the original ≥54% ATS project gate the same day. See `PROJECT-CHARTER.md` §2.

### Phase 2 — Service Layer ✅ 2026-05-06
Full REST API (games, experiments, predictions, datasets, frameworks, features),
dataset upload flow, Cloud Run Job trigger, Claude schema inference. Config-driven
runner with a dynamic feature matrix. All frontend pages built, with the
honest-evaluation banner. `platform.*` tables — 58/58 validation checks passed.

### Phase 3 — Productionize ✅ 2026-05-07
**Detail:** `docs/DEVOPS_SPEC_PHASE3.md`, `docs/TESTING_QA_SPEC_PHASE3.md`,
`PHASE3_STATUS.md`

Full GCP deployment via Terraform: Cloud Run service, Cloud CDN + GCS frontend,
Cloud Run Jobs, Cloud Scheduler, monitoring, runbooks, CI/CD.
`GET /api/v1/predictions` shipped. Integration test suite built.

*Retrospective note:* two Phase 3 deliverables looked complete and were not. The
CI deploy could never shift traffic (fixed 2026-09-10) and both monitoring alert
policies were silently unfirable (fixed during INC-002). Both were the same
shape — configuration that is syntactically present and functionally inert.

### Phase 4 — Validation & Improvements ✅ 2026-05-17
**Detail:** `PHASE4_STATUS.md`, `RUSH_VALIDATION_PLAN.md`,
`RUSH_FEATURE_EXPERIMENTS_REVIEW.md`, `GATE_REVIEW_PHASE4_RUSH.md`,
`INC-001-INVESTIGATION-REPORT.md`

Triggered by three rushing-feature experiments reporting 58–61% ATS against a
49.65% baseline. **The result was a label inversion (INC-001), not an edge** —
48.8% on correct labels. Both situational experiments were also NO-GO. Delivered
configurable seeds, shuffle-labels leakage testing, per-fold breakdowns, feature
importance, and comparison tooling.

Track 5 Go/No-Go: **both NO-GO.** Results were unambiguous; the decision was
never formally recorded at the time (O-11) and is recorded here.

### Phase 5 — Polish Sprint ✅ 2026-05-24
**Detail:** `PHASE5_STATUS.md`, `BACKEND_API_SPEC_PHASE5.md`,
`FRONTEND_SPEC_PHASE5.md`

Eight issues (P5-01 … P5-08) found in a live walkthrough: swapped router
routes, wizard step-navigation, stuck dataset uploads, wrong `end_season`
default, dashboard count, missing `per_fold`, 404 on feature-importance, and
unexplained home/away feature mirroring. All fixed.

**Carried debt:** three visual verifications in `PHASE5_STATUS.md` remain
unticked, and the FRONTEND May-2026 bug sprint is *paused, unverified not done*.
Backend counterparts are confirmed shipped; the F2-E visual checks never were.
Resume deliberately or drop deliberately — see `DELEGATIONS.md` carried debt.

---

## Incidents

| ID | Date | Summary | Record |
|---|---|---|---|
| INC-001 | 2026-05 | Label inversion produced a false 58–61% ATS result | `INC-001-label-inversion.md`, `INC-001-INVESTIGATION-REPORT.md` |
| INC-002 | 2026-09-08 | Ingest blocked by the closing-line gate; monitoring alerts silently unfirable; a week spent unable to answer which code was running | `INC-002-ingest-blocked-by-closing-line-gate.md` |
| — | 2026-09-09/10 | Ten defects across deploy, serving, dashboard and reproducibility, found and fixed under season deadline | `SPRINT-REVIEW-2026-09-10.md`, `REVIEW-2026-09-10.md` |

---

## Key decisions (full ADRs in `docs/DECISIONS.md`)

| ADR | Decision | Status |
|-----|----------|--------|
| 001 | Use existing GCP project `nfl-model-471509` | Accepted |
| 002 | nflfastR / nflverse as primary data spine | Accepted |
| 003 | Cloud Run for the API service | Accepted |
| 004 | BigQuery as the only data store (no separate OLTP) | Accepted |
| **005** | **Project goal is a comprehensive NFL prediction platform, _not_ an OL hypothesis validator** | **Accepted** |
| **006** | **Experiment gates are per-experiment. The project-level ≥54% ATS gate is RETIRED** | **Accepted** |
| 007 | Self-service platform with form-based upload + Claude API schema inference | Accepted |
| 008 | FastAPI BackgroundTasks in Phase 2; swap to Cloud Run Jobs in Phase 3 | Accepted |
| 009 | `model.type` uses abstract names in the API contract; runner resolves to concrete implementations | Accepted |
| 010 | Terraform for infrastructure-as-code | Accepted |
| **011** | **The platform is the product: no hypothesis testing in Claude chat** | **Accepted** |
| 012 | Hypothesis chat is a bounded client of the existing write API | Accepted |

**Session decisions not yet promoted to ADRs** — see
`PRE_SEASON_STATUS_2026-08-31.md` §3 and `REVIEW-2026-09-10.md` §6:

| Ref | Decision | Needs an ADR |
|---|---|---|
| DEC-A | Live forward prediction is an active project | Fold into Phase 7 |
| DEC-B | It follows the new-build protocol from Phase 1 | — |
| DEC-C | Gate-passing is not a prerequisite for a forward prediction; the honest-evaluation banner is | ✅ **Yes** — this governs what the public sees |
| — | `n_jobs=1` for reproducibility, and the caveat it places on every historical experiment | ✅ **Yes** |

> **005, 006 and 011 are bolded because they are the ones that keep getting lost.**
> Note that in `docs/DECISIONS.md` the ADRs are filed out of sequence — 005, 007,
> 009, 008, 010, 011, **006**, 012 — so ADR-006, the decision that retires the
> 54% gate, sits near the bottom where a skim will miss it. Reorder it.
