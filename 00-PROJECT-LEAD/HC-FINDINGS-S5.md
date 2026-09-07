# HC-S5 Findings — rulings, specs and ownership

**Owner:** PROJECT-LEAD · **Date:** 2026-08-31
**Raised by:** FRONTEND on returning HC-S5. All six verified against source here, not accepted on report.
**Status: specs only. Nothing dispatched.** Per `instructions.md`, no second agent is engaged in the same session as HC-S6 without Matt's say-so.

Findings 1, 4 and 5 are defects in code PROJECT-LEAD wrote during S0–S4. FRONTEND caught them from the outside, which is exactly what a clean-context reader is for.

---

## F-1 — `QuestionOut.prefill` / `prefill_evidence` / `confirmed` are always null

**Verified.** `PendingQuestion` (`app/scoping/session.py` L46-47) declares them with `None` defaults and nothing ever writes them; `_state()` builds `QuestionOut` from `PendingQuestion.__dict__`, so the fields ship empty on every response. FRONTEND worked around it by joining `/extract` pre-fills to questions by `slot_id` client-side.

FRONTEND's framing is right: a declared channel that is always empty invites the next reader to trust it.

**Ruling: REMOVE the three fields from `QuestionOut`, do not populate them.** Owner: BACKEND-API.

Populating would mean persisting pre-fills on the session, which means a new `prefills JSON` column and a DATA-PIPELINE migration — a schema change bought for speculative value. Removing is three lines and kills the trap outright. The client-side join already works and is honest about where pre-fills live: in the `/extract` response.

This is the "make wrong behaviour impossible" rule applied to ourselves. An empty declared field is the wrong thing; deleting it is the fix.

**Acceptance:** `QuestionOut` no longer declares the three fields; `test_prefills_start_unconfirmed` in `tests/test_scoping_api.py` is updated or removed deliberately, not left asserting a field that no longer exists; frontend build stays clean.

---

## F-2 — Pre-fills do not survive a page reload

Consequence of F-1's ruling, and accepted. Pre-fills exist only in the `/extract` response; reloading mid-session loses them and the questions are simply asked normally — which is the documented fallback path, not a broken state.

**Ruling: accept for now. Revisit only if it actually bites.** The tree is 17 slots; if Matt finds himself re-running `/extract` after reloads often enough to be annoying, that is the signal to add the column. Building it before that signal is speculative.

---

## F-3 — `/openapi.json` missing from the Vite dev proxy

**Verified.** `04-FRONTEND/vite.config.ts` proxies `/api` and `/health` only. `schema:GameUniverseFilter` resolves at runtime and the OpenAPI document is the only place those enum values exist, so local dev cannot resolve filter options. Production is same-origin and unaffected.

**Ruling: one-line fix. Owner: FRONTEND.** Not folded into S6 — S6 belongs to TESTING-QA and this is not a test.

```ts
'/openapi.json': { target: 'http://localhost:8080', changeOrigin: true },
```

**Acceptance:** a filter question renders its options in `npm run dev` against a local backend.

---

## F-4 — Field/value type rule is invisible to clients and fails late

**Verified.** `GameUniverseFilter`'s rule — `div_game` takes a bool, `week` takes an int — lives in a `model_validator` (`app/schemas/experiments.py` L45-56) and never reaches OpenAPI. A schema-driven client cannot know it. Worse, an invalid combination is not caught until the **last** answer, when `ExperimentCreateRequest.model_validate` finally runs in `answer_slot`.

That is a real usability defect of my design: the user answers question 4 wrongly and is told at question 17. It also sits awkwardly against D-3, which put slot-filling in the deterministic layer precisely so it could be checked as it goes.

**Ruling: add per-answer validation. Owner: BACKEND-API.**

`POST /answers` should validate the submitted value against the slot's declared `type` — and, for `type: "filter"`, against `GameUniverseFilter` itself — returning `400 invalid_answer` at the point of the mistake. The final whole-config validation stays as the backstop; this is an addition, not a replacement.

**Acceptance:** submitting `{field: "div_game", operator: "eq", value: 5}` returns 400 at that answer, not at the last one; a test asserts the failing slot id is named in the error; the existing whole-config check still runs.

---

## F-5 — `feature_catalog` gaps carry no nearest-expressible or suggested definition

**Verified, and it is my miss.** `app/scoping/gaps.py` L123-124 and L143-144 hardcode `None` for both fields on `feature_catalog` gaps. Only `filter_schema` gaps get them populated.

**Not deliberate.** The build plan's own worked example says the OL-weight gap should read: *no weight feature exists; nearest expressible is your existing OL composite; suggested definition — snap-weighted mean listed weight of the five OL by depth chart, sourced from `seasonal_rosters`, which is staged but not loaded.* S3 shipped the classification and dropped the content. The UI correctly renders "none recorded" rather than inventing text, so the shortfall is visible rather than papered over — but the gap record is the deliverable of the whole stop-at-the-wall design, and half of it is missing.

**Ruling: populate them. Owner: BACKEND-API.**

Keep it deterministic, in the same spirit as `concepts.json`: extend that file (or a sibling) with, per known-missing concept, a nearest-expressible pointer and a proposed definition including its data source and load status. What cannot be resolved from data stays `None` — an honest blank beats a generated guess, which is why this must not become a model call.

**Acceptance:** the OL-weight fixture in `tests/test_scoping_extract.py` asserts a non-null `suggested_definition` naming `seasonal_rosters`; a concept with no curated entry still yields `None` for both, asserted.

---

## F-6 — No commit SHA; the repo cannot produce a reviewable commit

**Verified earlier and recorded in `PHASE6_STATUS.md`.** ~300 files show as modified; every one is a permission-bit flip (`100644`→`100755`) with a zero-line content diff, from the machine migration in `fc297ef`. `core.filemode` is `true`.

**Not PROJECT-LEAD's call, and correctly escalated.** `git config core.filemode false` is local-only and changes no file content, but it changes what every other agent session sees in this repo, so Matt decides. Until then no stage in this phase can produce a reviewable commit, and "no commit SHA" is an accurate return rather than a missed deliverable.

**Awaiting Matt.**
