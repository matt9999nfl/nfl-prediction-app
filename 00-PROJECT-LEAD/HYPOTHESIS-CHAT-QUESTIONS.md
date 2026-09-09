# Hypothesis Chat — Escalation File

Workers write here when genuinely stuck, then exit. PROJECT-LEAD reads this on the next human turn.

**Do not guess forward. Do not read more files hoping ambiguity resolves. Do not make a decision that belongs to PROJECT-LEAD or to Matt.**

## Format

```
### [STAGE-ID] — [one-line question]
**Date:**
**Agent:**
**What I was doing:**
**What I tried:**
**The question:**
**What I need to proceed:**
```

## Open

### HC-S6-Q1 — There are no GCP credentials in this environment. Requirement A cannot be met. How should it be run?

**Date:** 2026-09-08
**Agent:** TESTING-QA

**What I was doing:**
HC-S6 requirement A — at least one `integration`-marked test that completes a
full scoping session against real BigQuery and asserts the persisted rows,
using the existing `bq_client` fixture. This is the stated point of the whole
stage: stages 0-5 have never run against live storage.

**What I tried:**
- `gcloud` and `bq`: not installed. `~/.config/gcloud`: does not exist.
- `GOOGLE_APPLICATION_CREDENTIALS`: unset. No service-account key file anywhere
  in the repo (`03-BACKEND-API/.env` sets `BIGQUERY_PROJECT` and
  `ANTHROPIC_API_KEY`, no GCP key).
- `bigquery.Client(project="nfl-model-471509")` → `DefaultCredentialsError`.
- The deployed revision instead: reads work anonymously, but every write
  endpoint returns 401 because `OWNER_API_KEY` is configured on
  `nfl-backend-api-00024-kw7`. I do not have that key, and I did not ask for
  it, because driving writes through production is a separate question (Q2).
- This is the same blocker S0 and S1 recorded and it has not moved.

I did **not** fake storage to get a green run. The brief names that as a
kill-switch and it would have been exactly the wrong move here: the most
important finding of this stage (F1) exists *because* the implementation's own
tests run against an in-memory stand-in that behaves differently from the real
SQL. A second stand-in would have hidden it again.

**The question:**
How should the live-storage suite be run? Options as I see them, in the order I
would rank them:

1. Matt runs `gcloud auth application-default login` on the machine that has
   the repo, then `pytest 06-TESTING-QA/integration/test_hypothesis_chat.py`.
   The module is written, complete, and skips cleanly today; it needs nothing
   but credentials.
2. A read/write service-account key scoped to `platform.scoping_sessions`,
   `platform.capability_gaps` and `platform.experiment_configs` only, made
   available to the test environment.
3. A ruling that HC-S6 returns with requirement A explicitly unmet, and that
   HC-S7 must not deploy until it is met.

**What I need to proceed:**
Credentials, or a ruling on option 3. Everything else in HC-S6 is done:
48 tests passing, 8 findings, requirements B (partial), C, D, E and F complete.

---

### HC-S6-Q2 — A full dispatch fires the production experiment runner. Is that in scope, and if so how is it cleaned up?

**Date:** 2026-09-08
**Agent:** TESTING-QA

**What I was doing:**
Writing the requirement-A test that dispatches a session end to end and asserts
the row that lands in `platform.experiment_configs`.

**What I tried:**
Traced what `dispatch` actually causes, rather than assuming it stops at the
config row:

```
POST /scoping/sessions/{id}/dispatch
  → routers/experiments.py::create_experiment
      → INSERT platform.experiment_configs                 [in scope, cleanable]
  → routers/experiments.py::trigger_run
      → UPDATE platform.experiment_configs SET status='running'
      → queries/experiments.py::trigger_experiment_runner
          → POST run.googleapis.com .../jobs/nfl-experiment-runner:run
              → the job writes experiments.backtest_runs
                              and experiments.backtest_predictions
```

So a real dispatch writes to `experiments.*` through one level of indirection.
The HC-S6 brief lists "a test would write to `experiments.*`, `curated.*`, or
`raw_*`" as a kill-switch, and those rows cannot be cleaned up from here —
`experiments.*` is off limits for deletes too, and the root conftest's cleanup
matches `experiment_id LIKE 'test_%'`, which cannot match anything this flow
creates because `create_experiment` assigns `str(uuid.uuid4())`.

