# Hypothesis Chat Interface — Phase 1 Brainstorm (running doc)

**Owner:** PROJECT-LEAD
**Status:** Phase 1 (brainstorm) per `agent-methodology/01-new-build-protocol.md`. No spec, no scope, no code.
**Started:** 2026-08-31
**Exit condition:** one approved sentence describing "what done looks like". Nothing proceeds to Phase 2 until that exists and Matt approves it.

---

## The ask (as stated, unedited)

A Claude LLM chat interface inside the platform. Instructed to use only the data and models within the platform. The user types a hypothesis — e.g. *"teams with heavier O lines perform better in poor weather"* — the LLM asks an extensive set of clarifying questions to scope the experiment, outputs a `.md` file of experiment instructions, confirms it with the user, then runs the experiment.

Wanted alongside: app fully functional and able to run experiments during the 2026 season (starts ~2026-09-10, ~10 days out).

---

## Verified current state (read 2026-08-31, from files not memory)

- Phase 5 polish sprint marked complete; app live (API on Cloud Run, frontend at 34.49.20.115). Write path works.
- `ExperimentConfig` (docs/API_CONTRACTS.md) is a **closed, narrow schema**: target ∈ 4 values; features as {dataset, column, semantic_name}; walk-forward methodology; `game_universe` filter supports **only `div_game` and `week`**; model ∈ 3 types.
- Data spine is **stale 115 days**. `raw_nflfastr.*` last modified 2026-05-08. No 2026 data.
- All 5 Cloud Scheduler jobs have been failing since May (auth bug). Fix is written in Terraform source but **not applied** — needs `terraform apply` (SEASON_AUTOMATION_PLAN.md P0).
- 13–14 new OL/advanced sources are staged on disk as parquet, **not loaded to BigQuery** (P1). No credentials on the staging machine.
- `user_datasets.*` and `platform.datasets` are empty — no user dataset upload has ever succeeded end-to-end.
- ADR-011 stands: experiments run in the platform, not in Claude chat.

---

## Assumptions being challenged (Phase 1 discipline — name what is being ruled out)

**C-1 — CORRECTED 2026-08-31.** My first read of this was wrong and the correction matters.

*Wrong:* "there is no weather data."
*Right:* `curated.games` already carries `roof`, `surface`, `temp`, `wind`, sourced from nflfastR schedules (`01-DATA-PIPELINE/scripts/build_curated_games.py` L45-71). `temp`, `wind` and `roof_dome` are already in the Phase 1 feature catalog (`docs/MODELING_SPEC_PHASE1.md` §Game-Level Context Features). Matt caught this.

What survives the correction, in sharper form — the example hypothesis breaks on two different things, and they are not the same kind of problem:

| Gap | What's missing | Size |
|---|---|---|
| "in poor weather" | Weather exists as a **model feature** but not as a **game-universe filter**. `GameUniverseFilter` accepts only `div_game` and `week`. A conditional/subgroup claim ("X holds *when* Y") is a slice, not another input column — adding `temp` as a 53rd feature does not answer it. | Small. Widen the filter to any `curated.games` column. |
| "heavier O lines" | No weight/height/size feature exists anywhere in the catalog. Player weight sits in `seasonal_rosters_2015_2025.parquet` and `combine_2000_2025.parquet` — both staged on disk, neither in BigQuery. There is also no *definition*: which five linemen, starters by depth chart or snap-weighted, and what about in-game substitution. | Real. Needs the staged load plus a modelling decision a human has to make. |

The generalisable point: **a hypothesis in prose decomposes into a target, a slice, and a set of features — and the platform's three surfaces for those are unequally mature.** Targets are fine (4 options). Slices are the narrowest surface by a wide margin. Features are broad but have holes exactly where a new hypothesis tends to point. The chat will hit the slice wall and the missing-feature wall constantly. What it does at those two walls *is* the design.

**C-2 — "Chat interface" and "LLM decides the experiment" are separable.**
Under `05-structural-governance.md`'s 60/30/10 rule, this feature decomposes: translating prose → a config is genuine AI work (10%); the clarifying-question sequence is a decision tree (30%, a rule engine — not a prompt); running the backtest is the existing deterministic runner (60%, no model at runtime). The risk is building all three as one prompt.

**C-3 — ADR-011 is not violated by this, but its boundary moves.**
"Experiments run in the app, not in Claude" survives if the LLM only *emits a config the existing runner executes* and can do nothing else. It is violated the moment the LLM can write or run its own query/script. This distinction needs to be structural, not instructed.

**C-4 — RESOLVED 2026-08-31.** Data-spine remediation (P0/P1/P2/P4) is owned by a separate session and out of scope for this build. This session plans the chat interface only. Standing dependency, not a competing deliverable: the chat is only as trustworthy as the spine beneath it.

---

## Open questions

