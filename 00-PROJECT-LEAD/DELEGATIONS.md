# DELEGATIONS — active work

**Updated:** 2026-09-09 (second session) · Plan: `HYPOTHESIS-CHAT-BUILD-PLAN.md` · Decision: `../docs/DECISIONS.md` ADR-012
**Full context:** `SESSION-HANDOFF-2026-09-09.md` · **Latest rulings:** `HC-S6-FIX-RULINGS.md`

HC-S6-FIX returned and is **accepted, 13/13** (`HC-S6-FIX-HANDOFF.md`). Its five
escalations are ruled in `HC-S6-FIX-RULINGS.md`. Nothing is deployed — the
scoping backend is still live at `nfl-backend-api-00024-kw7`.

## The order matters. This is not the parallel board it looks like.

| # | Task | Owner | Status | Why here |
|---|---|---|---|---|
| 1 | ~~**DP-REVIEW**~~ | DATA-PIPELINE | ✅ **COMPLETE 2026-09-09** | `01-DATA-PIPELINE/DP-REVIEW-2026-09-09.md`, 846 lines, 13 defects. See below |
| 2 | **HC-S6-FIX-2** — F7 guard, F4 per-season constant, Q5(b) rename | BACKEND-API | dispatched | All three flip TESTING-QA assertions |
| 3 | **HC-S6-CLEANUP** — 11 assertions to dispose of + the deploy-red trap | TESTING-QA | dispatched, **blocked on 2** | Running it first costs two of their sessions |
| 4 | **DO-HARDEN** — pre-container-failure alert, P4 freshness check, `/health` commit, review PL's terraform edit | DEVOPS | dispatched | **On the deploy path**, not parallel-safe — see below |
| 5 | **Deploy the API** | Matt / DEVOPS | waiting | After TNF is confirmed clean |
| 6 | **HC-S7** — deploy the chat frontend | FRONTEND | blocked on 2, 3, 5 | Picks up the `approval_hash` rename |

## DP-REVIEW outcome — 2026-09-09

**Six files reviewed** (the brief originally said five; DATA-PIPELINE caught the
omission against the commit). Five correct or correct-but-narrow, one **wrong**
(`ingest_pbp.py`), one **inert** (`build_curated_games.py` — its `EMPTY`
tolerance is unreachable code). 13 defects, DP-R-01 to DP-R-13.

**Season readiness is now established by measurement, not inference:**

| Fact | Evidence |
|---|---|
| Deployed image contains `42336b6` | `:latest` = digest `50be6f228183`, built 2026-09-08T09:23:28, 11h39m after the commit |
| Both pipeline jobs run the same image | `gcloud run jobs describe`, both `gcr.io/.../nfl-data-pipeline:latest` |
| Gameday fits its budget with 2.2x headroom | watched run `nfl-pipeline-gameday-lpvv4`, 13m08s against 1800s |
| Gameday ≡ full, by measurement | 13m08s vs `nfl-pipeline-full-rcn9v` 13m30s |
| No history lost | 2015-2025 present in `raw_nflfastr.pbp`; `curated.games` 2015-2026, 2022 = 271 (cancelled game) |

**Post-weekend queue, in order:** DP-R-13 (pin the image digest — DEVOPS),
DP-R-02, DP-R-03, DP-R-04, then the status enum from Q4, then §7.2.

**§7.2 was re-scoped by PROJECT-LEAD ruling.** The step-selection axis (`--only 1,5`)
is unusable: step 6 builds `curated.plays` from step 3's output, and the live API
reads `curated.plays` for game detail and team EPA. The axis is **season scope** —
gameday should run the same steps restricted to the current season, written
per-partition instead of dropped and rebuilt. That subsumes DP-R-12.

### ⚠️ The one check nothing can do for us — Friday 2026-09-11, after 17:00 NZ

```
bq query --use_legacy_sql=false "SELECT season, COUNT(*) AS plays FROM `nfl-model-471509.raw_nflfastr.pbp` GROUP BY season ORDER BY season"
```

Expect a 2026 row, ~2,700 plays. **No 2026 row = the season opener was silently
skipped and no alert fired.** Recovery: `gcloud run jobs execute nfl-pipeline-full
--region us-central1 --wait`, then re-run the query.

