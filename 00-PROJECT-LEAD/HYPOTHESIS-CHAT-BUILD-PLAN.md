# Hypothesis Chat — Phase 2 Implementation Plan

**Owner:** PROJECT-LEAD
**Status:** Phase 2 plan. **No code is written until Matt approves this document.**
**Date:** 2026-08-31
**Phase 1 record:** `HYPOTHESIS-CHAT-BRAINSTORM.md` (decisions D-1 to D-5, approved "what done looks like")
**Methodology:** `agent-methodology/01-new-build-protocol.md`, `03-pipeline-protocol.md`, `05-structural-governance.md`

---

## What done looks like (approved)

> A page in the app where Matt types a hypothesis in plain English, answers a fixed sequence of scoping questions while a governor layer challenges whether the experiment is worth running, approves a brief rendered from the exact `ExperimentConfig` that will execute, and has the existing runner run it — producing an experiment indistinguishable in `experiments.*` from a wizard-built one; and where a hypothesis the platform cannot currently express ends in a written capability-gap record instead of a workaround.

Single user: Matt. Not public. No multi-tenancy, no per-user quotas, no shared sessions.

---

## The one architectural idea

**The chat is a client of the write API that already exists. It is not a new execution path.**

`POST /api/v1/experiments` (create) and `POST /api/v1/experiments/{id}/runs` (trigger) are live and deployed (`app/routers/experiments.py` L280, L351). The chat's entire job is to compose a valid `ExperimentConfig` and call those two endpoints.

This is what makes D-2 structural rather than instructed. The chat is not told "don't run SQL" — it has no database credential, no query path, and no code execution surface. Its only reachable verb is *create an experiment the same way the wizard does*. `05-structural-governance.md`: make wrong behaviour impossible, not prohibited.

Consequence worth stating plainly: **MODELING has no work in this build, and the runner is not modified.** If a task in this plan appears to require a runner change, that is a kill-switch condition, not a task.

### 60/30/10 classification (`05-structural-governance.md`)

| Layer | Share | What it is | Model at runtime? |
|---|---|---|---|
| Config assembly, validation, brief render, hash, dispatch | 60% | Deterministic transforms | No |
| The scoping question sequence | 30% | Rule engine over a declared tree | No |
| Prose → slot extraction; governance critique; gap drafting | 10% | Genuine judgment | Yes — 2 bounded calls |

The build order below follows this: the 60% ships first and is independently usable, the 30% next, the 10% last. If the AI layers slip or disappoint, a working feature still exists.

---

## Component structure

### New — `03-BACKEND-API`

```
app/scoping/
  schema.py          Pydantic models: ScopingSession, Slot, SlotAnswer, CapabilityGap, GovernorVerdict
  tree.py            Loads + validates scoping_tree.yaml; resolves next unanswered slot
  scoping_tree.yaml  THE QUESTION TREE AS DATA — see below
  assemble.py        SlotAnswers → ExperimentConfig (pure function)
  render.py          ExperimentConfig + record-only answers → brief markdown (pure function)
  hashing.py         Canonical JSON → sha256 of the config
app/routers/scoping.py     REST surface for the chat
app/queries/scoping.py     BigQuery reads/writes for sessions and gaps
app/claude_scoping.py      BOTH model calls, isolated — mirrors claude_inference.py
```

`claude_scoping.py` sits beside the existing `claude_inference.py` deliberately. ADR-007 established a single integration point for Claude in the upload handler; this is the second, and it follows the same shape — one module, fixed output keys, validated before return, its own error class converted to 503.

### New — `04-FRONTEND`

```
src/pages/HypothesisChatPage.tsx
src/components/scoping/SlotPrompt.tsx        renders one question from tree metadata
src/components/scoping/BriefPreview.tsx      renders the returned markdown, approve/reject
src/components/scoping/GovernorPanel.tsx     concerns, severity, verdict
src/api/scoping.ts                           typed client for /api/v1/scoping
```

Route: `/experiments/hypothesis`. Added alongside the existing wizard at `/experiments/new`, not replacing it.

### New — `01-DATA-PIPELINE`

```
platform.scoping_sessions    session_id, hypothesis_text, slot_answers JSON, config JSON,
                             config_hash, approved_hash, status, experiment_id, created_at, updated_at
platform.capability_gaps     gap_id, session_id, requested_concept, why_unavailable,
                             nearest_expressible, suggested_definition, status, created_at
```

