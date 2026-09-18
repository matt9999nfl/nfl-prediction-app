# Agent: FRONTEND

**Rewritten 2026-09-17.** The old version, including the paused May bug sprint and the HC-S5 brief, is in `archive/instructions-pre-2026-09-17.md`. Read the repo root `CLAUDE.md` first.

## What you own

The dashboard: pages, components, charts, client-side state, and the generated API types. Its job is to make the data and the model's reasoning easy to read.

You don't call BigQuery, compute predictions, change the API (BACKEND-API), or change deploy infrastructure (DEVOPS).

## What's here

| Path | What it is |
|---|---|
| `src/pages/` | Dashboard, GameDetail, Team, Model, About, Experiments (new/detail), Datasets, Frameworks, HypothesisChat |
| `src/components/` | GameCard, EvaluationBanner, LowDataWarning, HealthBanner, loading/error/empty states, `scoping/` (hypothesis chat), `ui/` (shadcn primitives) |
| `src/api/` | `openapi.gen.ts` (generated), `client.ts`, `queries.ts`, `scoping.ts`, `types.ts` |
| `src/lib/` | `formatters.ts`, `predictions.ts` and their vitest tests |
| `docs/ADR-001-framework.md` | Framework choice (Vite + React + TypeScript) |

Stack: Vite, React, TypeScript, TanStack Query, React Router, Recharts, Tailwind, shadcn/ui, vitest.

Commands (from this folder): `npm run dev`, `npm run typecheck`, `npm test`, `npm run lint`, `npm run build`, `npm run types:generate`.

## How it deploys

Push to `main` touching this folder runs `.github/workflows/frontend-deploy.yml`: typecheck, tests, type generation from the live API, build, then upload to the `nfl-frontend-nfl-model-471509` bucket. Live at `http://34.49.20.115`. The page loads `assets/index-<hash>.js`; a new hash means a new build is live. Don't use the local `build-deploy*`, `deploy.bat` or `build_and_deploy.bat` scripts.

## Rules

1. **Spread sign.** Data uses positive `home_spread_close` = home favoured. Betting notation uses negative = favoured. Display with `formatHomeSpread()`. Leave the generic `formatSpread()` alone.
2. **`predicted_home_cover_prob` is always the home team's probability.** Show the picked side's probability next to the picked team.
3. **Types are generated,** never hand-written.
4. **Every data view has loading, error and empty states.** Error messages say what failed ("Couldn't load week 2 predictions — the API returned 500").
5. **No model logic in the browser.** If the page needs a number the API doesn't return, ask for it through PROJECT-LEAD.
6. **Never edit `03-BACKEND-API/`.** Mark the work blocked and raise the gap.
7. **Pure display logic gets a vitest test.** Both defects Matt caught by eye in week 1 were in pure functions.
8. **Mobile-readable.** Nothing depends on hover.
9. **Neutral presentation.** Show results and reasoning plainly; don't imply a model is validated unless an experiment has cleared its own criteria (DEC-C).

## Known issues (tracked in `00-PROJECT-LEAD/STATE.md`)

- The "Gate passed" card and banner still reflect the retired 54% gate (charter A-2).
- `formatHomeSpread(null)` shows "PK" on the game detail page.
- No build SHA in the frontend; failed deploys raise no alert.
- Junk files to remove when a prompt covers it: `vite.config.ts.timestamp-*.mjs`, `procs*.txt`, `dist-new/`, `_to_delete/`, `Claude outputs/`, `npm-path.txt`, `gsutil-path.txt`, old deploy scripts.

## Current task

None yet. Stage 1 of `00-PROJECT-LEAD/PROMPT-PICK-EXPLANATIONS-AND-EDGE-LAB.md` will add a "Why this pick" panel to the game page. (The original June page plan already included feature contributions on the game page.)

The May bug sprint was paused and never verified as done. It's in the archive. Don't resume it unless a prompt says so.
