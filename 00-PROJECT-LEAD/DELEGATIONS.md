# DELEGATIONS — Hypothesis Chat Build

Active tasks only. Completed rows move to `DELEGATION-LOG.md` (append-only, never edited).
Plan: `HYPOTHESIS-CHAT-BUILD-PLAN.md`. Decision: `../docs/DECISIONS.md` ADR-012.

| Task | Owner | Status | Outcome |
|------|-------|--------|---------|
| HC-S0 — scoping tree + conformance test | PROJECT-LEAD (built directly on Matt's instruction) | complete | 17 slots, 16 tests passing. See `PHASE6_STATUS.md`. |
| HC-S1 — platform.scoping_sessions, platform.capability_gaps | PROJECT-LEAD (built directly on Matt's instruction) | complete | Tables live and verified. Migration script unrun — see `PHASE6_STATUS.md`. |
| HC-S2 — deterministic core | PROJECT-LEAD (built directly) | complete | 7 endpoints, 51 tests passing. Guard proven to bite. |
| HC-S3 — extractor + gap detection | PROJECT-LEAD (built directly) | complete | 20 tests. Acceptance criterion corrected — see PHASE6_STATUS.md. |
| HC-S4 — governor | PROJECT-LEAD (built directly) | complete | 20 tests. 6/6 on the flawed fixtures; zero on a sound one. |
| HC-S5 — HypothesisChatPage + components | FRONTEND | complete | 7 files, build clean, 25/25 browser checks. Storage was faked — see PHASE6_STATUS S5 caveat. 6 findings in HC-FINDINGS-S5.md. |
| HC-S6 — test suite | TESTING-QA | dispatched | brief appended 2026-08-31. Must close the live-BigQuery gap S5 could not. |
| HC-S7 — deploy + verify ANTHROPIC_API_KEY scope | DEVOPS | blocked | needs HC-S6 |
| F-1, F-4, F-5 — backend defects found by FRONTEND | BACKEND-API | spec'd, NOT dispatched | `HC-FINDINGS-S5.md`. Awaiting Matt — one agent per session. |
| F-3 — Vite dev proxy one-liner | FRONTEND | spec'd, NOT dispatched | `HC-FINDINGS-S5.md` |
| F-6 — `git config core.filemode false` | Matt | waiting-on-Matt | No stage can produce a reviewable commit until decided |

Status values: in-progress, waiting-on-me, complete, blocked

## Carried debt, not part of this build

| Item | Note |
|------|------|
| `BUG-STATUS.md` never written | B1-B, B2-A and B2-E of the May 2026 bug sprint named it as a deliverable. The code fixes are confirmed present in source (`ExperimentCreateRequest.features`, `has_deprecated_features`); only the documentation is missing. The sprint block in `03-BACKEND-API/instructions.md` was closed 2026-08-31 so it cannot be picked up as current work. Reopen deliberately or drop it deliberately — do not leave it ambiguous. |
| FRONTEND bug sprint (May 2026) unverified | The `## CURRENT TASK` block in `04-FRONTEND/instructions.md` was paused 2026-08-31, not closed. Its BACKEND counterparts are confirmed shipped, but the frontend items — especially the F2-E visual checks — could not be confirmed from source. Unverified, not done. Resume deliberately or drop deliberately. |
| Phase 5 visual verification | `PHASE5_STATUS.md` §Outstanding Work lists three unticked visual checks (per-fold chart, feature importance panel, dashboard count). Backend data confirmed present; only the visual confirmation is outstanding. |