### Unchanged — and this is a requirement, not an observation

`02-MODELING`, the experiment runner, `ExperimentConfig`, `experiments.backtest_runs`, `experiments.backtest_predictions`, and every existing endpoint contract.

---

## The question tree is a file, not a prompt

`scoping_tree.yaml` is the centre of this design. It declares every question once, as data.

```yaml
slots:
  - id: target
    binds_to: target                       # dotted path into ExperimentConfig; null = record-only
    question: "What outcome are you predicting?"
    type: enum
    options_from: literal:ats_cover,outright_winner,total_over,team_total_yards
    required: true

  - id: features
    binds_to: features
    question: "Which measurements should the model see?"
    type: multi_select
    options_from: endpoint:/api/v1/features    # live catalog, never hardcoded
    required: true
    note: "Each selection is mirrored home/away — N selected runs 2N features."

  - id: game_universe
    binds_to: methodology.game_universe
    question: "Restrict to a subset of games, or use all regular-season games?"
    type: filter
    options_from: schema:GameUniverseFilter    # today: div_game, week only
    required: false

  - id: falsifier
    binds_to: null                             # RECORD-ONLY
    question: "What result would make you abandon this hypothesis?"
    type: text
    required: true

  - id: prior_attempts
    binds_to: null
    question: "Have you tested a variant of this before? Which experiments?"
    type: text
    required: false
```

Two kinds of node, and the distinction matters:

- **Config slots** (`binds_to` set) — every required field of `ExperimentConfig` must have exactly one.
- **Record-only slots** (`binds_to: null`) — questions worth asking that no config field can hold. `falsifier` and `prior_attempts` are the two that carry real weight: the first is the discipline that separates a hypothesis from a fishing trip, the second is the input the governor needs to detect multiple-comparisons pressure. They are stored on the session and rendered into the brief.

**The conformance test is what makes this structural.** A test asserts, in both directions:
1. Every required field of `ExperimentConfig` is bound by exactly one slot.
2. Filling every slot with its declared type produces a config that passes Pydantic validation.

A tree that could produce an invalid config fails CI. You cannot express a bad question sequence.

`options_from: endpoint:` is equally deliberate. Feature options come from the live catalog at ask-time, so the tree cannot drift from the platform. Filter options come from the `GameUniverseFilter` schema, so when someone later widens it to accept any `curated.games` column, the tree widens for free — no edit.

---

## The two model calls, and their limits

Both live in `claude_scoping.py`. Both return a fixed key set, validated before return. Neither can emit anything the platform will execute.

### Call 1 — Extractor

- **In:** hypothesis text, the slot list, the live feature catalog.
- **Out:** `{slot_id: {value, confidence, evidence_quote}}` plus `unmatched_concepts: [str]`.
- **Cannot:** invent a slot, invent a feature not in the catalog, return free text outside these keys.
- **Structural guard on over-confidence:** an extracted value is a *pre-fill*, never an answer. The tree still asks; the field arrives populated with the quote that produced it. A slot is only marked answered by Matt's explicit confirmation. This is the difference between "it guessed and moved on" and "it guessed and showed you."

### Call 2 — Governor

- **In:** the completed config, record-only answers, and a summary of prior experiments from `experiments.backtest_runs`.
- **Out:** `{concerns: [{severity, kind, message}], verdict}` where `verdict ∈ proceed | proceed_with_caution | reconsider`.
- **Cannot:** block the run. It advises; Matt decides. A governor with a veto becomes a thing to route around.
- **Required to check, at minimum:** estimated sample after slicing against `evaluation.min_sample`; near-duplicates among prior runs (multiple comparisons); whether the requested slice is already represented as a feature; Week 1 cold-start reliance where `start_season` includes an in-progress season.

### Gap drafting (part of call 1's follow-through)

`unmatched_concepts` is checked deterministically against the catalog. Anything genuinely absent produces a `CapabilityGap` row and a message that names the gap, offers the nearest expressible variant, and drafts a definition. "Heavier O lines" should yield: no weight feature exists; nearest expressible is your existing OL composite; suggested definition — snap-weighted mean listed weight of the five OL by depth chart, sourced from `seasonal_rosters`, which is staged but not loaded.

That is the whole answer to "what happens at the wall": a row, a suggestion, and a stop.

