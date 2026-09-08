# Phase 6 Status — Hypothesis Chat

**Owner:** PROJECT-LEAD
**Phase start:** 2026-08-31
**Plan:** `HYPOTHESIS-CHAT-BUILD-PLAN.md` · **Decision:** `../docs/DECISIONS.md` ADR-012

| Stage | Agent | Status |
|---|---|---|
| S0 — scoping tree + conformance test | built directly, on instruction | ✅ Complete |
| S1 — `platform.scoping_sessions`, `platform.capability_gaps` | built directly, via BigQuery console | ✅ Complete |
| S2 — deterministic core | built directly | ✅ Complete |
| S3 — extractor + gap detection | built directly | ✅ Complete |
| S4 — governor | built directly | ✅ Complete |
| S5 — chat page | FRONTEND | ✅ Complete (one caveat — see below) |
| S6 — test suite | TESTING-QA | 🔴 Dispatched 2026-08-31 |
| S7 — deploy | DEVOPS | ⚠️ Backend went live early — see below |

---

## S0 — Complete

**Files added** (all new; nothing existing modified):
- `03-BACKEND-API/app/scoping/__init__.py`
- `03-BACKEND-API/app/scoping/schema.py` — `Slot`, `ScopingTree`, `load_tree()`, `required_leaf_paths()`, `all_leaf_paths()`
- `03-BACKEND-API/app/scoping/scoping_tree.json` — 17 slots
- `03-BACKEND-API/tests/test_scoping_tree.py` — 16 tests

**Result:** 16 passed. Suite collects 201 tests with no import breakage.

### Acceptance

| Criterion | Result |
|---|---|
| Tree exists and parses | ✅ 17 slots |
| Every required config field bound by exactly one slot | ✅ 11 required leaves, all bound |
| No field bound twice | ✅ enforced in `ScopingTree` validator *and* asserted in test |
| All-slots-filled produces a valid request | ✅ |
| Test fails when a slot is removed | ✅ removed `min_sample` → 4 failures, restored → 16 pass |
| Zero hardcoded feature names | ✅ asserted against a fixture catalog |
| ≥2 record-only slots incl. a falsifier | ✅ `mechanism`, `falsifier`, `prior_attempts` |
| Every `options_from` uses one of three forms | ✅ enforced at model level |
| No file outside `app/scoping/` and the test touched | ✅ both appear as untracked; nothing else edited |
| Existing suite passes, count before/after | ⚠️ **Not established — see below** |

### Deviations from the plan, and why

1. **`scoping_tree.json`, not `.yaml`.** `pyyaml` is not in `pyproject.toml` and the kill-switch forbids adding a dependency. JSON costs hand-editing comfort and nothing else. Adding `pyyaml>=6.0` to `pyproject.toml` is the one-line reversal if Matt prefers YAML.

2. **Tree binds to `ExperimentCreateRequest`, not `ExperimentConfig`.** `ExperimentConfig.target` was loosened to plain `str` so legacy BigQuery rows don't crash the list endpoint (`app/schemas/experiments.py` L91). Binding there would let the tree offer an invalid target and still pass conformance. `ExperimentCreateRequest` carries the strict 4-value `Literal` and is what the chat actually POSTs. The plan and ADR-012 say `ExperimentConfig`; this is the correct reading of that intent, recorded here rather than silently applied.

3. **A slot may bind a nested model, not only a leaf.** `methodology.game_universe` is answered as one filter question, not three. `all_leaf_paths()` was corrected to permit this — the conformance test caught the original bug.

### Open — S0

**The existing suite's pass baseline was never established.** 201 tests collect cleanly, so nothing is broken at import time, but the suite cannot *run* to completion in this environment: tests reach for GCP and hang without credentials, and the sandbox has Python 3.10 against the project's `requires-python = ">=3.11"`. The before/after count in the acceptance criteria is therefore unmet. It needs one run on a machine with credentials — same blocker as S1.

---

## S1 — Complete

