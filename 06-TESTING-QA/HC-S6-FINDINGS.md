# HC-S6 Findings — Hypothesis Chat, read cold

**Owner:** TESTING-QA · **Date:** 2026-09-08
**Brief:** `06-TESTING-QA/instructions.md` → CURRENT TASK HC-S6
**Suite:** `06-TESTING-QA/scoping_hc/` and `06-TESTING-QA/integration/test_hypothesis_chat.py`
**Escalations:** `00-PROJECT-LEAD/HYPOTHESIS-CHAT-QUESTIONS.md` (HC-S6-Q1, HC-S6-Q2)

No file outside `06-TESTING-QA/` was modified. The findings below are written
up, not fixed — core principle 6, and the brief's hard boundary.

**Run:** 48 passed · 8 xfailed (each an open finding) · 1 module skipped for
want of credentials.

Do not read the count as a pass. **Requirement A — the whole point of this
stage — is UNMET.** See HC-S6-Q1.

---

## Summary

| # | Finding | Guarantee | Severity | Proven |
|---|---|---|---|---|
| F1 | `update_answers` never clears the stored `approved_hash`; only the response body pretends it did | 2 | **High** | Source + the stand-in disagreement |
| F2 | The approved hash covers the config, not the brief — two different briefs, one hash | 1, 2 | **High** | Executed, live catalog |
| F3 | `evaluated_games` treats `test_seasons` as a multiplier where the runner treats it as a stride — up to 7.15× overstatement | — | **High** | Independent count from real data |
| F5 | Because of F3, the governor returns "proceed" with zero concerns on a design that misses its own stated minimum | — | **High** | Executed |
| F7 | `approve()` has no already-dispatched guard, and it resets the status that guards `dispatch()` | 2 | **Medium** | Source |
| F4 | `GAMES_PER_SEASON` is a flat 272; 2015–2020 were 256-game seasons | — | Low | Independent count |
| F6 | A failed slice count is indistinguishable from no slice, and it fails toward a larger apparent sample | — | Medium | Executed |
| F8 | A capability gap that fails to persist is dropped from the response as well as the table | — | Medium | Source |

Checked and clean: **the credential boundary holds** (requirement F, 6 tests);
`render()` is pure under the full live catalog and unicode (requirement C);
`capability-gaps` will survive its first real row; `concepts.json` still
resolves against the live catalog; a raising BigQuery surfaces as 502 rather
than 500 or a wrong answer; the session completes and dispatches with no
Anthropic key.

---

## F1 — The stored approval is never cleared, and the response says it was

**Guarantee 2** — "nothing runs that changed after approval."
**Test:** `scoping_hc/test_hc_approval_attacks.py::test_attack_answer_after_approval_leaves_a_stored_approval_behind` (xfail, strict)
Live form: `integration/test_hypothesis_chat.py::test_attack_answer_after_approval_leaves_the_stored_approval_behind`

**What I did.** Read the DML `app/queries/scoping.py::update_answers` actually
emits, and compared it with the router's stated intent and with the in-memory
`Store` the implementation's own tests use.

**What happened.** The `UPDATE` sets `slot_answers`, `config`, `config_hash`,
`status`, `updated_at`. It never mentions `approved_hash`. The router
(`app/routers/scoping.py` L188-189) then patches `approved_hash: None` onto the
**in-memory row it returns to the caller**. So the HTTP response says the
approval was cleared and the database still holds it.

**What I expected.** The comment three lines above says it plainly:
"approved_hash is cleared so approval must be given again."

**Why it survived until now.** `03-BACKEND-API/tests/test_scoping_api.py::Store.update_answers`
sets `approved_hash=None`. Every existing approval test runs against that
stand-in, so `test_changing_an_answer_after_approval_blocks_dispatch` passes
for a reason that does not exist in production. This is the archetype the
brief describes, in the approval path itself — and it is the single best
argument for why HC-S6 had to be a live-storage stage.