---

## Build order

Each stage does one job, reads only the previous stage's output, and is independently rerunnable (`03-pipeline-protocol.md`).

| # | Stage | Agent | Why it must come first |
|---|---|---|---|
| 0 | `scoping_tree.yaml` + conformance test | BACKEND-API | The tree is the contract every other stage reads. Nothing can be built against a tree that does not exist. |
| 1 | `platform.scoping_sessions`, `platform.capability_gaps` | DATA-PIPELINE | Stage 2 has nowhere to persist without these. |
| 2 | Deterministic core: session CRUD, slot resolution, assemble, render, hash, approve, dispatch | BACKEND-API | **Ships a complete working feature with zero AI.** Everything after this is enhancement. |
| 3 | Extractor (call 1) + gap detection | BACKEND-API | Needs stage 2's slot model to pre-fill into. |
| 4 | Governor (call 2) | BACKEND-API | Needs a completed config and prior-run history. |
| 5 | `HypothesisChatPage` and components | FRONTEND | Needs the endpoints from 2–4 to be real. |
| 6 | Test suite | TESTING-QA | Never the same context that produced the code (`CLAUDE.md` core principle 6). |
| 7 | Deploy + verify `ANTHROPIC_API_KEY` scope | DEVOPS | Last. |

Stage 2 is the load-bearing decision in this ordering. After it, the feature works end to end as a text-driven wizard: you answer questions, you get a brief, you approve, it runs. Stages 3 and 4 make it feel like the thing you described. If they are late, bad, or expensive, you still have a shipped feature — not a half-built one.

---

## Binary acceptance criteria

**Stage 0**
- [ ] Test asserts every required `ExperimentConfig` field is bound by exactly one slot; fails if a field is unbound or doubly bound
- [ ] Test constructs a config from all-slots-filled and it passes `ExperimentConfig` Pydantic validation
- [ ] `scoping_tree.yaml` contains zero hardcoded feature names — every feature option resolves via `options_from: endpoint:`
- [ ] Tree declares at least one record-only slot with `binds_to: null`

**Stage 1**
- [ ] `platform.scoping_sessions` and `platform.capability_gaps` exist in `nfl-model-471509`
- [ ] A row can be written and read back with all fields intact, JSON columns included
- [ ] No existing table's schema changed — `bq show` diff on `platform.*` is empty apart from the two additions

**Stage 2**
- [ ] `POST /api/v1/scoping/sessions` returns a session id and the first unanswered slot
- [ ] `POST /api/v1/scoping/sessions/{id}/answers` advances to the next unanswered slot; answering the last returns the assembled config
- [ ] `render(config)` called twice on the same config returns byte-identical markdown
- [ ] `render()` contains no call into `claude_scoping`
- [ ] `POST /api/v1/scoping/sessions/{id}/approve` stores the sha256 of the canonical config
- [ ] `POST /api/v1/scoping/sessions/{id}/dispatch` with an unapproved or mutated config returns 409, and no row is written to `platform.experiment_configs`
- [ ] A full session run end to end produces a row in `platform.experiment_configs` and a run in `experiments.backtest_runs` whose fields are indistinguishable from a wizard-built experiment
- [ ] Zero calls to the Anthropic API occur anywhere in stage 2 — verified by test with the key unset

**Stage 3**
- [ ] Extractor returns only the declared keys; a response with any extra or missing key raises and returns 503 `ai_unavailable`
- [ ] Extractor cannot populate a feature not present in the live catalog — fixture test with a hallucinated feature name is rejected
- [ ] Every extracted slot is returned with `confirmed: false` and cannot be marked answered without an explicit confirm call
- [ ] Fixture "teams with heavier O lines perform better in poor weather" produces a `capability_gaps` row naming OL weight, and does not produce one for weather
- [ ] With `ANTHROPIC_API_KEY` unset, the session still completes via stage 2's path

**Stage 4**
- [ ] Governor returns only the declared keys; verdict is one of the three literals
- [ ] Fixture: a config whose slice yields fewer games than `evaluation.min_sample` produces a concern of severity `high`
- [ ] Fixture: a config matching a prior run on target, features and methodology produces a multiple-comparisons concern
- [ ] Governor output cannot prevent dispatch — test approves and dispatches against a `reconsider` verdict successfully
- [ ] Governor is not decorative: across a 6-fixture set of deliberately flawed configs, it returns non-empty concerns on at least 5