Executed 2026-08-31 in the BigQuery console (`nfl-model-471509`), signed in as Matt. The sandbox shell has no gcloud, no ADC and no key file, so the migration script could not be run there; the DDL executed was **derived from that script's `NEW_TABLES` definition**, not hand-written, so the two cannot disagree.

**Files added:**
- `01-DATA-PIPELINE/scripts/migrate_phase6_scoping.py` — idempotent, self-validating, follows the `migrate_phase2.py` pattern
- `00-PROJECT-LEAD/PHASE6_STAGE1_DDL.sql` — the derived console DDL

### Acceptance

| Criterion | Result |
|---|---|
| Both tables exist in `nfl-model-471509` | ✅ job SUCCESS, 2 statements |
| Round-trip write and read, JSON intact | ✅ nested array path (`$.features[0].dataset` → `curated`), explicit JSON null preserved as `null` (not lost to SQL NULL), and scalar `2015` all read back correctly |
| `experiment_id` type matches `experiment_configs` | ✅ both `STRING` |
| No pre-existing table changed | ✅ `platform` table count 4 → 6: exactly two added, none altered or dropped |
| Migration script idempotent | ⚠️ `CREATE TABLE IF NOT EXISTS` is idempotent by construction and the script uses `exists_ok=True`, but **the script itself has never been executed** — see below |
| Schema file per table | ✅ schemas live in the migration script, matching the Phase 2 convention (there is no `schemas/` directory in this repo) |
| No scheduled job or ingest path modified | ✅ new files only |

The probe row (`session_id = '__roundtrip_test__'`) was deleted; `SELECT COUNT(*)` returns 0. Both tables are empty.

### Open — S1

`migrate_phase6_scoping.py` has never been run. The tables it creates now exist, so a first run should be a no-op that passes its own validation — but "should" is not "did". Run it once on a machine with credentials to confirm the script and the deployed schema agree. Until then the script is unproven, and the project's own pitfall applies in reverse: data exists that no verified script produced.

---

## S2 — Complete

**Files added:** `app/scoping/{hashing,assemble,render,session}.py`, `app/queries/scoping.py`, `app/schemas/scoping.py`, `app/routers/scoping.py`, `tests/test_scoping_{core,api}.py`. **Modified:** `app/main.py` — two lines, import and `include_router`.

**Result:** 51 tests passing across the three Hypothesis Chat files (16 tree + 21 core + 14 API). Suite collects 236, up from 201.

**Seven endpoints live** under `/api/v1/scoping`: `POST /sessions`, `GET /sessions/{id}`, `POST /sessions/{id}/answers`, `GET /sessions/{id}/brief`, `POST /sessions/{id}/approve`, `POST /sessions/{id}/dispatch`, `GET /capability-gaps`.

### The three guarantees, and the tests that hold them

| Guarantee | How it is enforced | Proof |
|---|---|---|
| `render()` is pure | No model, no BigQuery, no clock. A test greps `render.py` for `claude_scoping`/`anthropic`/`bigquery` and fails if any appear — the named contract violation is "someone adds a generated summary paragraph", so it is guarded rather than left to review. | Byte-identical across 5 calls; identical under shuffled key order |
| Canonical hashing | Sorted keys, no insignificant whitespace, ints and floats kept distinct (`min_sample: 500` and `500.0` validate differently and must not collide). | Key order at both levels doesn't move the hash; any value change does |
| Nothing runs unapproved | `dispatch` **recomputes** the hash from the current answers rather than trusting the stored `config_hash`, then compares to `approved_hash`. Any answer change clears the approval. | Disabling the guard fails exactly `test_dispatch_without_approval_is_refused` and `test_changing_an_answer_after_approval_blocks_dispatch`; restoring it returns 14/14 |

### The structural claim, made literal

`dispatch` calls `create_experiment` and `trigger_run` — the wizard's own handlers — rather than writing to BigQuery itself. The chat is not *told* it cannot exceed the wizard; it runs the wizard's code. `app/scoping/` contains no SQL and holds no BigQuery client.