**What saves it today.** `dispatch` recomputes the hash from the current
answers rather than trusting the stored `config_hash`. That is genuinely good
design and it is why F1 is not catastrophic on its own: a changed *config*
answer moves the hash and dispatch refuses. F1 becomes reachable only in
combination with F2.

---

## F2 — Two different approval documents, one hash

**Guarantees 1 and 3** — "the brief cannot drift from the config"; "approval is bound to a hash."
**Test:** `scoping_hc/test_hc_render_purity.py::test_two_different_briefs_cannot_share_one_config_hash` (xfail, strict)
Live form: `integration/test_hypothesis_chat.py::test_attack_record_only_change_after_approval_still_dispatches`

**What I did.** Built two configs from the live 49-feature catalog that differ
in exactly one answer — `falsifier` — rendered both briefs, and hashed both
payloads.

**What happened.** The briefs differ. The hashes are identical.
`assemble()` deliberately excludes record-only slots from the config payload,
and `config_hash` is taken over that payload — but `render()` puts the
record-only answers into the brief. Three of the seventeen slots (`mechanism`,
`falsifier`, `prior_attempts`) are inside the approved document and outside the
thing that is approved.

**What I expected.** The brief's own closing paragraph, printed above the
hash, states: *"If any answer changes, the hash changes and approval is
required again — the document you approve and the config that runs cannot
differ."* That sentence is false for three slots.

**Combined with F1, this is a live route to an unapproved run.** Approve the
brief; change the falsifier; the stored approval is untouched (F1) and the
recomputed hash still matches (F2), so `dispatch` proceeds. The experiment that
runs is the one that was approved — but the document Matt signed off is not the
one on file, and the slot that changed is the one the design calls the
discipline separating a hypothesis from a fishing trip.

**Note on what this is not.** It is not the config drifting. The 60% layer is
sound. It is the *scope of the approval* being narrower than the artefact that
carries it, which is the same class of failure ADR-012 commitment 3 exists to
close, one layer out.

---

## F3 — `evaluated_games` and the runner disagree about what `test_seasons` means

**Test:** `scoping_hc/test_hc_governor_arithmetic.py::test_evaluated_games_matches_an_independent_count_at_test_seasons_2` and `::test_evaluated_games_never_exceeds_the_games_that_exist_in_the_window` (both xfail, strict)

**What I did.** Built the reference number from two sources that owe the
governor nothing: real per-season game counts paged out of the deployed
`/api/v1/games`, and the fold enumeration
`02-MODELING/backtests/walk_forward.py::build_folds_from_config` actually
performs.

**What happened**, on the tree's own default window (2015–2025, 4 training
seasons):

| `test_seasons` | Governor says | Runner will evaluate | Seasons tested | Overstatement |
|---|---|---|---|---|
| 1 | 1,904 | 1,871 | 2019–2025 | 1.02× |
| 2 | 3,808 | 1,072 | 2019, 2021, 2023, 2025 | **3.55×** |
| 3 | 5,712 | 799 | 2019, 2022, 2025 | **7.15×** |

`governor.evaluated_games` computes `(span − train) × test_seasons × 272`.
`build_folds_from_config` uses `test_seasons` as the **stride between folds**
and tests exactly one season per fold. The two only agree at `test_seasons=1`.

At `test_seasons=3` the governor reports 5,712 evaluated games from a window
containing 2,895 games in total — an estimate larger than the universe it is
drawn from. That form needs no agreement about fold semantics to be wrong.

**What I expected.** The number the user is shown to be the number the runner
will evaluate. `PHASE6_STATUS.md` states the intent exactly: *"folds ×
test_seasons × 272, not the season span — the span is the number people quote;
the folds are the number that matters."* The intent is right; the arithmetic
implements a third thing that is neither.

