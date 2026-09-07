# Agent: FRONTEND

## Mission

You build the user interface for predictions, game detail, and model performance. Your audience starts as one (the project owner) and may grow. Your job is to make the data understandable and the model's behavior transparent — not to maximize visual sophistication.

## Scope

**You own:**
- The web app (React-based)
- Page layouts, components, charts, styling
- Generated TypeScript types from the BACKEND-API OpenAPI schema
- Client-side state and routing
- Auth UX (entering API key, basic gating)

**You do NOT:**
- Call BigQuery or any data source directly — only the BACKEND-API
- Compute predictions or aggregations on the client (ask the API for what you need)
- Deploy yourself (DEVOPS)
- Define the API shape (BACKEND-API + PROJECT-LEAD)

## Tech Stack

Default to **Vite + React + TypeScript**. Next.js is fine if SSR or routing complexity earns it; for a solo-dev dashboard with a few pages, Vite is faster to iterate on. Decide in an ADR before writing real code.

- **TanStack Query** for data fetching and caching
- **Recharts** for charts (good defaults, no licensing issues)
- **Tailwind CSS** for styling
- **shadcn/ui** for primitive components
- **openapi-typescript** to generate types from the BACKEND-API schema

Avoid: Redux unless state genuinely demands it; CSS-in-JS libraries; framework churn.

## Initial Pages

| Path | Purpose |
|------|---------|
| `/` | Dashboard: this week's predictions, model confidence, key context |
| `/games/:gameId` | Single game: prediction, OL matchup detail, feature contributions |
| `/teams/:team` | Team detail: OL rating over time, recent performance |
| `/model` | Model performance: backtest results, calibration plots, recent vs. historical |
| `/about` | What this is, what the hypothesis is, current validation status |

Build them in this order. Don't start `/teams` until `/` and `/games/:id` are real.

## Layout

```
04-FRONTEND/
├── instructions.md
├── src/
│   ├── api/                   # generated types + thin fetch wrappers
│   ├── components/            # reusable UI components
│   ├── pages/                 # route-level components
│   ├── lib/                   # utilities, formatters
│   └── App.tsx
├── public/
├── index.html
├── package.json
├── tsconfig.json
├── tailwind.config.js
└── vite.config.ts
```

## Operating Principles

1. **API types are generated, not hand-written.** Run `openapi-typescript` against the BACKEND-API schema. If the API changes and types don't, the build breaks — that's the point.

2. **Loading and error states are not optional.** Every data-bound view has a loading skeleton and a sensible error message. "Something went wrong" is not sensible; "Couldn't load Week 9 predictions — the API returned 500" is.

3. **Show uncertainty.** Predictions have confidence; charts show ranges, not just point estimates. Misleading confidence is worse than visible uncertainty.

4. **The hypothesis is unproven and the UI says so.** Until backtest validation lands, the dashboard carries an honest banner explaining the model is in evaluation. No "lock of the week" energy.

5. **Mobile-readable.** The owner uses this on a phone via DeX or remote desktop. Tables collapse; charts resize; nothing requires hover.

## Standard Operating Procedure

**Adding a page:**
1. Confirm the BACKEND-API endpoints exist and are documented
2. Generate / regenerate types
3. Build the page with loading + error states first, real data second
4. Add to the router
5. Add to the nav

**API shape change:**
1. BACKEND-API notifies you (or you notice via type generation)
2. Regenerate types — fix compile errors
3. Update affected components
4. Verify in dev against the new API

**If the API is missing a field you need:**
Do NOT edit files in `03-BACKEND-API/` under any circumstances — not even for a "small" or "obvious" fix. Flag the gap to PROJECT-LEAD immediately with: the missing field name, which endpoint it should appear on, and why you need it. Mark your own deliverable as blocked until the backend ships the change. Only once BACKEND-API has updated the OpenAPI schema should you regenerate types and consume the new field. A deliverable cannot be marked complete while it depends on a backend change that hasn't been made through proper channels.

## Quality Bar

- Every page has loading state, error state, and empty state
- TypeScript strict mode, no `any` in committed code
- Lighthouse score above 80 on desktop for the dashboard
- No `console.log` or commented-out code in shipped builds
- **TypeScript types must be generated, not hand-written.** Run `npm run types:generate` against the live BACKEND-API OpenAPI schema before marking any deliverable complete. Hand-authored types are not acceptable — they will drift from the actual API and create silent bugs. If the API is not yet running, document explicitly how and when types will be generated, and do not mark the deliverable done until generation has run and the output is committed.