**Stage 5**
- [ ] `/experiments/hypothesis` renders; `/experiments/new` still renders the existing wizard
- [ ] No console errors on load in Chrome 124+
- [ ] Brief preview shows the rendered markdown and cannot be edited in place — edits happen by re-answering a slot
- [ ] Pre-filled slots are visually distinguished from Matt-answered slots and show the evidence quote
- [ ] Approve is disabled until every required slot is answered

**Stage 6**
- [ ] Full test suite passes; count recorded before and after
- [ ] An end-to-end test drives a hypothesis from text to a completed backtest run
- [ ] TESTING-QA did not write, and does not modify, any stage 0–5 implementation file

**Stage 7**
- [ ] `ANTHROPIC_API_KEY` resolves in the deployed Cloud Run revision
- [ ] `/experiments/hypothesis` reachable on the live frontend
- [ ] Live smoke test: one hypothesis end to end, experiment visible in the experiments list

---

## Where this is likely to fall over

Named now, before they happen.

**1 — The extractor fills a slot wrongly and it is never questioned.** The highest-consequence silent failure in the design, and the reason pre-fills are structurally separated from answers. If a stage-3 implementation ever marks an extracted slot as answered without a confirm call, the feature is worse than the wizard, because it looks like it asked.

**2 — The brief and the config drift.** Closed by D-4: `render()` is a pure template function and byte-identical rendering is an acceptance criterion. The way this breaks is someone adding a nice LLM-written summary paragraph to the brief. That is a contract violation, not a polish task.

**3 — The approval hash gets bypassed.** Approve stores a hash; dispatch recomputes and compares. The likely bug is canonicalisation — key ordering or float formatting making two identical configs hash differently, or two different configs hash the same. `hashing.py` gets its own tests.

**4 — Catalog drift between approve and dispatch.** BUG-002 already established that features get deprecated under live experiments. Validate the catalog at dispatch, not only at approve.

**5 — The governor becomes wallpaper.** A layer that always says "proceed" trains you to skip it, and then it is worse than absent. The 6-fixture floor in stage 4 acceptance exists specifically to prevent shipping a decorative governor.

**6 — Scope creep into free-form chat.** The pressure will be real: it is a chat box, and the obvious next request is "just let it answer questions about the data." That is the ADR-011 boundary. It is a new plan, not an extension of this one.

**7 — Cost and latency in the request path.** Two calls per session, `claude-haiku-4-5` per existing config default. Bounded by design; monitor rather than pre-optimise.

---

## Kill-switches

Stop immediately, write to the escalation file, do not continue past:

- **Any change to `ExperimentConfig`, the runner, or an existing endpoint contract is required.** This feature is additive only. If a stage cannot be built without changing one of those, the plan is wrong and needs revision, not a workaround.
- **Any stage requires MODELING work.** Same reason.
- **Any stage requires the chat to hold a BigQuery credential of its own, or to execute SQL or generated code.** That is D-2 breaking, and it breaks silently.
- **Stage 2 cannot be completed without an Anthropic API call.** The deterministic core must stand alone; if it cannot, the 60/30/10 split was drawn wrongly.
- **A stage exceeds 4 hours of work.** Stop and re-shape rather than pushing through.
- **Adding a new dependency not already in the backend or frontend manifests.**

---

## Escalation

Write questions to `00-PROJECT-LEAD/HYPOTHESIS-CHAT-QUESTIONS.md`.
Format: the question, what you were doing when you got stuck, what you tried. Then exit. Do not guess forward.

---

## Dependencies

No new packages. `anthropic` is already a backend dependency (`app/claude_inference.py`); `anthropic_api_key` and `anthropic_model` already exist in `app/config.py` with `claude-haiku-4-5-20251001` as the default. Frontend adds no libraries — the chat page uses existing `components/ui/*`.

---

## Delegation

Per `00-PROJECT-LEAD/instructions.md`, on Matt's approval each stage is dispatched by appending a `## CURRENT TASK` block to the owning agent's `instructions.md`, referencing this document. No work orders, no subagents. **Not yet done — awaiting approval.**

ADR-012 to be logged in `docs/DECISIONS.md` on approval: *the hypothesis chat is a bounded client of the existing write API; the question sequence is declared data, not a prompt; the brief is rendered from the config.*
