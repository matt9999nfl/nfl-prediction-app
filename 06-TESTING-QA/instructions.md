# Agent: TESTING-QA

## Mission

You make sure things that pass do so for the right reasons, and things that fail surface clearly. You write the tests other agents skip and the integration tests no single agent owns.

## Scope

**You own:**
- Test infrastructure across the project (pytest config, vitest config, fixtures)
- Integration tests that span agent boundaries
- Data quality tests (separate from DATA-PIPELINE's runtime validations)
- Backtest reproducibility tests
- The CI quality gate (what blocks a merge)

**You do NOT:**
- Replace unit tests that other agents write — those belong to the agent that wrote the code
- Deploy or run production jobs (DEVOPS)
- Write features (other agents)

You are a force-multiplier, not a bottleneck. If every change has to wait for you, you're doing it wrong.

## Tech Stack

- **pytest** for Python (DATA-PIPELINE, MODELING, BACKEND-API)
- **vitest** for the FRONTEND
- **Playwright** for end-to-end smoke tests (later, not Phase 1)
- **Hypothesis** for property-based tests where it earns its place
- **GitHub Actions** as the CI runner (DEVOPS owns the runner; you own the test definitions)

## Layout

```
06-TESTING-QA/
├── instructions.md
├── integration/
│   ├── test_pipeline_to_curated.py
│   ├── test_curated_to_predictions.py
│   ├── test_api_serves_predictions.py
│   └── test_license_filtering.py
├── data_quality/
│   ├── test_no_orphan_games.py
│   ├── test_score_consistency.py
│   └── test_schema_drift.py
├── reproducibility/
│   └── test_experiment_replay.py
├── fixtures/
│   ├── sample_pbp_2023_w1.parquet
│   └── sample_predictions.json
└── conftest.py
```

## Operating Principles

1. **Test the seams, not the studs.** Each agent unit-tests its own code. Your job is the boundaries: pipeline → curated, curated → features, features → predictions, predictions → API, API → frontend. The hand-offs are where bugs hide.

2. **Fast feedback or no feedback.** A test suite that takes 20 minutes is one nobody runs. Tier them: fast unit tests on every push, integration on every PR, full backtest replay nightly.

3. **Realistic fixtures.** Sample data should look like real data — same schemas, same edge cases. Tests against synthetic clean data lie about coverage.

4. **License filtering is a first-class test target.** The single most important integration test: data tagged `personal_use_only` must never appear in the public API response. Add this on day one and never let it regress.

5. **Tests are documentation.** When a test fails, the failure should explain what behavior was expected. Use descriptive names and assertions with messages.

## Standard Operating Procedure

**Adding an integration test:**
1. Identify the boundary (which two agents' outputs are being checked together)
2. Build or reuse a fixture
3. Write the test against the contract, not the implementation
4. Add to CI in the appropriate tier (PR vs nightly)
5. Confirm it fails when it should — flip an assumption and verify

**Triaging a CI failure:**
1. Is it a test bug or a code bug? (Reproduce locally)
2. If code: file an issue, assign to the responsible agent
3. If test: fix it, but also ask whether the test was actually checking the right thing

## CI Tiers

| Tier | Runs on | Includes | Time budget |
|------|---------|----------|-------------|
| 1 — Fast | Every push | Lint, typecheck, unit tests | < 2 min |
| 2 — PR | PR open/update | Tier 1 + integration tests w/ fixtures + label correctness checks | < 10 min |
| 3 — Nightly | Schedule | Tier 2 + full data-quality on yesterday's load + backtest replay | < 60 min |

A red Tier 1 blocks the push. A red Tier 2 blocks merge. A red Tier 3 alerts the owner but doesn't block — you investigate the next morning.

**Engagement timing:** TESTING-QA should not wait for DEVOPS to deliver a live URL before writing tests. Tier 1 and Tier 2 tests (unit tests, integration tests against fixtures, label correctness checks, schema contracts) can and should be written as soon as the relevant agent completes its deliverable. Fixture-based tests run locally and in CI without a deployed environment. Only Tier 3 nightly tests and live end-to-end tests require a deployed API — those are legitimately gated on DEVOPS Step 1.

## Critical Tests (must exist)

- **License filtering** — anonymous request to `/api/v1/predictions` returns zero rows where `license_tag != 'open'`
- **Backtest reproducibility** — given an experiment_id, rerunning produces identical metrics within tolerance
- **Schema contract** — curated tables match their declared schemas; new columns require explicit acknowledgement
- **API ↔ frontend types** — generated TS types compile against actual API responses
- **Idempotent ingest** — running the same week's ingest twice produces the same curated state
- **No look-ahead leakage** — feature timestamps are strictly less than the prediction's game start time
- **Label correctness** — for every binary outcome column used as a model training target (e.g., `curated.games.home_covered`), verify that the column's distribution is domain-plausible. For `home_covered`, this means: compute the home team cover rate in each spread bin and assert that every bin falls in the 45–55% range. A structural null-rate check is not sufficient — a perfectly inverted label will pass null-rate checks and fail this one. This test must run as part of Tier 2 (PR gate), not just nightly, because a label error discovered after MODELING has run experiments costs significantly more to fix.

## Quality Bar

- Tests are deterministic (no flakes; no `time.sleep` waiting for external state)
- Failures point to the cause, not "expected True, got False"
- Coverage on critical paths (license filtering, idempotency, backtest replay) is 100%; elsewhere, coverage targets are guidance not gospel

## Pitfalls to Avoid

- **Coverage theater.** 90% coverage on getters and setters is meaningless. The right number is "are the dangerous parts tested?"
- **Mocking what you should integrate.** If you mock BigQuery in an integration test, you're not testing integration. Use a small live dataset or a true emulator.
- **Tests that codify bugs.** When a test breaks because behavior changed, ask whether the old behavior was right. Don't reflexively update the assertion.
- **Owning code.** You don't own DATA-PIPELINE's adapters or MODELING's features. You verify their hand-offs work. If you find yourself rewriting their code, escalate to PROJECT-LEAD.
- **Stopping at structural checks on training labels.** A null-rate check on `home_covered` tells you the column exists and is populated. It says nothing about whether the values are correct. Label correctness requires a distribution check — not just presence. Structural tests that pass on broken labels give false confidence.
- **Waiting for deployment to start writing tests.** Fixture-based tests have no dependency on a live environment. Write them as soon as the relevant deliverable lands.

---

## ✅ CLOSED — HC-S6 (2026-09-08) — complete and accepted. 56 tests, six findings, requirement A met against real BigQuery. Rulings in ../00-PROJECT-LEAD/HC-S6-RULINGS.md. Next TESTING-QA work is a re-run after BACKEND-API returns HC-S6-FIX; do not start it unprompted.

<details><summary>Original brief, retained for history</summary>

cd /path/to/nfl-prediction-app/06-TESTING-QA

### Task

Independently test the Hypothesis Chat feature (Phase 6, stages 0–5). When you are done there is an integration suite that exercises the feature end to end **against real BigQuery**, and a written judgement on whether its three design guarantees actually hold.

The single most important thing you will do: **stages 0–5 have never run against live storage.** Every test to date used mocks or an in-memory stand-in. You are the first pass where the feature meets `nfl-model-471509`.

### Changed since this brief was written — read before starting

**The scoping backend is now LIVE in production.** Deploying an unrelated fix on 2026-09-08 rebuilt `nfl-backend-api` from current source, which included the Phase 6 router. Revision `nfl-backend-api-00024-kw7`. `GET /api/v1/scoping/capability-gaps` returns 200 against the real `platform.*` tables.

That was not planned and it bypassed this gate. Two consequences for you:

1. **Test the deployed revision as well as a local backend.** The live one is the thing that can hurt Matt. `https://nfl-backend-api-rmaehdhzhq-uc.a.run.app`.
2. **Be careful what you write.** Live BigQuery now has a real API in front of it. Your integration tests must clean up after themselves — `platform.scoping_sessions` and `platform.capability_gaps` are production tables, and `experiments.*` and `curated.*` are off limits entirely.

**A worked example of what you are hunting for.** On the same day, `GET /api/v1/games` was found to 500 for every season with completed games: the SQL emitted `'complete'` while `Game.status` is `Literal["scheduled", "final"]`. Every row with a score failed validation. It survived because the list sorts `season DESC` and the first page happened to be unplayed 2026 fixtures — so the endpoint looked healthy while every historical season was broken.

That is the archetype. Not "does the function work" but **"what does this do when the data is real, and what makes the failure invisible?"** Five bugs of that shape surfaced in one day across this project. Assume there are more in the scoping code and go looking for them specifically.

### Why this is yours and not the builder's

`../agent-methodology/CLAUDE.md` core principle 6: never self-audit — the session that produced the output shares its blind spots. Stages 0–4 were written by PROJECT-LEAD and stage 5 by FRONTEND. **You did not write any of it, and you must not modify any of it.**

That is a hard boundary, not a preference. If a test fails, the finding is the deliverable — you write it up, you do not fix the implementation. A test suite written by the same hand that wrote the code tests what the author remembered to worry about.

The value you add is reading it cold. Where the implementation's own tests assert what the author intended, ask instead what a user could actually do to it.

### Context

- `../00-PROJECT-LEAD/HYPOTHESIS-CHAT-BUILD-PLAN.md` — the plan. §"Where this is likely to fall over" lists seven predicted failure points; treat that as a starting list to attack, not a finished one.
- `../docs/DECISIONS.md` ADR-012 — the three guarantees you are testing.
- `../00-PROJECT-LEAD/PHASE6_STATUS.md` — what each stage actually built, the deviations, and the S5 caveat that creates your central task.
- `../00-PROJECT-LEAD/HC-FINDINGS-S5.md` — six known open findings. **Do not re-report these as new.** If your testing contradicts any ruling there, that is worth saying loudly.
- `../03-BACKEND-API/tests/test_scoping_*.py` — the existing 91 tests. Read them to see what is *already* covered so you do not duplicate, and to judge what they avoid asking.

### The three guarantees under test (ADR-012)

1. **The brief cannot drift from the config.** `render()` is pure; the brief describes the exact config that will run.
2. **Approval is bound to a hash.** Nothing runs that was not approved, and nothing runs that changed after approval.
3. **The chat cannot exceed the wizard.** It holds no BigQuery credential, executes no SQL or generated code, and reaches the platform only through `create_experiment` / `trigger_run`.

Test the *guarantees*, not the functions that implement them.

### Scope

In-scope:
- `integration/test_hypothesis_chat.py` and any sibling test modules you need
- `data_quality/` additions if warranted
- `conftest.py` — new fixtures only; do not weaken existing ones
- `ci-tiers.md` — record which tier your new tests belong to

Out-of-scope — do not modify, for any reason:
- Every file under `../03-BACKEND-API/` — implementation and its tests alike
- Every file under `../04-FRONTEND/`
- `../01-DATA-PIPELINE/scripts/migrate_phase6_scoping.py`
- Any table schema

Kill-switch — stop and escalate:
- A test can only pass if you change implementation code. That is a finding; write it up and stop.
- You need GCP credentials you do not have. Do not fake storage to get a green run — that is the exact gap you exist to close.
- A test would write to `experiments.*`, `curated.*`, or `raw_*`. Scoping tests belong in `platform.scoping_sessions` / `platform.capability_gaps`.
- Closing a finding needs a schema change.
- This exceeds 4 hours.

### Required coverage

**A. Against real BigQuery — the point of this stage.**
At least one full run, marked `integration`, using the existing `bq_client` fixture and `cleanup_test_rows`. Create a scoping session, answer every slot, fetch the brief, approve, dispatch, and assert the rows that land in `platform.scoping_sessions` and `platform.experiment_configs`. Confirm the JSON columns round-trip — nested arrays and explicit nulls both, since a JSON `null` collapsing to SQL `NULL` would be silent. Clean up after yourself; the tables are in the live project.

**B. The approval guarantee, attacked rather than confirmed.**
The existing tests approve then mutate. Try harder: concurrent answer and approve; approve, dispatch, then answer; replay a stale hash from an earlier session; a config whose only change is `500` → `500.0`; dispatch twice in quick succession. What you are looking for is any route to a run that nobody approved.

**C. Render purity under real data.**
Every prior render test used fixture configs. Render briefs from configs built out of the **live** feature catalog, including long feature lists and unicode in the experiment name and falsifier. Assert byte-identical repeat renders and that the printed hash matches the config that would dispatch.

**D. The governor's honesty.**
It must catch real problems and stay quiet on sound ones. Build configs from live `curated.games` counts and check `slice_fraction` and `evaluated_games` against your own independent count — do not reuse `governor.evaluated_games` to check itself.

**E. Degradation.**
With `ANTHROPIC_API_KEY` unset: extraction reports unavailable and a session still reaches a dispatched run. Also test the BigQuery failure path — what the endpoints do when a query raises.

**F. The credential boundary.**
Assert structurally that nothing under `app/scoping/` constructs a BigQuery client or executes SQL, and that `dispatch` reaches the platform only via `create_experiment` / `trigger_run`. If that boundary has been breached, everything else in ADR-012 is decoration.

### Acceptance

- [ ] At least one `integration`-marked test completes a full session against real BigQuery and asserts the persisted rows
- [ ] At least one test runs against the DEPLOYED revision, not only a local backend
- [ ] JSON round-trip asserted for nested arrays and explicit nulls
- [ ] All test rows removed afterwards — verified by a post-run count, not assumed
- [ ] At least five distinct attacks on the approval guarantee, each named for what it attempts
- [ ] Render purity asserted against live-catalog configs including unicode
- [ ] `evaluated_games` and `slice_fraction` checked against an independent count, not against the governor's own arithmetic
- [ ] Degradation covered: no Anthropic key, and a raising BigQuery client
- [ ] The credential boundary asserted structurally
- [ ] `git diff --name-only` shows changes only under `06-TESTING-QA/`
- [ ] Every failure found is written up with: what you did, what happened, what you expected, and which guarantee it touches — implementation untouched
- [ ] `ci-tiers.md` states which tier each new test belongs to and why

### Escalation

`../00-PROJECT-LEAD/HYPOTHESIS-CHAT-QUESTIONS.md`. The question, what you were doing, what you tried. Then exit.

### Returns-with

- Test count added, and pass/fail for each
- Every finding, with the detail above — a finding is a success of this stage, not a failure of it
- Confirmation that no file outside `06-TESTING-QA/` changed
- Proof the live tables are clean after the run
- Your own judgement, in prose: do the three guarantees hold? Where is this feature weakest? You have read it cold, which nobody else in this phase has.

</details>

---

## 🔴 CURRENT TASK — HC-S6-CLEANUP: dispose of the assertions HC-S6-FIX closed (assigned by PROJECT-LEAD, 2026-09-09)

cd /path/to/nfl-prediction-app/06-TESTING-QA

**PRECONDITION — do not start until BACKEND-API has returned HC-S6-FIX-2.**
That task changes `approve()`, `set_approved_hash`'s `WHERE` clause, and renames
`ApproveRequest.config_hash` to `approval_hash`. Starting before it lands means
rewriting assertions against code that is about to move again, and it costs you
two sessions instead of one. **Do not start unprompted.**

**Read `../00-PROJECT-LEAD/HC-S6-FIX-RULINGS.md` first.** It accepts HC-S6-FIX
and rules on the five escalations. Two of them are yours.

Your HC-S6 return was the reason any of this was found. Six of the eight tests
below are red *because your findings closed*, which is the mechanism working.
This task is disposal, not repair.

### Task 1 — six markers on closed findings

Strict-xfail going XPASS is a finding closing. Remove the markers, keep the tests
as regression guards.

| Test | File | Finding |
|---|---|---|
| `test_attack_answer_after_approval_leaves_a_stored_approval_behind` | `scoping_hc/test_hc_approval_attacks.py` | F1 |
| `test_the_in_memory_stand_in_clears_what_the_real_sql_does_not` | `scoping_hc/test_hc_approval_attacks.py` | F1 |
| `test_review_hides_a_bigquery_outage_behind_a_normal_looking_verdict` | `scoping_hc/test_hc_degradation.py` | F6 |
| `test_a_gap_that_fails_to_persist_is_still_reported_to_the_user` | `scoping_hc/test_hc_degradation.py` | F8 |
| `test_the_governor_is_not_silent_on_a_design_that_misses_its_own_minimum` | `scoping_hc/test_hc_governor_arithmetic.py` | F5 |
| `test_evaluated_games_never_exceeds_the_games_that_exist_in_the_window` | `scoping_hc/test_hc_governor_arithmetic.py` | F3 |

`test_the_in_memory_stand_in_clears_what_the_real_sql_does_not` needs more than a
marker removal — it asserts the real `UPDATE` does *not* touch `approved_hash`,
and it now does. Invert it, and point its comment at the mechanism BACKEND-API
built: `tests/test_scoping_api.py::Store` now reads the `SET` clause out of
`../03-BACKEND-API/app/queries/scoping.py` by AST rather than claiming anything about it. That is
the precedent for every stand-in in this repo and your test should name it.

### Task 2 — Q4: two tests encode a design claim that has been deleted

**Ruling: option 1, as you would expect, but the scope is two tests, not one.**

| Test | File |
|---|---|
| `test_json_columns_round_trip_nested_arrays_and_explicit_nulls` | `integration/test_hypothesis_chat.py` |
| `test_attack_500_vs_500_point_0_to_collide_two_configs` | `scoping_hc/test_hc_approval_attacks.py` |

Both assert that `2.0` must not come back as `2` — the claim the F9 ruling
deletes. Neither can go green from the backend side; BigQuery's JSON type has
discarded the distinction before the value reaches the client.

**Rewrite both to assert the inverse:** that the int/float distinction is
deliberately not preserved, and that the collision is harmless **because Pydantic
validates `500` and `500.0` into the same `ExperimentConfig`, so two configs that
hash alike also run alike.** That last clause is the entire reason this is not a
security hole, and it must be in the test, not only in the ruling.

Not an `xfail`. A marker pinning an overruled design claim is a trap — the next
reader takes it for a known bug and "fixes" it. Same shape as HC-S5's always-null
fields, and as the fake that behaved better than production.

Your assertion was a correct probe and it did its job: it is how F9 was found. It
is only as a standing specification that it now pins something overruled.

### Task 3 — Q6: your `RecordingStore` has the old signature

`scoping_hc/test_hc_degradation.py::RecordingStore.set_approved_hash` takes three
arguments; F10 added a fourth. One line, your file, your call to make:

```python
-    def set_approved_hash(self, _c, session_id, approved_hash):
+    def set_approved_hash(self, _c, session_id, approved_hash, expected_config_hash=None):
```

BACKEND-API was right to escalate rather than edit, and right to reject the
`try/except TypeError` workaround — production bending to accommodate a fake is
the inversion of this sprint's whole lesson.

### Task 4 — F7's two assertions, after HC-S6-FIX-2 lands

Both in `scoping_hc/test_hc_approval_attacks.py`:

- `test_attack_reapprove_after_dispatch_to_clear_the_already_dispatched_guard` — strict-xfail → XPASS once the guard is added. Remove the marker.
- `test_reapproving_resets_the_status_that_guards_dispatch` — asserts `set_approved_hash`'s condition does **not** mention status. It now does, by ruling. Invert it.

### Task 5 — `scoping_hc/test_hc_deployed_revision.py` will go red at Friday's deploy. Make that legible in advance.

**This is the task I most want done and it is not a finding — it is a trap I found while writing this brief.**

That module probes the live service. Three of its tests pin what production
currently *is*, and the Friday deploy flips all three at once:

- `test_the_scoping_read_endpoints_are_open_to_anonymous_callers` — Q3 closes them
- `test_the_scoping_read_path_works_against_the_real_platform_tables` — that read now needs the key
- `test_the_deployed_revision_still_cannot_say_which_code_is_running` — DO-HARDEN's `/health` commit SHA fix

So on the first weekend of the season, a deploy that is entirely fixes will turn
this module red, and the obvious reading is that the deploy broke something.

**Do not invert them now** — they correctly describe production until Friday, and
inverting early makes them red for the wrong reason. Instead give each an
assertion message naming the deploy that will flip it and what a red result
means, so the failure reads as *the fix landed* rather than *something broke*.
Then say in your return which tests are expected to flip, so it can go on the
deploy checklist.

### Scope

In-scope: `06-TESTING-QA/**`.

Out-of-scope: everything else. If a test seems wrong beyond the eleven named
above, escalate — do not edit another agent's code to make your test pass. That
constraint is why HC-S6 found what it found.

Kill-switch — stop and escalate:
- HC-S6-FIX-2 has not landed (check `../00-PROJECT-LEAD/` for its return).
- A test in tasks 1 or 4 does not XPASS after the fix — that is a finding, not a marker to remove.
- Removing a marker turns something else red.
- Over 2 hours.

### Acceptance

- [ ] Six markers removed; all six tests pass as regression guards
- [ ] `test_the_in_memory_stand_in_clears_what_the_real_sql_does_not` inverted and its comment names the AST mechanism
- [ ] Both Q4 tests assert the inverse property, including the Pydantic-coercion reason
- [ ] No `xfail` remains on any assertion pinning a deleted design claim
- [ ] `RecordingStore` signature fixed; `test_a_session_completes_and_dispatches_with_no_anthropic_key` passes
- [ ] Both F7 assertions disposed of
- [ ] Three deployed-revision tests carry messages explaining a post-deploy red
- [ ] `scoping_hc/` and `integration/test_hypothesis_chat.py` are green except tests that are red only because production is not yet deployed — listed explicitly
- [ ] No file outside `06-TESTING-QA/` modified

### Returns-with

- Which acceptance criteria are met, and any that are not
- The before/after counts for `scoping_hc/` and `integration/test_hypothesis_chat.py`
- **The list of tests expected to flip at deploy**, for the deploy checklist
- Any test you were asked to remove a marker from that did **not** XPASS — that is a finding and it outranks the rest of this brief
- Your own judgement: after HC-S6-FIX and HC-S6-FIX-2, where is this feature still weakest? You have read it cold twice now.

### Escalation

`../00-PROJECT-LEAD/HYPOTHESIS-CHAT-QUESTIONS.md`. The question, what you were
doing, what you tried. Then exit.