It also burns real runner compute and would leave a genuine-looking experiment
in Matt's experiments list.

**The question:**
Three sub-questions, and I need all three answered before writing to production
through this path:

1. Is a real dispatch in scope for HC-S6 at all, or does requirement A stop at
   `platform.experiment_configs` and the 409 guards (which is where I have left
   it)?
2. If it is in scope: is there a way to run the flow without firing the runner
   — a config flag, a scratch dataset, or a test-only job name? I could not
   find one, and I am not permitted to add one, since that is implementation.
3. If the runner must fire: who deletes the resulting `experiments.backtest_runs`
   and `experiments.backtest_predictions` rows, and the `experiment_configs`
   row with the random uuid? That is a DEVOPS or DATA-PIPELINE action, not a
   TESTING-QA one.

**What I need to proceed:**
A ruling on (1). If it is "yes, dispatch for real", then (2) and (3) as well.

The test is written and marked `skip` with this escalation as its reason:
`06-TESTING-QA/integration/test_hypothesis_chat.py::test_a_full_session_dispatches_to_a_real_experiment_config_row`.

---

### HC-S6-Q3 — Should the scoping READ endpoints be open to anonymous callers in production?

**Date:** 2026-09-08
**Agent:** TESTING-QA

**What I was doing:**
Probing the deployed revision `nfl-backend-api-00024-kw7`, read-only.

**What I tried:**
- Every scoping WRITE endpoint returns 401 to an anonymous caller. Good, and
  asserted as a regression guard.
- Every scoping READ endpoint is open:
  `GET /api/v1/scoping/capability-gaps` returns 200 to anyone on the internet,
  and `GET /api/v1/scoping/sessions/{id}` returns the hypothesis text, every
  slot answer and the assembled config to anyone holding the session uuid.

**The question:**
Is that intended? It follows the project's existing convention — reads carry no
key, which is what the public predictions endpoint relies on — so it may be a
deliberate inheritance rather than an oversight. But ADR-012 scoped this
feature as single-user and explicitly deferred auth on that basis, and the
capability-gap list is a readable index of what Matt's platform cannot yet do.
The session read needs a uuid, so it is not enumerable; the gap list needs
nothing.

I have recorded it as an observation, not filed it as a defect, because the
ruling is yours and not mine.
`06-TESTING-QA/scoping_hc/test_hc_deployed_revision.py::test_the_scoping_read_endpoints_are_open_to_anonymous_callers`
asserts the current behaviour so a change either way is visible.

**What I need to proceed:**
Nothing — this does not block HC-S6. It needs a ruling before HC-S7 deploys the
frontend.

---

### HC-S6-FIX-Q4 — The F9 ruling and TESTING-QA's round-trip test contradict each other. One of them has to change, and neither is mine to change.

**Date:** 2026-09-08
**Agent:** BACKEND-API

**What I was doing:**
HC-S6-FIX. Working through the six rulings before writing code, mapping each
ruling onto the TESTING-QA failure it is supposed to turn green. The brief's
acceptance criterion is `06-TESTING-QA/integration/test_hypothesis_chat.py`
passes: the four failures were the specification.

**What I tried:**
Mapping the four live failures to fixes. Three map cleanly:

| Failing test | Fix | Passes after fix? |
|---|---|---|
| `test_attack_answer_after_approval_leaves_the_stored_approval_behind` | F1 | yes |
| `test_attack_record_only_change_after_approval_still_dispatches` | F1+F2 | yes |
| `test_attack_concurrent_answer_and_approve` | F10 | yes |
| `test_json_columns_round_trip_nested_arrays_and_explicit_nulls` | F9 | **no — cannot** |

The fourth is the problem. Its last two lines are:

```python
assert stored["config"] == config, f"config changed in storage: {stored['config']!r}"
# 2.0 must not come back as 2 — int and float hash differently by design.
assert isinstance(stored["config"]["nested"]["array"][1], float)
```

The first of those passes today and always will, because Python's `2 == 2.0`.
The second is the one that fails, and it asserts *exactly the design claim the
F9 ruling deletes* — it even cites it in the comment. It is a storage-layer
assertion, not a hashing one: it tests the type that comes back out of
`_parse_json`, and `canonical_json` is nowhere in its call path.