**Why it survived.** `tests/test_scoping_governor.py::test_evaluated_games_counts_folds_not_seasons`
asserts `== 6 * 272` — the implementation's own formula, restated — and does it
at `test_seasons=1`, the one value where the formula and the runner agree.

---

## F5 — The consequence: the governor says "proceed" to an under-powered design

**Test:** `scoping_hc/test_hc_governor_arithmetic.py::test_the_governor_is_not_silent_on_a_design_that_misses_its_own_minimum` (xfail, strict)

**What I did.** 2015–2025, 4 training seasons, `test_seasons=2`,
`min_sample=1500`, no slice. Called `governor.review`.

**What happened.** `{"concerns": [], "verdict": "proceed"}`.

**What I expected.** A `sample_size` concern at severity `high`. The design
evaluates about 1,072 games against a minimum of 1,500 that the user
themselves set two questions earlier.

**Why this one matters most.** The plan's failure-point 5 is "the governor
becomes wallpaper", and S4 defended against it with a six-fixture floor and a
mirror test. Both pass. The layer is not decorative — it is *confidently
wrong in the quiet direction*. It clears an experiment that fails its own
stated bar, and the reason is arithmetic nobody checked against reality
because the check reused the arithmetic. A governor that warns about nothing
teaches you to skip it; a governor that clears a bad design teaches you to
trust it.

---

## F4 — 272 games per season, for seasons that had 256

**Test:** `scoping_hc/test_hc_governor_arithmetic.py::test_evaluated_games_matches_an_independent_count_on_the_default_window` (xfail, strict)

`GAMES_PER_SEASON = 272` is applied to every season. 2015–2020 were 16-game
seasons (256 games each, counted from `curated.games`), and one 2022 game was
cancelled (271). On the tree's default window the reported figure is 1,904
against a real 1,871.

Small on its own — 1.8%. Recorded because it is the same overstatement
direction as F3 and because `evaluated_games` is presented to the user as a
count, not an estimate.

---

## F6 — A failed slice count reads exactly like no slice at all

**Tests:** `scoping_hc/test_hc_governor_arithmetic.py::test_a_failed_slice_count_is_reported_as_if_no_slice_were_applied` and `scoping_hc/test_hc_degradation.py::test_review_hides_a_bigquery_outage_behind_a_normal_looking_verdict` (both pass — the behaviour is real; the finding is that it is wrong)

**What I did.** Made `sq.slice_fraction` and `sq.list_prior_configs` raise, and
called `GET /sessions/{id}/review` through the app.

**What happened.** HTTP 200. `slice_fraction: null`. `concerns: []`. A verdict.
Byte-identical in shape to a healthy review of a sound experiment.

**What I expected.** Some signal that two of the six checks did not run. The
router logs a warning server-side and returns nothing to the caller.

**Which failure this is.** `agent-methodology/04-debugging-protocol.md`:
*"Silent failures are expensive. The thing keeps running. The dashboard stays
green. The only missing piece is that it stopped doing the job."* During a
BigQuery outage the governor tells the user their experiment is fine, having
checked neither the sample size nor the prior runs — and it degrades toward a
*larger* apparent sample, because `check_sample_size` reads `slice_fraction is
None` as "no slice was applied".

---

## F7 — Re-approving after dispatch re-opens the only guard against a second run

**Test:** `scoping_hc/test_hc_approval_attacks.py::test_attack_reapprove_after_dispatch_to_clear_the_already_dispatched_guard` (xfail, strict)

**What I did.** Read the three endpoints that touch session status.

**What happened.** `answer_slot` and `dispatch` both refuse when the loaded row
says `dispatched`. `approve` checks status not at all, and
`set_approved_hash` sets `status = 'approved'` unconditionally. So: dispatch →
approve again → dispatch again. The second dispatch passes the guard,
`create_experiment` mints a second experiment, `trigger_run` fires a second
Cloud Run Job, and `mark_dispatched` overwrites `session.experiment_id` so the
first experiment is orphaned from the session that produced it.

