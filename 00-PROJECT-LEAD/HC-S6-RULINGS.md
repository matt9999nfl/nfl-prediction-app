# HC-S6 — findings accepted, escalations ruled

**Owner:** PROJECT-LEAD · **Date:** 2026-09-08
**Return:** 56 tests added (48 pass, 8 strict-xfail, 1 module skipped for credentials). Existing 91 backend tests still pass; nothing under `03-BACKEND-API` modified.

**HC-S6 is accepted. Requirement A is now MET** — the live-storage module ran against real BigQuery on 2026-09-08 after ADC login: 3 passed, 4 failed, 1 skipped (dispatch, per Q2), live tables clean afterwards.

The four failures are the deliverable. Two confirm F1/F2 against real storage; **two are new findings that nobody predicted from reading the code.**

All three primary findings verified here against source, not accepted on report. **All three are defects PROJECT-LEAD introduced in S2–S4.** Each was caught by replacing a model of the world the author wrote with something external — which is the entire argument for core principle 6, demonstrated rather than asserted.

---

## F1/F2 — Live route to dispatching an unapproved brief · CRITICAL · CONFIRMED

`app/queries/scoping.py::update_answers` sets `slot_answers`, `config`, `config_hash` and `status`. **It never sets `approved_hash`.** The router mutates `approved_hash` to `None` on the response dict only, so the API reports the approval as cleared while the row still holds it.

**Why every existing test missed it:** the in-memory `Store` in `tests/test_scoping_api.py` clears `approved_hash` in its `update_answers`. The fake behaves correctly; the real SQL does not. `test_changing_an_answer_after_approval_blocks_dispatch` passes for the wrong reason.

That is the exact archetype the S6 brief described, sitting inside the approval path — the one mechanism the whole feature was built to protect.

**Second, independent hole in the same finding.** The hash covers the `ExperimentConfig`. The brief also renders three record-only slots (`mechanism`, `falsifier`, `prior_attempts`). Change the falsifier after approving and the hash does not move, so dispatch proceeds against a document nobody signed off. ADR-012 commitment 3 says the approved artefact and the executed artefact cannot differ; today they can.

**Ruling — both must be fixed. Owner: BACKEND-API.**
1. `update_answers` must set `approved_hash = NULL`. The router must stop implying it in the response body.
2. The approval hash must cover **everything the brief renders** — config *and* record-only answers — not the config alone.
3. The in-memory `Store` in `test_scoping_api.py` must be corrected to match the real SQL, or the test that guards this will keep passing for the wrong reason. **A fake that is kinder than production is worse than no fake.**

Mitigating, and the reason this is not an incident: `dispatch` recomputes the hash from current answers rather than trusting the stored column, so the config half is still caught. It is the record-only half and the stale `approved_hash` that get through.

---

## F3/F5 — Governor clears under-powered experiments · HIGH · CONFIRMED

`app/scoping/governor.py::evaluated_games` computes `folds * test_seasons * 272`, where `folds = span - train_seasons`.

The runner (`02-MODELING/backtests/walk_forward.py::build_folds_from_config`) does `test += test_seasons` and returns `(train_list, test_season)` — **`test_seasons` is the stride between folds, and every fold evaluates exactly one season.**

So the governor multiplies by `test_seasons` when it should not, *and* miscounts folds. The two agree only at `test_seasons=1` — the single value `test_evaluated_games_counts_folds_not_seasons` asserts. I tested the implementation's own formula against itself at the one point it happens to be right.

Consequence: at `test_seasons=2` the governor reports ~3.5x the real sample and returns `{"concerns": [], "verdict": "proceed"}` for a design evaluating ~1,072 games against a minimum of 1,500 the user set themselves. **The sample-size check — the governor's headline job — silently passes the experiments it exists to stop.**

**Ruling: fix, and remove the duplication that caused it. Owner: BACKEND-API.**
The governor must not reimplement the runner's fold logic. Derive folds using the same algorithm, and add a test asserting the governor's fold count equals `len(build_folds_from_config(...))` across a matrix of `train_seasons` × `test_seasons`. Two definitions of "a fold" in one codebase is the root cause; one of them has to go.

---

## F6/F8 — Safety layers fail open and quiet · HIGH · CONFIRMED

`review_session` wraps `slice_fraction` and `list_prior_configs` in `try/except`, logs a warning, and continues with `fraction=None` and `priors=[]`. A BigQuery outage therefore returns a normal-looking **200 with an empty concern list** — having checked neither sample size nor prior runs — and degrades toward a *larger* apparent sample, so it fails in the permissive direction.

Same shape in `extract`: a `capability_gaps` insert that raises is `continue`d and dropped from the response, so "the write failed" is indistinguishable from "there are no gaps".

**Ruling: fail loud. Owner: BACKEND-API.**
A check that could not run is not a check that passed. When an input cannot be loaded, `review` must emit a concern of its own naming what it could not verify, and the verdict must not be `proceed`. A gap that failed to persist must be reported as such. Silence must never be the same shape as safety.

---

## F9 — BigQuery JSON normalises `2.0` to `2`, and the hash design depends on it not doing that · NEW · HIGH

