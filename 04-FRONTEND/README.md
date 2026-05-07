# NFL Prediction Platform — Frontend

React + Vite + TypeScript dashboard. See `docs/ADR-001-framework.md` for the framework choice rationale.

## Quickstart

```bash
cd 04-FRONTEND

# 1. Copy env file and fill in values (optional in dev — Vite proxy handles it)
cp .env.example .env.local

# 2. Install dependencies
npm install

# 3. Start the dev server (proxies /api and /health to localhost:8000)
npm run dev
```

The app runs at http://localhost:3000. Make sure the backend API is running:

```bash
cd ../03-BACKEND-API
uvicorn app.main:app --reload
```

## TypeScript type generation

Types in `src/api/types.ts` are hand-authored from `docs/API_CONTRACTS.md`.
Once the API is running, regenerate them from the live OpenAPI schema:

```bash
npm run types:generate
```

This writes `src/api/openapi.gen.ts`. Swap the imports in `src/api/queries.ts` and
`src/api/client.ts` to use the generated file once it exists.

## Routes

| Path | Component | Step |
|------|-----------|------|
| `/` | DashboardPage | 1 |
| `/games/:gameId` | GameDetailPage | 1 |
| `/model` | ModelPage (experiments list) | 1 |
| `/datasets` | DatasetsPage | 2 |
| `/datasets/:datasetId` | DatasetDetailPage (schema mapping) | 2 |
| `/experiments/new` | ExperimentsNewPage (6-step wizard) | 3 |
| `/experiments/:id` | ExperimentDetailPage (run + results) | 3/4 |
| `/frameworks` | FrameworksPage | 4 |
| `/frameworks/:id` | FrameworkDetailPage | 4 |

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE_URL` | `` (empty) | Backend API origin. Empty = use Vite proxy (dev). Set to `https://api.yourdomain.com` in prod. |
| `VITE_API_KEY` | `` | X-API-Key header value. Leave empty if the backend doesn't enforce auth yet (Phase 2). |

## Build

```bash
npm run build       # TypeScript check + Vite build → dist/
npm run preview     # Serve the dist/ build locally
npm run typecheck   # tsc --noEmit only, no build
```

## Notes for DEVOPS

- Output is a static SPA in `dist/`. Deploy to Cloud Storage + CDN or any static host.
- The Vite proxy (`/api`, `/health`) is dev-only. In production, set `VITE_API_BASE_URL` and configure CORS on the backend to accept the frontend origin.
- No server-side rendering — this is a Vite SPA build.