**Stage 2 needs no Anthropic key**, and a test asserts it with the variable deleted. The ordering claim in the plan holds: this is a complete, usable feature with no model in the loop.

### Notes worth keeping

- The stored config omits optional slots left blank so Pydantic applies its own defaults; `model_dump()` on the dispatched body materialises them as explicit nulls. Same experiment. The dispatch-fidelity test compares post-validation on both sides — comparing raw dicts fails on that difference while catching nothing real.
- `_IncludedRouter`: this sandbox's FastAPI is newer than the project pins and defers route expansion, so `app.routes` does not list endpoint paths. Verify via `app.openapi()['paths']` instead. Not a code issue; it will mislead the next person who checks.

---

## S3 — Complete

**Files added:** `app/claude_scoping.py`, `app/scoping/gaps.py`, `app/scoping/concepts.json`, `tests/test_scoping_extract.py`. **Modified:** `app/routers/scoping.py`, `app/schemas/scoping.py`.

**Result:** 20 new tests; 71 passing across the four Hypothesis Chat files. Suite collects 256, up from 236. Eighth endpoint: `POST /api/v1/scoping/sessions/{id}/extract`.

### The contract on the model, enforced not requested

`_validate` refuses rather than repairs — a silently corrected response is how a wrong pre-fill arrives looking confident. It rejects missing keys, **extra** keys, slot ids not in the tree, and any feature not in the live catalog. That last one is the hallucination that would actually hurt: an invented `ol_avg_weight` would reach the user looking like a real selection they made.

**A pre-fill is never an answer.** Extraction does not advance the session by even one question; the pre-fill arrives attached to a question that still gets asked, carrying the words from the hypothesis that produced it. Proven by mutation: making `extract` commit its pre-fills fails `test_a_prefill_does_not_answer_the_question`, and only that test.

**Extraction cannot block a run.** With no API key the endpoint returns `extraction_unavailable: true` and the session completes normally — asserted end to end.

### Gap detection is a rule engine, not a second model call

`concepts.json` maps domain concepts to what the platform already has. Its job is to kill **false** gaps: a model reporting "weather is unavailable" is wrong — `temp`, `wind`, `roof_dome` exist — and this corrects it deterministically. A test asserts every feature named in `concepts.json` exists in the live catalog, so a stale alias fails the build instead of silently resolving to nothing.

`detect_gaps` reads the allowed slice fields from `GameUniverseFilter` itself. A test proves the consequence: widen the filter to accept `temp`, and the weather gap stops being reported with no code change here.

### ⚠️ Acceptance criterion changed — read this

The build plan's Stage 3 criterion said Matt's hypothesis should produce **one** gap (OL weight) and **none** for weather. **Implemented behaviour produces two**, and the criterion was wrong.

I wrote it while still believing weather was simply available. It is available as a **model feature** and unavailable as a **game-universe slice** — and "heavier O lines perform better *in poor weather*" is a slice claim. Reporting no gap would tell Matt the hypothesis is fully expressible when it is not; adding `temp` as a 53rd input column does not answer a conditional question.

So gaps are now classified in two kinds:

| Kind | Meaning | Matt's hypothesis |
|---|---|---|
| `feature_catalog` | The measurement does not exist at all | OL weight — no weight/size feature anywhere; the data is in `seasonal_rosters` parquet, unloaded |
| `filter_schema` | It exists as a feature but the game universe cannot be restricted by it | poor weather — `temp`/`wind`/`roof_dome` are inputs, not slices |

Making the code match a criterion I now know to be wrong would have been the worse choice. Flagged rather than quietly changed.

---

## S4 — Complete

**Files added:** `app/scoping/governor.py`, `tests/test_scoping_governor.py`. **Modified:** `app/queries/scoping.py`, `app/routers/scoping.py`, `app/schemas/scoping.py`.

**Result:** 20 new tests; 91 passing across the five Hypothesis Chat files. Suite collects 276. Ninth endpoint: `GET /api/v1/scoping/sessions/{id}/review`.