**What I expected.** A terminal state to be terminal. `dispatched` is the end of
the session lifecycle in `app/scoping/session.py`.

**Not the same as the existing `test_dispatching_twice_is_refused`**, which
dispatches twice in a row without the intervening approve.

---

## F8 — A capability gap that cannot be written is not reported either

**Test:** `scoping_hc/test_hc_degradation.py::test_a_gap_that_fails_to_persist_is_still_reported_to_the_user` (xfail, strict)

`app/routers/scoping.py::extract` catches a failed `insert_gap`, logs it, and
`continue`s. The gap never enters `persisted`, and `persisted` is the entire
`gaps` field of the response. So on a write failure the caller is told there
are no gaps — indistinguishable from a hypothesis the platform can fully
express.

ADR-012's answer to "what happens at the wall" is *a row, a suggestion, and a
stop*. On this path there is no row, no suggestion, and no stop — the session
carries on toward an experiment that cannot answer the question asked.

---

## Contradictions with HC-FINDINGS-S5 — none, but two notes

I found nothing that contradicts the six S5 rulings. Two observations that
touch them:

**F-5 (feature_catalog gaps carry null nearest_expressible / suggested_definition).**
Confirmed still present, and I checked the consequence PROJECT-LEAD did not
have to: those nulls do **not** break `GET /api/v1/scoping/capability-gaps`.
Both fields are `Optional` on `CapabilityGapOut`, and rows built from the real
rule engine validate against the real response model
(`scoping_hc/test_hc_gap_row_shapes.py`). The endpoint will survive its first
real row. The ruling stands unchanged; this just removes a worry from it.

**F-6 (`core.filemode` makes `git diff --name-only` useless).**
Confirmed and still unresolved. Running `git -c core.filemode=false status
--porcelain` reduces ~300 phantom modifications to 5 real entries and makes the
acceptance check possible without changing any file content or any config. That
is a per-command flag, not a repo change, so it needs no ruling from Matt to be
used by an agent today. Offered as a workaround for the blocked acceptance
criterion, not as a substitute for the decision he still owns.

---

## Where this feature is weakest — my own read

The 60% deterministic core is the strongest part and it is stronger than its
own tests demonstrate. `dispatch` recomputing the hash instead of trusting a
stored column is exactly the right instinct, and it is what keeps F1 from
being a serious incident. The credential boundary is real: `app/scoping/`
imports nothing that could reach BigQuery, executes nothing, and holds no SQL.
ADR-012 commitment 1 is not a promise here, it is a property, and it survived
being attacked with a parser rather than a grep.

The weakness is not in any one layer. It is that **every guarantee in this
feature is tested against a model of the world that the same author wrote.**

- The approval guarantee was tested against a `Store` that clears a field the
  real `UPDATE` does not (F1).
- The governor's arithmetic was tested against the governor's arithmetic (F3).
- The brief-cannot-drift guarantee was tested on the config, which is the half
  the hash covers, and never on the half it does not (F2).

Each of those tests is well written. Each asserts the thing the author was
worried about. None of them could fail, because the thing they check against is
downstream of the same understanding that produced the code. That is core
principle 6 stated as a bug report rather than as a rule, and it is why the
three findings that matter all came from replacing the reference with something
external — real SQL text, real season counts, the real runner's fold loop.

The second-order weakness is that **the degradation paths all fail quiet.** F6
and F8 are the same shape: an exception is caught, a warning is logged
server-side, and the response is a normal-looking success with less in it.
Both surfaces — the governor's verdict and the gap record — are the ones whose
entire value is telling the user something is wrong. Failing them toward
silence inverts them.

If I could ask for one thing beyond the fixes: make the governor's
`evaluated_games` come from the same function the runner uses to build folds,
rather than from a formula that restates it. The two have already drifted, and
nothing in the current test suite can notice when they drift again.