So the F9 ruling ("normalise, and delete the claim") cannot make it pass. I
checked what could:

- Normalising whole floats in `canonical_json` — no effect. The assertion never
  touches the hash. Test A already passes and still will.
- Restoring float-ness in `app/queries/scoping.py::_parse_json` — impossible.
  BigQuery's JSON type has already discarded the distinction by the time the
  value reaches the client; there is no type metadata left to reconstruct from.
- Storing `config` as STRING instead of the JSON type — that is a schema change
  to `platform.scoping_sessions`, owned by the Stage 1 DDL, and out of my scope.

I did not edit their file. The brief's kill-switch is explicit about that.

**The question:**
TESTING-QA's assertion is a *correct probe* — its failure is how F9 was found,
and it did its job. But as a standing specification it now pins a design
decision you have since overruled, so it can never go green. Which of these do
you want?

1. **TESTING-QA rewrites that assertion** to test the property the F9 ruling
   actually cares about: hash a config containing a whole-number float,
   round-trip it through BigQuery, rehash, assert equality — and assert that the
   int/float distinction is *deliberately not* preserved, with the comment
   updated to say so. This is the test the F9 ruling asks me to write; it
   belongs in their live module rather than duplicated in mine, since mine
   cannot reach live storage (see "what I need" below). **My recommendation.**
2. I add that round-trip-equality test on the backend side, their assertion is
   marked `xfail` with the F9 ruling as the reason, and the acceptance criterion
   is amended to "three of the four failures pass; the fourth is superseded".
3. The F9 ruling is wrong and the int/float distinction should be preserved —
   in which case the fix is a schema change to `platform.scoping_sessions`, not
   anything in `app/scoping/`, and it is a different task with a different owner.

I do not think 3 is right. Your reasoning in the ruling holds: Pydantic already
coerces `500.0` to `500` for an int field, so the distinction was never real
past the schema boundary, and a hash that cannot survive its own storage layer
fails closed and wedges the session. I am flagging it only because option 1
means changing a file I am forbidden to touch, and option 2 means an acceptance
criterion in my own brief cannot be met as written.

**What I need to proceed:**
A ruling on 1 / 2 / 3. Everything else in HC-S6-FIX is unblocked and I can
implement F1, F3, F4, F6, F10 and dry-run dispatch without it — F9's *code*
change is unambiguous and I will make it either way; it is only the disposition
of their assertion, and the acceptance criterion that depends on it, that is
stuck.

Separately, and not a blocker for you to rule on: I cannot verify any of this
against real BigQuery from where I am running. No `gcloud`, no ADC, no
`GOOGLE_APPLICATION_CREDENTIALS` in this environment — the same wall TESTING-QA
hit in Q1. Several acceptance criteria say "verified against real BigQuery, not
a fake". Those stay formally unmet until Matt runs the module himself per the
Q1 Option 1 ruling.

---

### HC-S6-FIX-Q5 — Does F2 change what `render()` prints? The brief's own kill-switch says that is your call, and I think the honest fix requires it.

**Date:** 2026-09-08
**Agent:** BACKEND-API

**What I was doing:**
Planning F2 — making the approval hash cover everything the brief renders,
config *and* record-only answers.

**What I tried:**
Working out whether it can be done without touching `render()`'s output, since
the brief lists that as a kill-switch: *"F2 cannot be done without changing what
`render()` outputs — that would invalidate every brief already approved, and is
a decision for PROJECT-LEAD."*

`render()` ends with:

```
Config hash: `{config_hash(payload)}`

Approving this brief approves that exact hash. If any answer changes, the hash
changes and approval is required again — the document you approve and the
config that runs cannot differ.
```

Two ways to do F2:

**(a) Leave `render()` alone.** The brief keeps printing the config-only hash;
approve and dispatch compare a broader hash computed server-side over config +
record-only answers. The *guarantee* is restored — changing the falsifier now
blocks dispatch. But the document keeps printing a hash that is not the thing
being approved, and its closing paragraph becomes false as written: it promises
that if any answer changes the printed hash changes, and for the three
record-only slots it still would not. It also leaves a real gap: the client
sends `ApproveRequest.config_hash`, so `/approve`'s stale-brief check still only
detects config drift. A falsifier edited between rendering the brief and
approving it would not be caught at approve time — only later, at dispatch.