### Every check is deterministic, and that is the point

The plan put the governor in the 10% AI layer. Building it showed all four required checks are arithmetic — sample size, duplication, cold start, threshold plausibility — so they are done as arithmetic. The failure mode for this layer was never being wrong; it was being decorative, and a governor that depends on a model returning something useful will, on the day it returns "looks good" to a bad experiment, have taught Matt to skip it. Arithmetic cannot have that day.

A model layer can still be added on top for judgment the arithmetic cannot reach — mechanism/feature mismatch, an unfalsifiable falsifier. Nothing depends on it.

### What it checks

| Check | What it catches |
|---|---|
| `sample_size` | Real slice counts from `curated.games`, not estimates. Also catches a design that holds nothing out — train window as long as the season span means zero evaluated games |
| `implausible_threshold` | A bar at or above 57% ATS, which the project's own SOP treats as a leakage suspect rather than a target |
| `trivial_threshold` | A bar at or below a coin flip — the experiment cannot fail |
| `slice_is_feature` | Conditioning on `div_game` while also feeding it to the model: inside the slice it barely varies |
| `cold_start` | An in-progress season, where early weeks rest on the prior-season-average fallback |
| `duplicate_experiment` / `multiple_comparisons` | Identical and near-variant prior runs (Jaccard ≥ 0.6 on features, same target) |
| `no_falsifier` / `prior_attempts` | The record-only answers earning their place |

`evaluated_games` counts **folds × test_seasons × 272**, not the season span — 2015–2024 with a 4-season training window evaluates 1,632 games, not 2,720. The span is the number people quote; the folds are the number that matters.

### The two tests that keep it honest

- **The floor:** non-empty concerns on at least 5 of 6 deliberately flawed fixtures. Currently 6 of 6.
- **The mirror:** a sound experiment returns **zero** concerns. A layer that warns about everything is the same failure as one that warns about nothing.

### The veto it does not have

`dispatch` never calls the governor, and a test asserts that by reading the source — the veto is *absent*, not merely unused. A separate test drives a `reconsider` verdict all the way to a 202. Matt decides; a governor that could block would become a thing to route around, and the honest signal would go with the veto.

**Note on `slice_fraction`:** the field name is validated against `GameUniverseFilter`'s own allowed values and the operator against a fixed map before either reaches SQL, so nothing from a config interpolates uncontrolled.

---

## S5 — Complete, with one caveat that must not be forgotten

Returned by FRONTEND 2026-08-31, ~30 minutes.

**Files added:** `src/api/scoping.ts`, `src/api/openapi.gen.ts`, `src/components/scoping/{SlotPrompt,BriefPreview,GovernorPanel,CapabilityGapNotice,Markdown}.tsx`, `src/pages/HypothesisChatPage.tsx`. **Modified:** `src/App.tsx` (one route), `src/components/Layout.tsx` (one nav item).

Independently verified here: the backend suite still passes 91/91, which is stronger evidence than mtime that nothing under `03-BACKEND-API` was touched.

### Acceptance

| Criterion | Ruling |
|---|---|
| `/experiments/hypothesis` renders; `/experiments/new` unchanged | ✅ Met |
| `npm run build` / `tsc --noEmit` clean | ✅ Met — 761 kB, 218 kB gzip |
| No console errors on load | ✅ Met — Chromium 141 |
| Zero hardcoded feature or filter names | ✅ Met — grep across all 7 hand-written files for 98 catalog names, both filter fields, four operators, every target/metric/model literal, and `curated` |
| Pre-fill visually distinct, shows evidence quote, needs explicit action | ✅ Met |
| Brief not editable in place | ✅ Met — and structurally so, see deviation below |
| Approve disabled until every required slot answered | ✅ Met — driven by `missing_required` |
| Approve sends the hash from the latest brief; forced 409 re-fetches | ✅ Met |
| `reconsider` verdict does not disable approve or dispatch | ✅ Met |
| Flow completes with `ANTHROPIC_API_KEY` unset | ✅ Met — 5/5 |
| Both gap kinds render distinguishably, with suggested definition | ⚠️ Met with caveat — the UI renders both kinds correctly; the backend supplies `null` for `feature_catalog` definitions. Finding 5, a backend defect, not a UI one |
| Full session end to end against the backend | ⚠️ **Met with caveat — see below** |
| No file outside scope modified | ✅ Met |

