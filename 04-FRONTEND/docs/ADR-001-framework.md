# ADR-001 — Framework: Vite over Next.js

**Date:** 2026-05-06
**Status:** Accepted

## Context

The dashboard is a single-user internal tool. It has a handful of pages, no public-facing routes, no SEO requirements, and no server-side rendering needs. The primary runtime environment is the owner's browser, pointed at a local or Cloud Run backend API.

## Decision

**Vite + React + TypeScript.**

## Rationale

Next.js earns its overhead when you need SSR, ISR, edge middleware, or a file-system router at scale. None of those apply here. The considerations that matter for this project:

| Factor | Vite | Next.js |
|--------|------|---------|
| Cold-start dev server | ~200ms | ~2–4s |
| Build output | Static SPA, host anywhere | Node server or static export |
| SSR requirement | No | No |
| API routes needed | No — backend is separate | Tempting but unnecessary coupling |
| Routing complexity | React Router v6, explicit | File-system router (overkill) |
| Team size | 1 | N/A |

The only scenario where Next.js wins here is if we later need server components to hide API keys from the client bundle. At that point the migration is straightforward; the component tree doesn't change.

## Consequences

- Bundle is a static SPA. DEVOPS deploys it to Cloud Storage + CDN or any static host.
- API key is an env var baked at build time (`VITE_API_KEY`). Not secret-safe for multi-user; acceptable for single-user Phase 2.
- React Router v6 owns all client-side routing. No `next/link`, no `next/router`.
- Type generation: `openapi-typescript` runs as a dev script, not a Next.js API route.

## Revisit when

- The dashboard needs to run on a shared domain with per-user auth (→ Next.js Auth.js + server components)
- Bundle analysis shows the SPA exceeds 500kB gzipped and code-splitting isn't enough
