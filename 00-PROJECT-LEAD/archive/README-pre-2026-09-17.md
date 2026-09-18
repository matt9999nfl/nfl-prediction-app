# NFL Prediction App

Multi-agent architecture for a data-driven NFL prediction platform. The working hypothesis is that offensive line (OL) performance — and its second-order effects — are systematically undervalued by betting markets, but the architecture is deliberately decoupled from any single data source or rating system so the hypothesis can be tested against multiple inputs.

## How to Work With This Repo

This project is organized around **six specialized Cowork agents**, each owning one domain. Every agent folder contains an `instructions.md` that defines its role, scope, interfaces, and quality bar.

To work on a specific domain, point Cowork at that folder. The agent reads its `instructions.md`, knows what it owns and what it doesn't, and collaborates with other agents through the contracts in `docs/`.

## Agents

| # | Agent | Mission |
|---|-------|---------|
| 00 | PROJECT-LEAD | Architecture decisions, contracts, sequencing |
| 01 | DATA-PIPELINE | Source data → BigQuery, validated and clean |
| 02 | MODELING | Features, backtests, predictions |
| 03 | BACKEND-API | REST API serving predictions and game data |
| 04 | FRONTEND | Dashboard and game detail UI |
| 05 | DEVOPS | GCP deployment, scheduling, monitoring |
| 06 | TESTING-QA | Test suites and quality gates |

## Shared Documents (`docs/`)

These are the cross-agent contracts. All agents read these; PROJECT-LEAD owns and updates them.

- `ARCHITECTURE.md` — System overview, data flow, component boundaries
- `API_CONTRACTS.md` — REST endpoint shapes between BACKEND-API and FRONTEND
- `DECISIONS.md` — Architecture Decision Records (ADRs)
- `DATA_SOURCES.md` — Inventory of evaluated data sources, status, and licensing notes

## Project Constants

- **GCP project ID:** `nfl-model-471509`
- **Existing infrastructure:** Cloud Functions, BigQuery datasets, Cloud Storage buckets
- **Time budget:** ~10 hrs/week (often in short bursts via remote desktop / DeX)
- **Stage:** Pre-validation. The OL hypothesis has not yet been backtested on real historical data with multiple data sources.

## Data Source Strategy

The pipeline is built around **swappable adapters**, not a single vendor. Treat each source as an input feature class that earns or loses its place based on backtest contribution.

**Primary spine — `nflfastR` / `nflverse`**
- Free, open-source, play-by-play back to 1999, updated nightly
- Includes EPA, Win Probability, CPOE, drive/series data
- Python via `nfl_data_py`
- No licensing constraints — safe for portfolio and public-facing use
- This is the foundation; everything else is additive

**Evaluated supplements** (status tracked in `docs/DATA_SOURCES.md`):
- **FTN charting data** — accessed via nflverse, manual play charting
- **NFL Next Gen Stats** — public-facing tables
- **Sports Info Solutions (SIS)** — pricing/licensing under evaluation
- **PFF** — *deprioritized*. Ratings didn't match eye test last season; recent restructuring and sentiment make it unreliable as a foundation. May appear later as one signal among many, never the spine.
- **Scraped sources (PFN, Covers, ESPN)** — used for injury/lineup signals; observe rate limits and ToS

**Portfolio-facing rule:** anything that ends up in the public BACKEND-API or FRONTEND must be from sources that allow it. nflfastR-derived outputs are always safe; anything else is filtered by license tags carried through the pipeline.

## Critical Constraints

1. **Validation before product.** Phase 1 (data + backtest) is a hard gate. Don't invest in BACKEND/FRONTEND polish until the OL hypothesis is validated on historical data with proper out-of-sample testing.
2. **Source-agnostic design.** No agent assumes a specific vendor. Features are defined by what they measure, not where they came from. This is what lets you swap PFF for nflfastR-derived metrics or add SIS later without rewriting the model.
3. **Remote-friendly.** The system runs on GCP and is operable via REST API and scheduled jobs. You should be able to trigger runs and check status from a phone or remote desktop without local tooling.
4. **Respect data source ToS.** Scraping must observe rate limits and robots.txt. Prefer official/permissive sources where they exist.

## Phases

**Phase 1 — Foundation & Validation (Weeks 1–3)**
DATA-PIPELINE builds the nflfastR-backed historical store. MODELING ports the OL analysis to use nflfastR-derived features and runs the first real backtest. PROJECT-LEAD reviews backtest results before unlocking Phase 2.

**Phase 2 — Service Layer (Weeks 4–5)**
BACKEND-API exposes validated predictions. FRONTEND ships a minimum dashboard.

**Phase 3 — Productionize (Week 6+)**
DEVOPS deploys, schedules, and monitors. TESTING-QA hardens with integration tests. Iterate on supplemental data sources based on backtest contribution.