**(b) The brief prints the approval hash** that actually covers the whole
document, `BriefResponse.config_hash` and `ApproveRequest.config_hash` carry
that value, and the closing paragraph becomes true again. This closes the gap in
(a) completely. It also changes `render()`'s output and therefore the hash of
every brief, which is the kill-switch.

I want (b). ADR-012 commitment 3 is that the approved artefact and the executed
artefact cannot differ, and (a) leaves a window where they still can. (a) also
leaves a document that misdescribes itself, which is the same class of problem
as the lying fake — a thing that says the guarantee holds while it does not.

The cost of (b) is invalidating briefs already approved. **I could not check
whether any exist** — no BigQuery access from here. Given the frontend is not
deployed and writes need `OWNER_API_KEY`, I would expect
`platform.scoping_sessions` to hold no genuine approvals at all, which would
make (b) free. That is checkable with one query and it is the fact your ruling
turns on:

```sql
SELECT COUNT(*) FROM `nfl-model-471509.platform.scoping_sessions`
WHERE approved_hash IS NOT NULL;
```

**The question:**
(a) or (b)? And if (b), do you want the field renamed — `approval_hash`
throughout the schemas, or `config_hash` kept as the wire name to avoid a
frontend change before HC-S7?

**What I need to proceed:**
A ruling on (a) vs (b), and the rename. F2 is the only fix blocked on it; F1,
F3, F4, F6, F10 and dry-run dispatch are independent and ready to go.

**One note you will want regardless of the ruling**, because it changes what
"fix the lying fake" has to mean. Correcting the in-memory `Store` is necessary
but *not sufficient* to make the guard test bite.
`test_changing_an_answer_after_approval_blocks_dispatch` changes `min_sample` —
a **config** slot — so the config hash moves and `dispatch` returns
`approval_mismatch` whether or not the stored `approved_hash` was cleared. The
test stays green through a full regression of F1 even after the fake is honest.
The test that actually bites has to change a **record-only** slot, which is the
F2 path. I will add that one and demonstrate it failing against reverted SQL, as
the returns-with asks. Recording it here because it is the same archetype one
level down: the fake was kind, and so was the test's choice of which answer to
change.

---

### HC-S6-FIX-Q6 — Implementing the F10 ruling changes `set_approved_hash`'s signature, and breaks one TESTING-QA fake I am not allowed to edit.

**Date:** 2026-09-09
**Agent:** BACKEND-API

**What I was doing:**
F10. The ruling: *"`set_approved_hash` should include the config hash it
believes it is approving in its `WHERE` clause, so an approval that lost a race
writes zero rows and returns a clear 409."*

**What I tried:**
Implemented as ruled:

```python
def set_approved_hash(client, session_id, approved_hash, expected_config_hash=None) -> bool
```

`expected_config_hash` defaults to `approved_hash`, so every existing 3-argument
caller keeps working — including all four call sites in
`06-TESTING-QA/integration/test_hypothesis_chat.py`, which need no edit and
whose concurrency test now passes.

One caller does break:
`06-TESTING-QA/scoping_hc/test_hc_degradation.py::RecordingStore.set_approved_hash`
takes exactly three arguments, so
`test_a_session_completes_and_dispatches_with_no_anthropic_key` now fails with
`TypeError: got an unexpected keyword argument 'expected_config_hash'`. That
test is not about any finding — it is the no-Anthropic-key degradation contract,
and it is failing purely because a stand-in has the old signature.

I looked for a way to avoid the signature change:

- **Pass it positionally** — same arity, same TypeError.
- **A second function** (`set_approved_hash_if(...)`) — worse: their fixture
  monkeypatches `set_approved_hash` by name, so the router would bypass the
  stand-in entirely and try a real query against a dummy client.
- **Store the approval hash in the `config_hash` column** so the condition can
  read `config_hash = @approved_hash` with three arguments — this forces
  `/brief` and the session state to report the approval hash as `config_hash`,
  which breaks `test_brief_matches_the_hash_the_state_reports` and makes
  `actual = config_hash(payload)` in `approve()` dead, which
  `test_attack_approve_a_hash_the_client_computed_itself` pins.
- **`try/except TypeError` around the call** — rejected on principle. That is a
  production code path bending itself to accommodate a fake, in a sprint whose
  whole lesson is that fakes must bend to production.

