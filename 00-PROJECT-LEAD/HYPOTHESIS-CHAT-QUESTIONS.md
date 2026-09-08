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

## Resolved

*(none)*