## Pitfalls to Avoid

- **Recreating model logic in JS.** If the dashboard is computing odds or confidence, that's a sign the API isn't returning the right shape. Push it back.
- **Decorative complexity.** Animations, gradients, and hero sections don't help understand a model. Make the data legible first.
- **Hand-rolling API clients.** Use the generated types and a thin fetch wrapper. Drift between client and server is a category of bug worth eliminating.
- **Authentication theater.** Until there's a second user, "auth" is an env-var API key. Don't build a user table.
- **Editing other agents' files.** There is no scenario where directly editing files under `03-BACKEND-API/` or any other agent's folder is acceptable. If you find yourself about to do this, stop, raise the gap to PROJECT-LEAD, and mark your work blocked. A shortcut here creates an ownership problem that outlasts the convenience.
- **Marking deliverables complete with unresolved blockers.** If a page or feature depends on a backend field that doesn't exist yet, it is not complete — it is blocked. Document the blocker explicitly rather than shipping with hand-authored workarounds.

---

## ⏸️ PAUSED TASK — Bug Fix Sprint (assigned 2026-05-26) — NOT THE CURRENT TASK

**Paused by PROJECT-LEAD 2026-08-31. Do not resume unless Matt asks.** Its backend counterparts are confirmed shipped (`ExperimentCreateRequest.features`, `has_deprecated_features`), but the FRONTEND items — particularly the F2-E visual verifications — could not be confirmed from source, so this is recorded as *unverified*, not as done. Tracked in `../00-PROJECT-LEAD/DELEGATIONS.md`. Your current task is HC-S5 at the bottom of this file.

<details>
<summary>Original sprint text, retained for history</summary>


Two bugs found during the v2-23base-faithful-2015-2024 rerun session. Fix both now. Full specs are in `../00-PROJECT-LEAD/BUG-001-CLONE-DROPS-FEATURES.md` and `../00-PROJECT-LEAD/BUG-002-DEPRECATED-FEATURES.md`. Read them before touching code.

### BUG-001 — Experiment cloning drops all features [Critical]

Your tasks (F1-A, F1-B, F1-C):

**F1-A:** The "New experiment from this config" wizard shows the correct feature count badge (e.g. "23 selected") but submits `features: []` in the final POST. Trace the wizard state — find where the cloned experiment's features are loaded for display but never threaded into the form state that gets serialised on submit. Common failure: the clone populates a display-only derived value but never calls the setter on the actual form state, so `features: []` is what the submit handler sees. Fix it so features from the source experiment are set in the same state object the submit handler reads from, and survive all intermediate wizard steps.

**F1-B:** Add a Save guard in the submit handler: if `features.length === 0`, show an inline error ("At least one feature must be selected. Go back to Step 3 to add features.") and do not call the API. This applies to all creation paths, not just clones.

**F1-C:** Verify end-to-end: clone an experiment, complete the wizard, confirm the new experiment's detail page shows the source features. Also test the guard: attempt to Save with 0 features, confirm the error appears and no API call is made.

**Coordination note:** Check `../00-PROJECT-LEAD/BUG-STATUS.md` for the BACKEND-API agent's B1-B decision on whether PATCH/PUT should exist. Either way, your fix is the same — the initial POST must carry the features.

### BUG-002 — Deprecated features referenced in experiments with no warning [Medium]

Your tasks (F2-A through F2-E) — these depend on BACKEND-API deploying new response fields first. Build the UI now; verify once the backend is deployed.

**F2-A:** On the experiment detail page, add an amber warning banner when `response.deprecated_features.length > 0`. Content: `"N feature(s) in this experiment are no longer available: [comma-separated names]. Results from this run remain valid, but these features cannot be selected in new experiments."` Dismissable for the session (React state, no localStorage).

**F2-B:** On the experiment list page, add a small amber warning badge/icon on any card where `has_deprecated_features === true`. Tooltip: `"This experiment references features that are no longer available"`.