**The question:**
The fix is one line in their file:

```python
-    def set_approved_hash(self, _c, session_id, approved_hash):
+    def set_approved_hash(self, _c, session_id, approved_hash, expected_config_hash=None):
```

Do you want TESTING-QA to make it, or do you want me to? I have not touched it —
the brief forbids editing their tests and says to escalate instead.

**What I need to proceed:**
Nothing blocking. F10 is implemented and its own tests pass. This is one
red test in their suite, caused by my change, and I want it fixed by whoever
owns the file rather than left to look like a regression in the degradation
contract.

---

### HC-S6-FIX-Q7 — F4 and F7 have no ruling. Both are real, neither is in my six, and one of them is live.

**Date:** 2026-09-09
**Agent:** BACKEND-API

**What I was doing:**
Reconciling `06-TESTING-QA/HC-S6-FINDINGS.md` (F1–F10) against
`HC-S6-RULINGS.md`, which rules on F1/F2, F3/F5, F6/F8, F9 and F10.

**What I tried:**
F4 and F7 are ruled on nowhere, and neither appears in the HC-S6-FIX brief's
"six fixes". I have implemented neither, because guessing at an unruled finding
is the thing the brief tells me not to do. Both are recorded in code comments
pointing here.

**F4 — `GAMES_PER_SEASON = 272` applied to 256-game seasons.**
2015-2020 were 16-game seasons; one 2022 game was cancelled. On the tree's own
default window the governor reports 1,904 evaluated games against a real 1,871.
1.8%, and in the same overstating direction F3 was. It matters more than the
size suggests because `evaluated_games` is presented to the user as a count,
not an estimate, and the sample-size check compares it against a minimum the
user set themselves.

The fix is not free: an honest count needs real per-season game counts from
`curated.games`, which means `evaluated_games` takes a season→count map and
`/review` loads it. That puts a BigQuery read behind a number that is currently
pure arithmetic — and under the F6 ruling I have just implemented, a read that
fails must then produce a concern rather than a silent fallback to 272. It is a
coherent design, but it is a design decision, not a bug fix.

**F7 — re-approving after a dispatch re-opens the only guard against a second run.**
`approve()` checks status not at all, and `set_approved_hash` sets
`status = 'approved'` unconditionally. `dispatch` refuses a second run by
checking `status == 'dispatched'`. So: dispatch → approve again → dispatch
again, and you get two experiments, two Cloud Run jobs, and
`session.experiment_id` overwritten so the first experiment is orphaned from the
session that produced it. This is live in production today, mitigated only by
`OWNER_API_KEY`.

The fix is small — an `already_dispatched` guard in `approve()` matching the one
in `answer_slot` — but it flips
`scoping_hc/test_hc_approval_attacks.py::test_attack_reapprove_after_dispatch_to_clear_the_already_dispatched_guard`
from strict-xfail to XPASS, and its sibling
`test_reapproving_resets_the_status_that_guards_dispatch` asserts that
`set_approved_hash`'s condition does NOT mention status. I kept both green by
leaving F7 alone, deliberately, so it is visible rather than half-done.

**The question:**
1. F4: fix it with a real per-season count, keep the flat constant and label the
   figure an estimate in the response, or leave it and close the finding?
2. F7: is the `already_dispatched` guard in `approve()` mine to add now? It is
   two lines and closes a live double-run path. I did not add it because it is
   unruled and it changes a TESTING-QA assertion's outcome.

**What I need to proceed:**
A ruling on each. Neither blocks HC-S6-FIX, which is complete and returned.

---

### HC-S6-FIX-Q4/Q5 — status note from the follow-up session

**Date:** 2026-09-09
**Agent:** BACKEND-API

Q4 and Q5 above were raised on 2026-09-08 and are still open. I was told to
proceed with HC-S6-FIX, so I have — here is exactly what I did in each, so the
rulings can still go either way cheaply.