Found only by round-tripping through real storage.

`hashing.py` states, deliberately: *"ints and floats keep their own repr: 1 and 1.0 are NOT the same config."* BigQuery's JSON type does not honour that — `2.0` is stored and returned as `2`.

`dispatch` recomputes the hash from `slot_answers` **read back out of BigQuery**. So for any config containing a float with no fractional part, the recomputed hash cannot match the approved one, and a legitimately approved experiment is refused forever with `approval_mismatch`.

It fails **closed**, so it is not a security hole — it is a wedge. But it invalidates a design decision I wrote into the hashing module: the int/float distinction is unenforceable through the storage layer, and was never actually real.

**Ruling: normalise, and delete the claim. Owner: BACKEND-API.** `canonical_json` must be idempotent across a storage round-trip — a float with zero fractional part canonicalises to its integer form. Pydantic already coerces `500.0` to `500` for an `int` field, so nothing meaningful is lost. Add a test that hashes a config, round-trips it through BigQuery, rehashes, and asserts equality; that is the property that actually matters and no unit test could have caught it.

---

## F10 — Concurrent answer and approve wedges a session · NEW · MEDIUM

Two threads, one writing an answer and one approving, leave `approved_hash` attached to answers it was not computed from. `dispatch` compares the two and refuses, so it fails closed — but the session is stuck and **no message explains why**. Both endpoints read, decide, then write with no condition on the `UPDATE` and no transaction.

Single-user, so the window is small. Not small enough to ignore: the UI can fire an answer and an approve in quick succession.

**Ruling: make the write conditional. Owner: BACKEND-API.** `set_approved_hash` should include the config hash it believes it is approving in its `WHERE` clause, so an approval that lost a race writes zero rows and returns a clear 409 instead of silently landing. Same treatment for `update_answers` where practical.

---

## Escalations

### Q1 — Live-storage credentials · **Option 1.**

Matt has `gcloud` installed and authenticated on the machine with the repo — established during INC-002 today. He runs:

```
gcloud auth application-default login
cd C:\Users\OEM\OneDrive\Desktop\nfl-prediction-app\06-TESTING-QA
pytest integration/test_hypothesis_chat.py -m integration -v
```

**Requirement A stays formally UNMET until that runs**, and HC-S7 does not deploy the frontend until it does. Option 3 is explicitly rejected: shipping a UI over a storage layer that has never been exercised is how F1 survived five stages.

TESTING-QA's refusal to fake storage for a green run was correct and is worth stating plainly — F1 exists *because* an in-memory stand-in behaved better than production. A second one would have hidden it again.

### Q2 — Real dispatch · **Out of scope for HC-S6.**

Requirement A stops at `platform.scoping_sessions`, the approve path, and the 409 guards. Do not fire a real dispatch.

Reasons: it writes to `experiments.*` through `trigger_experiment_runner`, which the brief lists as a kill-switch; the rows carry a random uuid that the conftest's `test_%` cleanup cannot match; it burns runner compute and leaves a genuine-looking experiment in Matt's list.

**But this is itself a finding.** There is no way to exercise the most consequential path in the feature without production side effects. That is a testability defect in my design, not a limitation TESTING-QA should route around. **Spec for BACKEND-API:** a dry-run mode on dispatch that performs every validation and hash check, returns the experiment payload it *would* create, and writes nothing. Then requirement A can cover dispatch honestly.

### Q3 — Anonymous reads on scoping endpoints · **Close them before HC-S7.**

`GET /scoping/capability-gaps` returns 200 to anyone on the internet, and `GET /scoping/sessions/{id}` returns hypothesis text, every answer and the assembled config to anyone holding the uuid.

The open-reads convention exists for the public predictions surface — a deliberate choice for data meant to be shown. This is different: the gap list is a readable index of what the platform cannot do, and sessions carry Matt's unpublished research thinking. ADR-012 scoped this feature single-user and deferred auth *on that basis*, which is an argument for restricting reads, not for inheriting a convention built for a different purpose.

**Ruling:** scoping read endpoints require `require_api_key`, before HC-S7. Owner: BACKEND-API. Keep TESTING-QA's assertion, inverted, so the change is visible.

---

## Consequences

| # | Action | Owner | Blocks |
|---|---|---|---|
| 1 | F1/F2 — clear `approved_hash` in SQL; hash the whole brief; fix the lying fake | BACKEND-API | HC-S7 |
| 2 | F3/F5 — one definition of a fold; agreement test against the runner | BACKEND-API | HC-S7 |
| 3 | F6/F8 — fail loud on unavailable checks | BACKEND-API | HC-S7 |
| 4 | Q3 — API key on scoping reads | BACKEND-API | HC-S7 |
| 5 | Q2 — dry-run dispatch mode | BACKEND-API | requirement A covering dispatch |
| 6 | Q1 — ADC login, then run the integration module | Matt | HC-S7 |

**HC-S7 is blocked on 1–4 and 6.** The backend is already live in production, so items 1 and 4 are live defects today — mitigated only by the frontend not being deployed and writes being key-protected.
