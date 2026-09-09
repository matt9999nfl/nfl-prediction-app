# HC-S6-FIX — accepted, and the five open questions ruled

**Owner:** PROJECT-LEAD · **Date:** 2026-09-09
**Return:** `HC-S6-FIX-HANDOFF.md` · **Prior rulings:** `HC-S6-RULINGS.md` · **Escalations:** `HYPOTHESIS-CHAT-QUESTIONS.md`

---

## HC-S6-FIX is ACCEPTED

Thirteen of thirteen acceptance criteria met. Criterion 11 is met for three of four
integration failures; the fourth is unmeetable as written for a reason that was a
ruling I owed, not a shortfall in the work — see Q4.

**Verified here against source, not accepted on report:** `update_answers` sets
`approved_hash = NULL` in the same statement; `set_approved_hash` conditions its
`WHERE` on `config_hash`; `canonical_json` folds whole-number floats and excludes
`bool`; `governor.fold_test_seasons` uses the runner's stride algorithm;
`tests/test_scoping_folds.py` lifts `build_folds_from_config` out of the runner's
own file by AST; `require_api_key` is present on all nine scoping endpoints;
`approve()` has no status guard, confirming F7 independently.

### Two things worth recording as precedent

**The fake now reads production.** `tests/test_scoping_api.py::Store` no longer
makes its own claim about clearing `approved_hash` — `_real_update_clears_approved_hash()`
parses the `SET` clause out of `app/queries/scoping.py` by AST and the stand-in
behaves however that statement behaves. My F1 ruling said "correct the fake."
BACKEND-API made it *structurally incapable of being kinder than production*,
which is core principle 1 applied to the exact defect that motivated the sprint.
**This is the pattern for every stand-in in this repo from here on.**

**The return undercut its own revert table, unprompted.** Reverting F1 alone does
not turn `test_changing_an_answer_after_approval_blocks_dispatch` red, because
that test changes `min_sample` — a config slot — so F2 catches it regardless. The
test's *choice of which answer to change* was itself kind. BACKEND-API found
that, wrote it down, and built `test_changing_only_the_falsifier_invalidates_a_surviving_approval`
to bite on F1 alone. An agent optimising for a clean return leaves that unsaid.
The rest of the return is more credible because it did not.

---

## Q4 — the F9 contradiction · **Option 1. Two tests, not one.**

TESTING-QA rewrites. The scope in the escalation is understated: **two** tests
encode the claim the F9 ruling deletes —
`integration/test_hypothesis_chat.py::test_json_columns_round_trip_nested_arrays_and_explicit_nulls`
and `scoping_hc/test_hc_approval_attacks.py::test_attack_500_vs_500_point_0_to_collide_two_configs`.

**Not option 2.** An `xfail` marker pinning an overruled design claim is a trap
for the next reader — the same shape as HC-S5's F-1 always-null fields, and the
same shape as the lying fake. A test that can never go green will eventually be
"fixed" by someone who reads it as a known bug rather than a deleted decision.

**Not option 3.** BACKEND-API's reasoning is correct and matches mine: the
int/float distinction was never enforceable past the schema boundary, Pydantic
already coerces `500.0` to `500`, and a hash that cannot survive its own storage
layer fails closed into a wedged session. Preserving it means a schema change to
`platform.scoping_sessions` to buy back something that was never real.

**Rewrite both to assert the inverse** — that the distinction is deliberately not
preserved, and that the collision is harmless because Pydantic validates `500`
and `500.0` into the same `ExperimentConfig`, so two configs that hash alike also
run alike. That last clause is the reason the collision is not a security hole
and it must appear in the test, not only here.

---

## Q5 — does F2 change what `render()` prints · **(b), conditional on a count of zero.**

**Precondition:** `SELECT COUNT(*) FROM platform.scoping_sessions WHERE approved_hash IS NOT NULL`
must return 0. If it does not, this ruling is void and returns to me.

BACKEND-API argued for (b) and was right. (a) leaves a document whose closing
paragraph promises that if any answer changes the printed hash changes — which
is false for the three record-only slots. **A document that misdescribes its own
guarantee is the lying fake one layer up**, and ADR-012 commitment 3 is precisely
that the approved artefact and the executed artefact cannot differ.

The stopgap shipped in HC-S6-FIX (`BriefResponse.approval_hash`, optional
`ApproveRequest.approval_hash`) closed the half of the window that needed no
change to `render()`, and left (b) cheap: the values are computed and already on
the wire.

**Rename it. `approval_hash` throughout the schemas.**

I ruled the other way first — keep `config_hash` as the wire name to avoid a
frontend change — and I was wrong on both halves. It does not force a change
*before* HC-S7; `src/api/scoping.ts` is edited *as part of* HC-S7, which has not
shipped. And it does not buy nothing: a field named `config_hash` that carries a
hash covering config **and** record-only answers is a name that lies about its
contents. That is this sprint's archetype — the router that reported an approval
cleared while storage kept it, the fake that behaved better than production, the
brief whose closing paragraph promised a guarantee it did not provide. Shipping a
fourth instance of it while ruling on the first three would be indefensible.

So: `render()` prints the approval hash, `ApproveRequest.approval_hash` is
required, the config-only comparison is dropped, and the wire field is named for
what it holds. `config_hash` survives as the internal staleness check only.

---

## Q6 — the `RecordingStore` signature · **TESTING-QA, bundled.**

One line, in their file, caused by a signature change I ruled for. BACKEND-API
was right not to touch it and right to reject the `try/except TypeError`
workaround on principle — production bending to accommodate a fake is the
inversion of this sprint's entire lesson.