### The caveat — read before trusting the end-to-end evidence

The 25/25 browser checks ran against a local backend whose `app/queries/scoping.py` and `app/queries/experiments.py` were replaced with in-memory stand-ins, because the environment has no GCP credentials. Every router, schema, assembler, hasher, renderer, governor and gap rule ran for real; **only storage was faked**, and no file under `03-BACKEND-API` was modified.

So this is genuine evidence for the UI contract and **not** evidence that the flow works against live BigQuery. FRONTEND flagged this itself rather than letting it pass, which is the right call.

**Ruling: closing that gap is HC-S6's job, not HC-S7's.** Two reasons. TESTING-QA already has the infrastructure — `conftest.py` provides a `bq_client` on ADC and an autouse `cleanup_test_rows`, and `pytest.ini` already declares `integration` and `live` markers. And S7 is deploy: finding out at deploy time that the storage layer never worked is the most expensive place to find it. S6's brief requires at least one run against real BigQuery.

### Deviation — `Markdown.tsx`, accepted

Beyond the suggested component split. **Accepted.** The kill-switch forbade new npm dependencies and there is no markdown renderer in `package.json`; writing a small one that emits React elements honours that constraint, and it makes "the brief is read-only" structural rather than promised — there is no `dangerouslySetInnerHTML` and no editable surface. That is the same reasoning as ADR-012 commitment 3 applied one layer out, so it fits rather than bends the design.

### Open items from S5

Six findings raised, all verified in source here rather than taken on report. Specs and ownership in `HC-FINDINGS-S5.md`. None block HC-S6.

---

## ⚠️ S7 partially happened by accident — 2026-09-08

Deploying the `games` endpoint fix rebuilt `nfl-backend-api` from current source, which **includes the Phase 6 scoping router**. Revision `nfl-backend-api-00024-kw7`. `GET /api/v1/scoping/capability-gaps` returns 200 in production.

**This bypassed the HC-S6 gate.** TESTING-QA exists precisely to close the "never run against real BigQuery" gap, and the backend is now doing exactly that, unverified by them.

Not an emergency, and there is a silver lining:
- The endpoints are purely additive; nothing calls them, since the frontend is not deployed.
- Write paths need approval + dispatch, so nothing can run an experiment by accident.
- `capability-gaps` returning 200 is the **first live evidence** that the scoping BigQuery read path works against the real `platform.*` tables — the thing S5's in-memory stand-in could not prove.

**HC-S6 still runs, and its brief is unchanged.** It should now additionally verify the deployed revision rather than only a local backend.

## Observability regression in the same deploy

`/health` now reports `"commit":"unknown"`, where it previously reported `fc297ef`. The build did not inject a commit SHA — likely because it was built from a local directory rather than a tagged source.

Worth fixing rather than shrugging at: *"which code is actually running"* is the exact question that took a week to answer during INC-002, when the pipeline image turned out to be four months old. Losing that signal on the API is a step backwards. DEVOPS item.
 found while verifying — not part of this build

`git status` reports ~300 files as modified. Every one is a permission-bit change (`100644` → `100755`) with a zero-line content diff, left by the OneDrive / machine migration in commit `fc297ef`. `core.filemode` is `true`, so git surfaces all of them.

Consequences: `git diff --name-only` is useless as a review or acceptance check anywhere in this repo, and the next commit from any agent will be ~300 files wide and unreviewable.

`git config core.filemode false` fixes it locally and changes no file content. Not applied — it alters how every other agent session sees the repo, so it is Matt's call.