DP-R-02's loop — drop, empty fetch, `EMPTY`, skip, no season, no check generated,
`ALL CHECKS PASSED` — **was observed running in production on 2026-09-09** and is
harmless today only because 2026 genuinely has no plays yet. After TNF it stops
being harmless. This is the gap the 40,000-row floor fix opened.

### Why DP-REVIEW was first

It was previously listed as "parallel-safe, blocks nothing." **That was wrong.**
Those five files are the ingest path, edited by an agent working outside its
domain under time pressure mid-incident, and Thursday 2026-09-10 is the first
unattended scheduled run of exactly that code. Reviewing them afterwards means
the review happens after the event it was insurance against.

The counter, recorded honestly: alerting now works and is proven with a real
email, so a *failed* job gets reported. It does not catch a job that succeeds and
writes something subtly wrong — and `validate_pbp`'s 40,000-row gate is the
standing proof that this codebase produces exactly that failure mode.

### Why 2 must precede 3

HC-S6-FIX-2 changes `approve()`, `set_approved_hash`'s `WHERE` clause, and
renames `ApproveRequest.config_hash` to `approval_hash`. TESTING-QA rewriting
assertions before that lands means rewriting them twice.

### Why DO-HARDEN is on the deploy path

It carries the `/health` commit SHA fix. The Friday deploy should include it so
we regain *which code is actually running* in the same push — the question that
took a week to answer during INC-002.

## Deploy checklist — Friday, after TNF

- [ ] TNF Thursday run confirmed clean
- [ ] HC-S6-FIX-2 landed and returned
- [ ] HC-S6-CLEANUP landed and returned
- [ ] DO-HARDEN's `/health` commit SHA fix included in the build
- [ ] **Expect `scoping_hc/test_hc_deployed_revision.py` to go red.** Three tests pin what production currently is and all three flip at this deploy: the anonymous-read assertions (Q3 closes them) and `test_the_deployed_revision_still_cannot_say_which_code_is_running` (DO-HARDEN). Red there means the fixes landed. TESTING-QA is returning the exact list.
- [ ] Confirm `/health` reports a real commit SHA after the deploy

## Waiting on Matt

| Item | Note |
|---|---|
| `SELECT COUNT(*) ... WHERE approved_hash IS NOT NULL` | **Gates Q5(b) in HC-S6-FIX-2.** Zero → proceed. Non-zero → the ruling is void and returns to PROJECT-LEAD |
| Thursday 2026-09-10 TNF | First unattended scheduled run. Alerting will now report a failure |
| `git config core.filemode false` | ~300 permission-bit diffs make `git diff --name-only` useless as a review check repo-wide |

## Spec'd, deliberately not dispatched

`HC-FINDINGS-S5.md` — F-1 (remove the always-null prefill fields), F-3 (Vite dev
proxy one-liner, FRONTEND), F-4 (per-answer validation), F-5 (feature-catalog
gaps ship with null definitions).

Still held. F-4's ruling reads differently now the F2 hash work has settled, and
PROJECT-LEAD wants to look at that properly rather than in passing.

## Carried debt

| Item | Note |
|---|---|
| FRONTEND May-2026 bug sprint | Paused, **unverified not done**. Backend counterparts confirmed shipped; the F2-E visual checks were never confirmed. Resume deliberately or drop deliberately |
| Phase 5 visual verification | Three unticked checks in `PHASE5_STATUS.md` |
| `BUG-STATUS.md` never written | Named as a deliverable by the May bug sprint. Code fixes confirmed in source; documentation missing |
| Role-boundary deviations | PROJECT-LEAD edited 5 files in `01-DATA-PIPELINE` and 1 in `05-DEVOPS` during INC-002. DP-REVIEW and DO-HARDEN carry the reviews |
| `ROADMAP.md` is stale | Last updated 2026-08-31; still says "Phase 5 complete" and knows nothing of INC-002 or the accidental deploy. It is the first document a cold session reads |
| `.git` lock clutter | ~10 dead `.lock.*` files PROJECT-LEAD's sandbox could not delete. Harmless; Matt can remove from Explorer |