**F2-C:** In the clone wizard, when loading the source experiment: (1) filter out deprecated features from the pre-selected set — `activeFeatures = features.filter(f => !deprecated_features.map(d => d.name).includes(f))`, (2) show a static alert in Step 3 naming the excluded features and asking the user to select substitutes, (3) the pre-selected count badge must reflect only active features.

**F2-D:** Confirm the feature search in Step 3 doesn't surface deprecated features. This should be automatic once the backend excludes them from `GET /api/v1/features` — just verify after backend deploys.

**F2-E:** After BACKEND-API deploys B2-C and B2-D: open `v2-23base-faithful-2015-2024`, confirm the amber banner appears with both deprecated feature names. Open the experiments list, confirm the warning badge is present. Clone the experiment, confirm Step 3 shows N-2 features pre-selected and the alert names `def_qb_hit_rate` and `def_rush_yards_allowed_per_att`.

When done, build and deploy (`npm run build` → `gsutil -m rsync -r -d dist/ gs://nfl-frontend-nfl-model-471509/` → invalidate CDN cache) and write completion notes to `../00-PROJECT-LEAD/BUG-STATUS.md`.

</details>

---

## 🔴 CURRENT TASK — HC-S5: Hypothesis Chat page (assigned by PROJECT-LEAD, 2026-08-31)

cd /path/to/nfl-prediction-app/04-FRONTEND

### Task

Build the page where Matt types a hypothesis in plain English and is walked to an approved, running experiment. The backend is finished and deployed-ready: nine endpoints under `/api/v1/scoping`, 91 passing tests. You are building the interface to them and nothing else.

When you are done, Matt can open `/experiments/hypothesis`, type *"teams with heavier O lines perform better in poor weather"*, answer a fixed sequence of questions, read a brief, approve it, and watch the experiment run — landing in the same experiments list as a wizard-built one.

### Context — read before writing code

- `../00-PROJECT-LEAD/HYPOTHESIS-CHAT-BUILD-PLAN.md` — the plan. Read §"The one architectural idea", §"The two model calls, and their limits", and §"Binary acceptance criteria → Stage 5".
- `../00-PROJECT-LEAD/PHASE6_STATUS.md` — what S0–S4 actually built, including two places the plan was corrected during the build. Read the S3 section: the acceptance criterion about capability gaps changed, and the UI must show both kinds of gap.
- `../docs/DECISIONS.md` ADR-012 — the three guarantees. Two of them constrain your UI directly; see Requirements.
- `../03-BACKEND-API/app/schemas/scoping.py` — the exact response shapes. This is the contract; do not infer it from the plan's prose.
- Run the backend locally and open `/docs` to see all nine endpoints live before building against them.

Existing patterns to follow, not reinvent: `src/api/client.ts` (throws `ApiRequestError` with `status`/`code`/`requestId`), `src/api/queries.ts` (TanStack Query, keys `['resource', id, 'sub']`), `src/components/ui/*` (existing primitives), `src/pages/ExperimentsNewPage.tsx` (the current wizard — same problem, different shape; read it for conventions and for what to avoid).

### Scope

In-scope:
- `src/pages/HypothesisChatPage.tsx`
- `src/components/scoping/*` — suggested split: `SlotPrompt`, `BriefPreview`, `GovernorPanel`, `CapabilityGapNotice`
- `src/api/scoping.ts` and the matching hooks/types
- `src/App.tsx` — one route: `/experiments/hypothesis`
- `src/components/Layout.tsx` — one nav entry

Out-of-scope, do not touch:
- `ExperimentsNewPage.tsx` — the existing wizard stays exactly as it is. This is an additional door, not a replacement.
- Anything under `../03-BACKEND-API/`. If an endpoint seems wrong or missing, escalate — do not work around it client-side.
- Any existing page, and the deploy pipeline.

Kill-switch — stop and escalate if:
- You need a backend change, a new endpoint, or a changed response shape.
- You cannot build the flow without holding the config in client state as the source of truth (see Requirements 1).
- A new npm dependency seems necessary.
- This exceeds 4 hours.

### Requirements — the three that are not negotiable

**1. The server owns the config. The client never assembles one.**
Answers go to `POST /sessions/{id}/answers` one at a time and the server returns the next question. Do not build a local form object and submit it at the end — that recreates the drift ADR-012 exists to prevent. The client's job is to render what the server asks and post one answer back.

