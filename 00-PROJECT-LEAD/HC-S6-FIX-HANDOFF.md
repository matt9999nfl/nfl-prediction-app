# HC-S6-FIX — returns-with

**Owner:** BACKEND-API · **Date:** 2026-09-09 · **Wall clock:** ~2h15m
**Tests:** 91 backend scoping tests before → **238 passed, 1 skipped** after (+147, +5 files)
**Files modified:** in-scope only. `git status` in full at the bottom.

---

## 1. Acceptance criteria

| # | Criterion | Status |
|---|---|---|
| 1 | `update_answers` clears `approved_hash` in SQL | **DONE** — verified against real BigQuery 2026-09-09 |
| 2 | In-memory `Store` matches the real SQL; guard test FAILS when the SQL fix is reverted | **DONE** — proof in §3 |
| 3 | Approval hash covers config **and** record-only answers | **DONE** |
| 4 | Governor fold count == `len(build_folds_from_config(...))` across a matrix | **DONE** — 96 cases, against the runner's own source |
| 5 | Scoping reads require the API key; anonymous callers get 401 | **DONE** |
| 6 | `review` with a raising BigQuery client names what it could not check, and does not return `proceed` | **DONE** |
| 7 | A failed gap insert is reported, not dropped | **DONE** |
| 8 | Hash survives a BigQuery round-trip, asserted with a real round-trip | **DONE** — Matt ran it against live BigQuery 2026-09-09, 5 passed |
| 9 | A lost approve race writes zero rows and returns 409 | **DONE** — code + forced-interleaving test |
| 10 | Dry-run dispatch writes nothing, asserted by row counts before and after | **DONE** |
| 11 | `06-TESTING-QA/integration/test_hypothesis_chat.py` passes | **3 of 4, confirmed live.** The fourth cannot pass — HC-S6-FIX-Q4 |
| 12 | All 91 existing backend scoping tests still pass | **DONE** (one replaced, see §5) |
| 13 | No file outside the in-scope list modified | **DONE** |

---

## 2. What changed

**F1 — the stored approval is cleared.** `update_answers` now sets
`approved_hash = NULL` in the same statement. The router no longer assigns it on
the response object; `answer_slot` and `approve` re-read the row and report what
storage says. If the two ever disagree again, the API shows the disagreement
instead of hiding it.

**F2 — the approval covers the whole brief.** New `approval_hash(config,
record_only)` in `app/scoping/hashing.py` is what gets stored and what dispatch
compares. `config_hash` is unchanged, still printed in the brief, still what
`/approve` checks for staleness — so `render()`'s output is untouched and no
already-approved brief is invalidated. That is option (a) of HC-S6-FIX-Q5, which
is still unruled; the residual window it leaves is closed for any client that
sends the new `BriefResponse.approval_hash` back with its approval. Both
behaviours are pinned by tests, including the one documenting the gap.