**Q4 (the F9 contradiction).** I made the code change the ruling asks for:
`canonical_json` folds a whole-number float to its integer form and the claim is
deleted from the docstring. The consequence stands unchanged — 
`integration/test_hypothesis_chat.py::test_json_columns_round_trip_nested_arrays_and_explicit_nulls`
still fails on `assert isinstance(stored["config"]["nested"]["array"][1], float)`
and no backend change can make it pass. A second TESTING-QA test now fails for
the same reason:
`scoping_hc/test_hc_approval_attacks.py::test_attack_500_vs_500_point_0_to_collide_two_configs`
asserts the deleted claim directly. **My recommendation is unchanged: option 1.**
Until it is ruled, the brief's acceptance criterion *"test_hypothesis_chat.py
passes: the four failures were the specification"* is met for three of the four.

I added the round-trip test the F9 ruling asks for on the backend side —
`tests/test_scoping_hash_roundtrip.py::test_the_hash_survives_a_real_round_trip`
— which does a real write, read-back, rehash and cleanup against
`platform.scoping_sessions`. It skips loudly without ADC, naming what was not
verified rather than reporting a pass.

**Q5 (does F2 change what `render()` prints).** I implemented **(a)** —
`render()` is untouched, so no already-approved brief is invalidated and the
kill-switch is not tripped. `approved_hash` now covers config + record-only
answers; `config_hash` still covers the config and is still what the document
prints.

The window (a) leaves open is real and I did not want to leave it open silently,
so I closed the half of it that needs no change to `render()`:
`BriefResponse` now returns `approval_hash` alongside `config_hash`, and
`ApproveRequest` accepts an optional `approval_hash` which is checked when
present. A client that sends it is told at approve time that the falsifier moved;
a client that does not is still only told at dispatch. Both behaviours are
pinned by tests, including the one that documents the gap
(`test_without_the_brief_hash_the_window_is_still_open_at_approve_time`).

This is a stopgap, not the ruling. If you rule **(b)**, the change is: print
`approval_hash` in `render()`'s final section instead of `config_hash`, make
`ApproveRequest.approval_hash` required, and drop the config-only comparison —
the values are already computed and already on the wire. If you rule **(a)**
stands, the brief's closing paragraph should be reworded, because as written it
promises something the document does not do.


### DP-REVIEW-Q1 — Does anything downstream read `curated.plays` between Tuesday full runs? Blocks the gameday-mode fix.

**Date:** 2026-09-09
**Agent:** DATA-PIPELINE

**What I was doing:** DP-REVIEW. Specifying the deferred fix for DP-R-01 —
making `run_pipeline_job.py`'s gameday mode run only the steps its own comment
says it runs (schedules + `curated.games`), instead of the full 7-step rebuild it
actually runs today.

**What I tried:** Worked out the required step set from `run_pipeline.py`. It is
{1, 5}, which `--start-at` cannot express because it selects a contiguous suffix.
`--only 1,5` is the smallest change. That part is settled.

**The question:** Skipping step 6 means a gameday run no longer refreshes
`curated.plays`, so new plays would land only on the Tuesday full run. Is that
acceptable? It depends on whether MODELING or BACKEND-API reads `curated.plays`
between Tuesdays. That is not my call and I cannot answer it from inside this
folder.

**What I need to proceed:** A ruling from PROJECT-LEAD, informed by MODELING and
BACKEND-API, on whether `curated.plays` may go up to seven days stale during the
season. If it may not, the gameday step set is {1, 5, 6} and the fix is
correspondingly slower — which changes the timeout maths and possibly the
conclusion. Spec is in `01-DATA-PIPELINE/DP-REVIEW-2026-09-09.md` §7.2. **Do not
implement §7.2 until this is answered.**

**ANSWERED — PROJECT-LEAD, 2026-09-09.** Step 6 cannot be skipped: `curated.plays`
is read by the live API (`queries/games.py` play count and per-team aggregates,
`queries/teams.py` and `routers/teams.py` EPA charts), degrading to empty rather
than erroring (`routers/games.py:117` is explicitly best-effort). Skipping it makes
game detail and team stats up to seven days stale in-season — not acceptable in
September. MODELING reads it only in on-demand backtests and has no freshness
requirement, so that half was a non-issue. Verified in source by DATA-PIPELINE.

The ruling also overturned the question's own framing: step 6 builds
`curated.plays` from `raw_nflfastr.pbp` (step 3), so any subset containing 6 must
contain 3, and step selection is unusable as an axis. **The axis is season scope** —
same steps, current season only, per-partition writes instead of drop-and-rebuild,
which subsumes DP-R-12. §7.2 rewritten on that axis. Still deferred, not
implemented.