It does not justify a session of its own. It goes in the same TESTING-QA brief as
Q4.

---

## Q7 / F7 — re-approval re-opens the dispatch guard · **Fix now. Guard in the SQL, not only the router.**

Confirmed in source: `approve()` calls `_load_or_404` and never reads `status`,
and `set_approved_hash`'s `WHERE` conditions on `config_hash` only — which a
dispatch does not move. So dispatch → approve → dispatch lands, resets status to
`approved`, mints a second experiment, fires a second Cloud Run job, and
overwrites `session.experiment_id` so the first experiment is orphaned from the
session that produced it.

**Both layers.** A check in `approve()` returning a clean 409 `already_dispatched`,
mirroring the one in `answer_slot`, *and* `AND status != 'dispatched'` in
`set_approved_hash`'s `WHERE` clause.

The router check alone is not enough, and F1 is the standing proof: a
router-level check over permissive SQL is exactly how a guarantee stays broken
while the API reports it holding. The SQL condition makes the second run
impossible rather than prohibited, and it is the pattern F10 just established in
the same function.

There is no legitimate approval after dispatch — `answer_slot` already refuses to
change answers once dispatched — so the condition cannot block real work.

Both TESTING-QA assertions flip. That is correct: a strict-xfail going XPASS is
the mechanism reporting a closed finding, which is what it is for.

**Orphaning matters more than double-spend.** This project has already been
burned once by an invalidated run sitting in the log looking valid (PR-001, and
the SOP item that came out of it). A second experiment whose session no longer
points at it is that failure mode with a new cause.

---

## Q7 / F4 — `GAMES_PER_SEASON = 272` · **None of the three options. Use the right constant.**

2015–2020 were 16-game seasons (256); 2021 onward are 17-game (272). That is
static history, not a BigQuery read. A per-season lookup is exact everywhere
except the cancelled 2022 game, at zero cost to `/review`'s fragility.

The real-count option is a coherent design and I am declining it on price: it
puts a BigQuery read behind a number that is currently pure arithmetic, and under
the F6 ruling just implemented, a read that fails must then raise a concern. That
is a materially more fragile `/review` bought for 1.8% and one game.

Keep `GAMES_PER_SEASON` as the fallback for seasons outside the table, so a
future season needs no code change to be counted, only to be counted exactly.

BACKEND-API's framing was right and is why this is being fixed at all rather than
closed: `evaluated_games` is presented to the user as a count, not an estimate,
and it errs in the same permissive direction F3 did.

---

## Deploy timing — **not before TNF. Friday, after Thursday's run is confirmed clean.**

F1, the open reads (Q3) and F7 are live on `nfl-backend-api-00024-kw7` and all
fixed or about to be fixed in the repo. Deploying strictly improves production
and breaks nothing, because the frontend does not exist to notice the auth
change. So the argument is entirely about timing.

Against deploying now: exploiting any of the three requires `OWNER_API_KEY`, and
the frontend is undeployed, so practical exposure until HC-S7 is close to nil.
Against that, a full API image rebuild is precisely how the scoping router
reached production unnoticed on 2026-09-08 and how `/health` lost its commit SHA
in the same push. **Thursday 2026-09-10 is the first unattended scheduled run of
the season.** Trading near-zero exposure for an unforced image rebuild the night
before is the wrong side of that trade.

**Consequence: DO-HARDEN is not parallel-safe.** It carries the `/health` commit
SHA fix, and the Friday deploy should include it so we regain *which code is
running* in the same push — the question that took a week to answer during
INC-002. DO-HARDEN moves onto the deploy path and must land before Friday.

---

## Sequencing — and why it is not the parallel board it looks like

| # | Task | Owner | Why here |
|---|---|---|---|
| 1 | **DP-REVIEW** | DATA-PIPELINE | **Before TNF.** Its value expires Thursday |
| 2 | **HC-S6-FIX-2** — F7, F4, Q5(b) | BACKEND-API | All three flip TESTING-QA assertions |
| 3 | **HC-S6-CLEANUP** | TESTING-QA | Must follow 2, or they rewrite against code about to move |
| 4 | **DO-HARDEN** | DEVOPS | On the deploy path |
| 5 | Deploy | — | After TNF is confirmed clean |
| 6 | **HC-S7** | FRONTEND | — |

**DP-REVIEW was listed as "blocks nothing." That was wrong.** Those five files
are the ingest path, edited by an agent working outside its domain under time
pressure mid-incident, and Thursday is the first unattended run of exactly that
code. Reviewing them after TNF means the review happens after the event it was
insurance against.

The counter is real and worth recording: alerting now works and is proven with a
real email, so a *failed* job gets reported. It does not catch a job that
succeeds and writes something subtly wrong — and `validate_pbp`'s 40,000-row gate
is the standing proof that this codebase produces exactly that failure mode. A
review catches the second kind; the alert does not.

**2 and 3 are ordered, not parallel.** Running TESTING-QA first means they
rewrite assertions against code that is about to change again, and it costs two
of their sessions instead of one.

---

## Held, deliberately

The four HC-S5 findings (`HC-FINDINGS-S5.md`) stay undispatched. F-4's ruling
reads differently now the F2 hash work has settled, and I want to look at that
properly rather than in passing.

## Process note for the next brief

HC-S6-FIX cited `../00-PROJECT-LEAD/HC-S6-FINDINGS.md`. That file is in
`06-TESTING-QA/`. BACKEND-API found it anyway; the next brief should not repeat
the error.