**F3 — one definition of a fold.** `governor.fold_test_seasons()` uses the
runner's algorithm: first test season is `start + train_seasons`, one season per
fold, `test_seasons` is the stride. `evaluated_games` is now `folds ×
games_per_season`. The duplication cannot be deleted outright — ADR-012
commitment 1 keeps `app/scoping/` free of imports beyond stdlib, pydantic and
siblings, and `walk_forward` pulls pandas, sklearn and xgboost — so
`tests/test_scoping_folds.py` lifts `build_folds_from_config` out of the
runner's own file by AST and compares against it across `train_seasons ×
test_seasons`. Change either definition and it goes red.

**F6 — the review fails loud.** `/review` records every input it could not load
by name and passes them to `governor.review`, which emits a HIGH concern of kind
`upstream_error` naming the check that did not run. The verdict can no longer be
`proceed`. `ReviewResponse` gained `checks_unavailable` and `degraded`. Where
the slice count failed on a config that has a filter, the concern says outright
that the reported figure is the unsliced one and overstates the sample.

The "could not check" logic lives in the caller rather than in
`check_sample_size`, because with `slice_fraction=None` that function genuinely
cannot tell "no filter" from "the count failed" — and guessing would make an
honest no-filter config noisy. The caller knows which happened, so the caller
says so.

**F8 — a gap that failed to persist is reported.** `ExtractResponse` gained
`gaps_not_recorded` (status `not_recorded`) and a `detail` saying plainly that
nothing will surface them later. `extract` still cannot block a session.

**F9 — the hash survives storage.** `canonical_json` folds whole-number floats
to ints; the int/float claim is deleted. `bool` is excluded — it is an int
subclass and must still hash as `true`.

**F10 — the approval write is conditional.** `set_approved_hash` carries the
config hash it believes it is approving and returns whether the write landed;
zero rows → 409 `approval_conflict` with a message saying what to do. A client
that cannot report a row count is treated as "cannot tell", never as zero —
refusing a write nobody can prove failed would be the same silent failure in
the other direction.

**Q3 — reads need the key.** `require_api_key` on all four scoping reads.

**Q2 — dry-run dispatch.** `POST /dispatch?dry_run=true` runs every check
including the approval guard, returns the payload it would have created, and
writes nothing — 200, not 202, because nothing was accepted for processing.

**The lying fake.** `tests/test_scoping_api.py::Store` no longer makes its own
claim about clearing `approved_hash` or about conditional approval. It reads
both properties off the real statement in `app/queries/scoping.py` and behaves
the way that statement behaves. Fixing the SQL and leaving the fake alone would
have left a test that stayed green through a regression; now reverting the SQL
turns the file red. **A fake may only be as kind as the thing it stands in for.**

---

## 3. Proof each guard bites

Each fix reverted in place, the tests that should catch it run, the fix
restored. Full output: reproduce with the revert column below.

| Reverted | Tests that went red |
|---|---|
| F1 `approved_hash = NULL` removed | `test_update_answers_clears_the_stored_approval`, `test_the_in_memory_store_behaves_the_way_the_real_sql_behaves`, `test_changing_only_the_falsifier_invalidates_a_surviving_approval` |
| F2 approve+dispatch back to the config-only hash | `test_changing_only_the_falsifier_invalidates_a_surviving_approval`, `test_dry_run_refuses_a_brief_that_changed_after_approval` |
| F3 stride back to `+= 1` | 55 of 96 matrix cases against the runner's own source |
| F6 `unavailable_inputs` not passed | 4 degradation tests, incl. `test_a_review_that_could_not_run_never_returns_proceed` |
| F8 failed gap dropped again | `test_a_gap_that_cannot_be_written_is_reported` |
| F9 float folding removed | `test_the_hash_survives_a_simulated_round_trip`, `test_the_approval_hash_survives_the_round_trip_too`, `test_a_whole_number_float_hashes_as_its_integer_form` |
| F10 condition removed from the write | `test_the_approval_write_is_conditional...`, `test_the_in_memory_store_behaves...`, `test_an_approval_that_lost_a_race_is_refused_with_409` |
| Q2 dry-run branch disabled | 3 dry-run tests |
| Q3 `require_api_key` removed from one read | `test_an_anonymous_caller_cannot_read_a_scoping_endpoint[.../sessions/{sid}]` |

**One honest note on F1.** Reverting F1 *alone* does **not** turn
`test_changing_an_answer_after_approval_blocks_dispatch` red — that test changes
`min_sample`, a config slot, so the config hash moves and dispatch refuses via
F2 regardless. It is the same archetype one level down: the test's choice of
which answer to change was itself kind. The test that bites on F1 alone changes
a **record-only** slot and asserts the stored approval was cleared;
`test_changing_only_the_falsifier_invalidates_a_surviving_approval` is that
test, and it is in the table above.

---

## 4. What I could NOT verify

**No GCP credentials in this environment** — no `gcloud`, no ADC, no
`GOOGLE_APPLICATION_CREDENTIALS`. The same wall TESTING-QA hit in HC-S6-Q1.
Storage was deliberately not faked to close the gap.

So these stay formally unmet until Matt runs them:

```
gcloud auth application-default login
cd 03-BACKEND-API && pytest tests/test_scoping_hash_roundtrip.py -v
cd 06-TESTING-QA && pytest integration/test_hypothesis_chat.py -m integration -v
```

- ~~criterion 1 — `approved_hash = NULL` against real BigQuery~~ **CLOSED 2026-09-09.**
- ~~criterion 8 — the real round-trip~~ **CLOSED 2026-09-09.** Matt ran
  `tests/test_scoping_hash_roundtrip.py` on Python 3.11 with ADC:
  **5 passed**, including `test_the_hash_survives_a_real_round_trip`. A config
  holding whole-number floats was written to `platform.scoping_sessions`, read
  back through the real query layer, and rehashed to the same value. F9 is
  closed against the thing itself, not against a model of it.

  Two things that run confirmed alongside it, neither of which a unit test
  could reach: `set_approved_hash` returned True against real BigQuery, so
  `num_dml_affected_rows` reports a real count and the new conditional
  `WHERE ... AND config_hash = @expected_config_hash` matches the row it should
  (F10's condition is not accidentally matching nothing). The row was deleted
  and the deletion proved by a post-run count.
- ~~criterion 11 — the three of four that should now pass~~ **CLOSED 2026-09-09.**

**Live run, 2026-09-09, `integration/test_hypothesis_chat.py -m integration`:**
**6 passed, 1 failed, 1 skipped** — from 3 passed, 4 failed, 1 skipped on
2026-09-08. All three fixable failures now pass against real BigQuery:

| Test | Was | Now |
|---|---|---|
| `test_attack_answer_after_approval_leaves_the_stored_approval_behind` | FAILED | **PASSED** — F1 closed in live storage |
| `test_attack_record_only_change_after_approval_still_dispatches` | FAILED | **PASSED** — F2 closed |
| `test_attack_concurrent_answer_and_approve` | FAILED | **PASSED** — F10 closed |
| `test_json_columns_round_trip_nested_arrays_and_explicit_nulls` | FAILED | **FAILED** — `assert False` on `isinstance(..., float)`. HC-S6-FIX-Q4; unfixable from the backend |

The skip is the escalated dispatch test (HC-S6-Q2), now answerable by dry-run
mode. The suite's own post-run count confirms it left no rows in
`platform.scoping_sessions` or `platform.capability_gaps`.

**HC-S6-Q1 is therefore met.** The rulings' consequence table lists HC-S7 as
blocked on items 1-4 and 6; 1-4 are implemented and 6 is done. What remains
before HC-S7 is a ruling on Q4, and on the two unruled findings in Q7 — one of
which (F7) is a live double-dispatch path.

`tests/test_scoping_hash_roundtrip.py::test_the_hash_survives_a_real_round_trip`
skips with a message naming what was not verified, rather than reporting a pass.

---

## 5. TESTING-QA tests that change state, and why

Run: `cd 06-TESTING-QA && NFL_BACKEND_ROOT=../03-BACKEND-API pytest scoping_hc/ -q`
→ **44 passed, 8 failed, 4 xfailed.**

**Six are findings closing — the marker needs removing, by TESTING-QA:**

| Test | Why |
|---|---|
| `test_attack_answer_after_approval_leaves_a_stored_approval_behind` | strict xfail → XPASS. F1 closed |
| `test_the_in_memory_stand_in_clears_what_the_real_sql_does_not` | asserts the real UPDATE does not touch `approved_hash`. It now does — its own message says "F1 may be fixed" |
| `test_review_hides_a_bigquery_outage_behind_a_normal_looking_verdict` | its own message says "F6 may be closed" |
| `test_a_gap_that_fails_to_persist_is_still_reported_to_the_user` | strict xfail → XPASS. F8 closed |
| `test_the_governor_is_not_silent_on_a_design_that_misses_its_own_minimum` | strict xfail → XPASS. F5 closed |
| `test_evaluated_games_never_exceeds_the_games_that_exist_in_the_window` | strict xfail → XPASS. F3 closed |

**One is the F9 contradiction — HC-S6-FIX-Q4:**
`test_attack_500_vs_500_point_0_to_collide_two_configs` asserts the design claim
the F9 ruling deletes. Same root cause as the fourth integration failure.

**One is my change breaking a stand-in — HC-S6-FIX-Q6:**
`test_a_session_completes_and_dispatches_with_no_anthropic_key` fails with
`TypeError: got an unexpected keyword argument 'expected_config_hash'`. Their
`RecordingStore` takes the old three-argument signature. One line to fix; I did
not touch their file.

The two structural suites that constrain this work — the credential boundary and
the dispatch/render purity checks — **all still pass.**

---

## 6. Where I think the rulings are wrong or incomplete

They were written by the person who wrote the bugs, so here is my read.

**The rulings are right on substance.** F1, F2, F3, F6, F9 and F10 each name the
real mechanism, and F3's insistence on removing the duplication rather than
patching the formula is the part that will keep paying.

**Three gaps:**

1. **F9's ruling and TESTING-QA's tests cannot both stand** (Q4, raised
   2026-09-08, still open). The ruling is correct — the int/float distinction
   was unenforceable past the storage boundary and fails closed into a wedged
   session — but two of their tests encode the deleted claim and one of them can
   never go green from the backend side. Acceptance criterion 11 is unmeetable
   as written until this is ruled.

2. **F4 and F7 have no ruling at all** (Q7). F7 is a live double-dispatch path
   in production today: dispatch → approve again → dispatch again mints a second
   experiment and a second Cloud Run job. The fix is two lines. I left it because
   it is unruled and because closing it flips a TESTING-QA assertion, but it
   should not sit unruled while the service is live.

3. **F2's ruling does not say whether `render()` changes** (Q5, still open). I
   took the reading that does not trip the kill-switch, and closed as much of the
   remaining window as I could without it. The brief's closing paragraph now
   promises something the document does not quite do — worth a decision either
   way.

**One thing the rulings say that I would put more strongly.** "The governor must
not reimplement the runner's fold logic" cannot be fully honoured while ADR-012
commitment 1 forbids `app/scoping/` from importing anything outside stdlib and
pydantic. The two definitions still exist; what has gone is the freedom for them
to disagree. If that is not good enough, the fold algorithm needs to move to a
shared dependency-free module both projects import — which is a structural change
across 02-MODELING and 03-BACKEND-API, and a bigger decision than this sprint.

---

## Appendix — files

```
 M 00-PROJECT-LEAD/HYPOTHESIS-CHAT-QUESTIONS.md   escalations Q6, Q7, Q4/Q5 status
 M 03-BACKEND-API/app/queries/scoping.py          F1, F10
 M 03-BACKEND-API/app/routers/scoping.py          F1, F2, F6, F8, Q2, Q3
 M 03-BACKEND-API/app/schemas/scoping.py          F2, F6, F8, Q2
 M 03-BACKEND-API/app/scoping/governor.py         F3, F6
 M 03-BACKEND-API/app/scoping/hashing.py          F2, F9
 M 03-BACKEND-API/tests/test_scoping_api.py       the fake now reads the real SQL
 M 03-BACKEND-API/tests/test_scoping_core.py      F9: one test replaced by three
 M 03-BACKEND-API/tests/test_scoping_governor.py  fake signature mirrors F10
?? 03-BACKEND-API/tests/test_scoping_storage_contract.py
?? 03-BACKEND-API/tests/test_scoping_folds.py
?? 03-BACKEND-API/tests/test_scoping_guarantee.py
?? 03-BACKEND-API/tests/test_scoping_degradation.py
?? 03-BACKEND-API/tests/test_scoping_hash_roundtrip.py
   00-PROJECT-LEAD/HC-S6-FIX-HANDOFF.md           this file (new)
```

`00-PROJECT-LEAD/DELEGATIONS.md` was already modified before this task started;
I did not touch it.

**Not deployed.** The scoping backend is live at revision
`nfl-backend-api-00024-kw7` and F1, F4 (unruled) and F7 (unruled) are live
defects today. Nothing here has been redeployed — the brief did not ask for it,
and Q3 in particular changes the auth surface the frontend will meet.