| # | Question | Status |
|---|----------|--------|
| Q1 | Given ~10 days to kickoff, what must be true at kickoff vs. what can land mid-season? | **Answered** — out of scope. Data spine is being fixed in a separate session. This session plans the chat interface only. |
| Q2 | What is the LLM allowed to *do*? (capability boundary) | **Answered** — bounded executor. Config emitter only; at a wall it stops and writes the gap up. See D-2. |
| Q3 | Is the clarifying-question sequence a fixed tree or LLM-generated per hypothesis? | **Answered** — split. Deterministic tree fills config slots; LLM sits above it as governor. See D-3. |
| Q4 | Is the `.md` the execution contract or a rendering of it? | **Answered** — config authoritative, `.md` rendered from it, approval bound to config hash. See D-4. |
| Q5 | What does an experiment do with the in-progress 2026 season? | **Closed** — out of scope. Separate project. See D-5. |
| Q6 | Where do capability-gap records go — agent `instructions.md` via the delegation protocol, or a backlog Matt triages? | open, Phase 2 |
| Q7 | Who uses this — Matt only, or public? | **Answered** — Matt only at this stage. No multi-tenancy, no quotas, no shared sessions. |

---

## Decisions made

- **D-0 (2026-08-31)** — Process note: PROJECT-LEAD asserted "no weather data" from a stocktake reading without checking the pipeline source. Matt corrected it. Verify claims about what the platform contains against `01-DATA-PIPELINE/scripts/` and the feature catalog, not against inventory docs, which describe datasets rather than columns.
- **D-5 (2026-08-31, revised)** — **Live forward prediction is out of scope for this build.** It is a separate project in a separate session, along with any new data sources it needs. This feature is built against the platform as it exists: the current `ExperimentConfig`, the current runner, the current data. When forward prediction lands it will extend the experiment object; that is not this feature's problem to anticipate. *Chose to scope against today's platform over designing for a future one because the alternative is designing the system we wish we needed — the named pitfall in `00-PROJECT-LEAD/instructions.md`.*
- **D-4 (2026-08-31)** — Single source of truth: the `ExperimentConfig` is authoritative and the `.md` brief is **rendered from it deterministically**, never authored alongside it. Approval is recorded against the config hash and the runner refuses any config whose hash was not approved. Edits happen by re-answering a question, not by editing the file. *Chose rendering over prose-authoring because it makes brief/config drift structurally impossible rather than prohibited — the failure mode being closed is approving one thing while another executes, which is silent by nature.*
- **D-3 (2026-08-31)** — Two-layer questioning, matching the SOP/governance split in `05-structural-governance.md`. **Layer 1 (rule engine, ~30%):** a deterministic decision tree asks every question needed to fill an `ExperimentConfig` slot, in fixed order — unit-testable, no model variance. **Layer 2 (AI, ~10%):** the LLM does not ask slot questions; it challenges whether the experiment should run — sample size after slicing, multiple-comparisons pressure across prior runs, whether the slice is a proxy for something already in the feature set. *Chose the split over an LLM-driven question flow because the two halves fail differently and testing them together makes both untestable.*
- **D-2 (2026-08-31)** — The chat is a **bounded executor**, not an autonomous agent (`05-structural-governance.md`). Its only execution output is an `ExperimentConfig` the existing runner consumes. It cannot write SQL, run code, create tables, or extend the feature catalog. When a hypothesis needs something the platform cannot express, it stops, offers the nearest expressible variant, and emits a capability-gap record. *Chose bounded executor over free SQL because reproducibility and ADR-011 compliance are the point of the platform; accepted cost is that the first genuinely novel hypothesis returns a gap record rather than a result.*
- **D-1 (2026-08-31)** — Scope of this planning session is the hypothesis chat interface alone. Data-spine remediation is tracked separately and treated here as a dependency, not a deliverable.

---

## Out of scope / handled elsewhere

Tracked so they are not re-litigated, not because they block this build.

- Live/forward predictions, live odds, prediction tracking — separate project, separate session.
- Data-spine remediation and new source ingest (`SEASON_AUTOMATION_PLAN.md` P0–P4) — separate session. Adding sources is understood to be routine.
- Missing features and filters (OL weight, weather-as-slice) — handled *by* this feature via the capability-gap record in D-2, not *before* it.

**Standing note, not a blocker:** the one thing live testing would genuinely change about this design is the weight on D-3 Layer 2 — a weekly leaderboard across many hypotheses manufactures winners by chance. Layer 2 should be built so it can carry that load later without redesign.

---

## What done looks like

**Draft 2 — APPROVED 2026-08-31. Phase 2 plan is in `HYPOTHESIS-CHAT-BUILD-PLAN.md`.**

> A page in the app where Matt types a hypothesis in plain English, answers a fixed sequence of scoping questions while a governor layer challenges whether the experiment is worth running, approves a brief rendered from the exact `ExperimentConfig` that will execute, and has the existing runner run it — producing an experiment indistinguishable in `experiments.*` from a wizard-built one; and where a hypothesis the platform cannot currently express ends in a written capability-gap record instead of a workaround.

*Draft 1 (superseded) additionally required a live week-by-week 2026 record. Removed 2026-08-31 — out of scope per D-5.*