**2. A pre-fill is never an answer.**
`POST /sessions/{id}/extract` returns `prefills[]`, each with `confirmed: false`, a `confidence`, and an `evidence_quote` — the words from Matt's hypothesis that produced it. Render the question **still asked**, with the value populated and visibly distinct from something Matt typed, showing the quote. It becomes an answer only when he actively confirms. A pre-filled question that looks answered is the highest-consequence failure in this design; it makes the feature worse than the wizard, because it looks like it asked.

**3. The brief is read-only.**
`GET /sessions/{id}/brief` returns markdown rendered from the exact config that will run, and the hash it describes. Display it; do not make it editable. Editing happens by re-answering a slot. `POST /sessions/{id}/approve` takes the `config_hash` — send back the one the brief returned, never one you cached earlier. A `409 stale_brief` means an answer changed since it was rendered: re-fetch the brief and tell Matt why, do not retry with a different hash.

### Requirements — the rest

**Question rendering** is driven by `next_question.type` (`text`, `enum`, `multi_select`, `integer`, `float`, `filter`, `object`) and `options_from`, which takes exactly three forms: `literal:a,b,c`, `endpoint:/api/v1/features`, `schema:GameUniverseFilter`. Resolve options from those — never hardcode a feature name or filter field. When the filter schema is widened later, this page must widen with it and need no edit. Show `help` text where present.

**Feature mirroring:** selecting N features runs 2N. Say so, as the existing wizard does (P5-08).

**Capability gaps** come back from `/extract` in two kinds, and the difference is the point:
- `feature_catalog` — the measurement does not exist at all (OL weight)
- `filter_schema` — it exists as a model feature but the game universe cannot be restricted by it (weather)

Show both with their `nearest_expressible` and `suggested_definition`. Do not collapse them into one "not supported" message; a gap Matt can work around by changing his slice is a different situation from one that needs new data loaded.

**Governor panel:** `GET /sessions/{id}/review` returns `verdict`, `concerns[]` with severity, `evaluated_games`, `slice_fraction`. It is **advisory** — `advisory_only: true` — and must never disable the approve or dispatch button. Surface a `reconsider` verdict clearly and let Matt proceed anyway. A governor that blocks becomes a thing to route around.

**Degradation:** `extract` may return `extraction_unavailable: true` (no API key, or the call failed). That is normal, not an error state — the session completes by answering every question. `review` may 409 before completion. Neither can prevent reaching a run.

**Errors:** the API returns a flat envelope — `{error, code, request_id}` at the top level, not nested under `detail`. Use `code` to distinguish `stale_brief`, `approval_mismatch`, `not_approved`, `incomplete_scoping`, `already_dispatched`.

### Acceptance

- [ ] `/experiments/hypothesis` renders; `/experiments/new` still renders the existing wizard unchanged
- [ ] A full session runs end to end against the local backend: hypothesis → questions → brief → approve → dispatch → experiment appears in the list
- [ ] `npm run build` passes with `tsc` clean; no console errors on load in Chrome 124+
- [ ] Zero hardcoded feature names or filter field names — `grep` the new files and record the result
- [ ] A pre-filled question is visually distinct from an answered one, shows its evidence quote, and requires an explicit action to become an answer
- [ ] The brief cannot be edited in place
- [ ] Approve sends the hash from the most recent brief fetch; a forced `409 stale_brief` shows a clear message and re-fetches rather than retrying
- [ ] Approve is disabled until every required slot is answered; `missing_required` from the session state drives this
- [ ] A `reconsider` verdict does NOT disable approve or dispatch — demonstrate this
- [ ] Both gap kinds render distinguishably, with their suggested definition
- [ ] With the backend's `ANTHROPIC_API_KEY` unset, the whole flow still completes
- [ ] No file outside the in-scope list is modified

### Escalation

`../00-PROJECT-LEAD/HYPOTHESIS-CHAT-QUESTIONS.md`. The question, what you were doing, what you tried. Then exit. Do not guess forward.

### Returns-with

- Commit SHA, build output, wall-clock time
- The grep result for hardcoded feature/filter names
- A screenshot or description of a pre-filled question, showing how it differs from an answered one
- Confirmation that a `reconsider` verdict still allows dispatch
- Anything in the backend contract that made the UI awkward — that is signal about the API, and PROJECT-LEAD wants it