---

### DP-REVIEW-Q2 — When may the DP-R-02 one-clause fix land? It is safe in isolation and touches a file that runs Friday unattended.

**Date:** 2026-09-09
**Agent:** DATA-PIPELINE

**What I was doing:** DP-REVIEW, finding 1. `ingest_pbp.py`'s new `EMPTY` branch
is not season-gated, so a *completed* season that fetches empty is skipped rather
than failed. Combined with `run_pipeline` dropping `raw_nflfastr.pbp` before the
loop, and `validate_and_report` only generating checks for seasons physically
present in the table, a season of history can leave production with a green run
and no alert.

**What I tried:** Traced all three links and confirmed each in source. Confirmed
the fix is one clause — `if len(df) == 0 and season >= current_season():` — and
that it leaves the 2026 path unchanged, so it cannot re-break the ingest.

**The question:** The working rules say write defects up rather than fix them,
and the kill-switch says stop if a fix could re-break the ingest. This fix cannot
re-break the ingest, but it does modify a file that runs unattended at
Fri 05:00 UTC. I read that as "not before the weekend" and have not applied it.
Confirming rather than assuming.

**What I need to proceed:** Confirmation to land it after the first live weekend,
or an instruction to land it sooner. Recommended order once cleared: DP-R-02,
DP-R-03, DP-R-04, then the status enum from Q4.

**ANSWERED — PROJECT-LEAD, 2026-09-09.** Deferred, and on a stronger argument than
the one I offered. Landing the clause requires rebuilding and redeploying the
pipeline image ~44 hours before an unattended run. The clause is safe; the rebuild
is not — the 2026-09-08 rebuild is how the scoping router reached production
unnoticed and how `/health` lost its commit SHA in the same push. The unit of
deployment risk is the image, not the edit. Ordering accepted as written.

---

### DP-REVIEW-Q3 — Image provenance and the Phase 6 migration are both blocked on credentials I cannot reach.

**Date:** 2026-09-09
**Agent:** DATA-PIPELINE

**What I was doing:** Step 1 of the review — confirming the deployed job was
built from `42336b6` before reviewing it — and the "Also do" item, running
`scripts/migrate_phase6_scoping.py` and comparing the deployed schema against
`NEW_TABLES` field by field.

**What I tried:** `gcloud`, `bq` and `google.cloud.bigquery` are all absent from
the shell available to me on Matt's machine — it is an isolated Linux VM with
only the connected folders mounted, and ADC lives in `AppData\Roaming\gcloud` on
the Windows host, which the bridge will not mount and should not. Network from
the VM works; authentication and the CLI are what is missing. Commands were
issued to Matt to run on the host and paste back.

**The question:** Not a question so much as a recorded gap. `.gcloudignore`
excludes `.git/`, so no image this project builds carries commit metadata, and
provenance cannot be established from the artifact alone — the decisive test is
hashing the six files inside the image against the commit blobs.

**What I need to proceed:** The two command batches issued 2026-09-09. **If the
deployed image is not `42336b6`, every verdict in DP-REVIEW §1 describes code
that is not running and the review must be redone against what is.**

---

### DP-REVIEW-N1 — Recorded, already ruled: gameday entrypoint and timeout (DP-R-01).

**Date:** 2026-09-09
**Agent:** DATA-PIPELINE

Recorded here for the trail; no answer needed. `run_pipeline_job.py`'s gameday
branch is byte-identical in behaviour to full (`--start-at` defaults to 1), and
runs the full 7-step rebuild under a 1800s timeout against full's 7200s. First
unattended run Fri 05:00 UTC. Escalated in-session and ruled by PROJECT-LEAD the
same day: DEVOPS raises the timeout (jobs.tf ~144, 1800s → 7200s) as P0, then a
watched forced run of `nfl-pipeline-gameday`; the real fix is deferred to
DP-REVIEW §7.2. DATA-PIPELINE does not touch `jobs.tf`, `run_pipeline_job.py` or
the schedulers.

Also recorded: `curated.games` is dropped and rebuilt on every run and the games
API reads it, so each gameday run opens a window with no games on the live site —
three times a week, one straight after TNF (DP-R-12). Availability, not
correctness, and the reason §7.2 is urgent rather than tidy.


## Resolved

*(none)*
