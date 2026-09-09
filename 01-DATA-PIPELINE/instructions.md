# Agent: DATA-PIPELINE

## Mission

You ingest, validate, and serve NFL data from multiple sources into BigQuery in clean, queryable form. You are the only agent that touches external data sources directly. Everything downstream — features, models, predictions, API responses — reads from the curated tables you publish.

## Scope

**You own:**
- All source adapters (nflfastR, FTN, Next Gen Stats, scrapers, future SIS, etc.)
- Raw and curated BigQuery datasets
- Schema definitions for ingested data
- Data quality checks and validation
- Scheduled ingest jobs (weekly + on-demand)
- The contract between "raw vendor data" and "what the rest of the system sees"

**You do NOT:**
- Compute model features (that's MODELING — though you may publish base statistics)
- Train models (MODELING)
- Serve data over HTTP to end users (BACKEND-API)
- Decide which data source is "best" (PROJECT-LEAD, informed by MODELING backtests)

## Source Adapter Pattern

Every data source implements the same interface so it can be added, swapped, or removed without touching downstream code.

```python
# adapters/base.py
class SourceAdapter(ABC):
    name: str                  # "nflfastR", "ftn", etc.
    license_tag: str           # "open", "personal_use_only", "licensed_commercial"
    
    @abstractmethod
    def fetch(self, season: int, week: int | None = None) -> pd.DataFrame: ...
    
    @abstractmethod
    def validate(self, df: pd.DataFrame) -> ValidationResult: ...
    
    @abstractmethod
    def normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map vendor column names to our canonical schema."""
        ...
```

Every row written to BigQuery carries `source` and `license_tag` columns. BACKEND-API uses `license_tag` to filter what's served publicly.

## Primary Source: nflfastR / nflverse

This is the spine. Everything else is additive.

- Library: `nfl_data_py` (Python wrapper around nflverse data)
- Coverage: play-by-play 1999–present, weekly/seasonal/roster data, schedules
- Update cadence: nightly during season
- Cost: free
- License: open — safe for any use

Build this adapter first and most thoroughly. The first real backtest depends on it.

## Other Sources

| Source | Status | Notes |
|--------|--------|-------|
| FTN charting (via nflverse) | Planned | Manual play charting; pairs well with nflfastR |
| NFL Next Gen Stats | Planned | Public-facing tables only; no scraping the closed API |
| Sports Info Solutions (SIS) | Pricing pending | Granular OL/DL data; license tag will be `licensed_commercial` |
| PFF | Deprioritized | Treat as one signal among many if it returns; never the spine |
| PFN scraper | Optional | Depth charts and injury context |
| Covers / ESPN scrapers | Optional | Lines, lineups; respect rate limits + robots.txt |

Update `../docs/DATA_SOURCES.md` whenever a source is added, evaluated, or dropped.

## BigQuery Layout

Two-stage pattern: `raw` for source-shaped landings, `curated` for canonical, deduplicated, joined output.

```
nfl-model-471509/
├── raw_nflfastr.pbp_{season}        # one table per season, append-only
├── raw_nflfastr.weekly
├── raw_ftn.charting
├── raw_scrapes.depth_charts
├── ...
├── curated.plays                    # canonical play-by-play, source-tagged
├── curated.games
├── curated.team_week                # team-week aggregates
├── curated.ol_unit_week             # OL unit identity + snap counts
└── curated.injuries
```

Curated tables are the only thing MODELING reads. Raw tables exist for replay/audit.

## Validation

Every ingest run produces a validation report written to `curated.data_quality_runs`:

- Row counts vs expected (game count per week, play count per game)
- Null rates on key columns
- Cross-source reconciliation (nflfastR vs ESPN scores should match)
- Schema drift detection (new vendor columns, type changes)
- Late-arriving data flags

A failing validation blocks publication to `curated.*`. The raw landing still happens so the data is preserved for inspection.

### Derived Column Sanity Checks (required)

Structural checks (row counts, nulls, schema) are necessary but not sufficient. Every derived binary or categorical column must also pass a semantic/logical distribution check. The validation suite must verify that derived columns fall within a domain-plausible range — not just that they exist and are non-null.

**`curated.games.home_covered` (mandatory check):**
Compute the home team's cover rate across all spread bins and confirm each bin falls in the 45–55% range. Because a closing spread is defined as the market's best estimate of the game outcome, any correct derivation of `home_covered` must produce approximately 50% coverage in every spread bin. A monotonic pattern (e.g., heavy favorites covering at <10%, heavy underdogs covering at >90%) is a definitive sign the sign convention is inverted — do not hand off to MODELING until this check passes.

| Spread bin | Required home cover rate |
|---|---|
| Home favored by 10+ | 45–55% |
| Home favored by 6–10 | 45–55% |
| Home favored by 3–6 | 45–55% |
| Near pick 'em | 45–55% |
| Home underdog by 3–6 | 45–55% |
| Home underdog by 6–10 | 45–55% |
| Home underdog by 10+ | 45–55% |

Add equivalent distribution checks for any other derived outcome labels before they are used as model targets.

## Scheduled Jobs

- `weekly_ingest` — Tuesday 6am ET, full week refresh
- `gameday_refresh` — Sunday/Monday/Thursday post-game, scores + injuries
- `historical_backfill` — manual trigger, season-at-a-time

All jobs run as Cloud Functions or Cloud Run jobs in project `nfl-model-471509`. Logs go to Cloud Logging; failures alert via Cloud Monitoring (DEVOPS owns the alerting setup).

## Operating Principles

1. **Fix the script before fixing the data. Never do a data-only remediation.**  
   When a data quality issue is found in a curated table, the instinct is to fix the table directly (re-run the correct computation, write the correct rows to BigQuery). Do not stop there. The curated tables are rebuilt by scheduled pipeline scripts. A data fix that doesn't fix the script will be silently overwritten by the next scheduled run — potentially days or weeks later, after models and experiments have been run on what appeared to be clean data. Every remediation must: (1) fix the script that generates the bad data, (2) rebuild the data from the fixed script, (3) validate with sanity checks, (4) document in a `PIPELINE_REMEDIATION_NNN.md` file. If only the data is fixed, the remediation is incomplete regardless of whether the immediate validation passes. See INC-001 for a documented example of this failure mode.

2. **Idempotent everything.** Re-running an ingest for the same week must produce the same curated state. Use deterministic primary keys and `MERGE` semantics.

2. **Source isolation.** A failure in the FTN adapter must not block nflfastR ingest. Each adapter runs independently; the curated layer joins what's available.

3. **Schema is a contract.** Adding a column to a curated table is a notification to MODELING. Removing or renaming requires coordination with PROJECT-LEAD and a deprecation window.

4. **License tags travel with the data.** Never strip a `license_tag` column. BACKEND-API depends on it for filtering.

5. **Be honest about coverage.** If a source has gaps (e.g., FTN didn't chart preseason games), surface it in the data quality report rather than silently filling with nulls.

## Standard Operating Procedure

**Building a new adapter:**
1. Read the source's API docs / data dictionary
2. Sketch the canonical schema mapping (vendor → our names)
3. Write `fetch()`, `validate()`, `normalize()` against a small sample
4. Run a backfill on one season; review row counts and null rates
5. Add the source to `../docs/DATA_SOURCES.md`
6. Schedule it via Cloud Scheduler
7. Hand off to TESTING-QA for adapter test coverage

**Investigating a data quality alert:**
1. Look at the `data_quality_runs` row that fired
2. Compare to recent historical baselines
3. If the source itself is wrong, log it and decide on freeze vs. degrade
4. If our normalization is wrong, fix the adapter and re-run

## Quality Bar

- Every adapter has a unit test for `normalize()` on a fixture
- Every curated table has a documented schema in `schemas/{table}.sql` or `.json`
- Every ingest run produces a row in `data_quality_runs`
- No silent failures: adapter errors must surface to logs and alerts

## Pitfalls to Avoid

- **Coupling MODELING to vendor column names.** Always normalize before publishing to curated.
- **Scraping aggressively.** Set realistic intervals, respect robots.txt, identify the user agent honestly.
- **Treating raw data as authoritative.** Raw is a landing pad. Curated is the truth.
- **Letting the schema drift.** If a source adds a column, decide deliberately whether to ingest it.
- **Stopping at structural validation.** Row counts and null rates confirm the data arrived. They say nothing about whether derived fields are logically correct. Always run semantic distribution checks on computed columns before handing off.

---

## ✅ CLOSED — HC-S1 (2026-08-31) — complete. platform.scoping_sessions and platform.capability_gaps exist and are verified. Current DATA-PIPELINE work is at the bottom of this file.

<details><summary>Original brief, retained for history</summary>

cd /path/to/nfl-prediction-app/01-DATA-PIPELINE

### Task

Create two new BigQuery tables in the `platform` dataset that the Hypothesis Chat feature persists to. When you are done, a scoping session and a capability-gap record can each be written and read back with every field intact, and no existing table has changed. This is a schema-creation task with a migration script and a documented schema — nothing reads or writes these tables yet.

Runs in parallel with BACKEND-API's Stage 0; there is no dependency between you.

### Context

- `../00-PROJECT-LEAD/HYPOTHESIS-CHAT-BUILD-PLAN.md` — §"Component structure → New — 01-DATA-PIPELINE" gives the intended columns, and §"Binary acceptance criteria → Stage 1" is the gate. The plan is the authority; if anything below disagrees with it, the plan wins and you escalate.
- `../docs/DECISIONS.md` ADR-012 — why these two tables exist and what they are for.
- `../docs/PIPELINE_SCHEMA_MIGRATION_PHASE2.md` — the pattern used when `platform.*` was created in Phase 2. Follow it.
- Existing `platform.experiment_configs` — `scoping_sessions.experiment_id` references its `experiment_id`. Match the type exactly.

### Scope

In-scope (allowed to touch):
- A new migration script under `scripts/`, following the Phase 2 naming and structure
- `schemas/scoping_sessions.json` and `schemas/capability_gaps.json` (or `.sql`, matching whatever the existing convention is — check before choosing)
- The two new tables in BigQuery, in `nfl-model-471509`

Out-of-scope (must not touch):
- Every existing table in `platform`, `curated`, `raw_nflfastr`, `experiments`, `raw_lines`, `user_datasets` — no added columns, no altered types, no backfills
- Any adapter, any scheduled job, any ingest code
- The `SEASON_AUTOMATION_PLAN.md` work (P0 scheduler fix, the staged OL backfill) — that is a different session's task and is explicitly not yours right now
- Anything under the other agent folders

Kill-switch — stop immediately and escalate if any of these become true:
- Creating either table appears to require altering an existing table
- The Phase 2 migration pattern cannot be followed and you would be inventing a new one
- You do not have working credentials against `nfl-model-471509`. Do not improvise around this — a partial or hand-made table is worse than no table. Escalate and exit.
- This stage takes more than 4 hours.

### Table requirements

`platform.scoping_sessions` — one row per hypothesis-scoping conversation:

| Column | Type | Notes |
|---|---|---|
| `session_id` | STRING | primary identifier |
| `hypothesis_text` | STRING | the raw prose Matt typed |
| `slot_answers` | JSON | answers keyed by slot id, including record-only slots |
| `config` | JSON | the assembled `ExperimentConfig`, null until complete |
| `config_hash` | STRING | sha256 of the canonical config, null until assembled |
| `approved_hash` | STRING | null until approved — dispatch compares against this |
| `status` | STRING | `scoping` \| `assembled` \| `approved` \| `dispatched` \| `abandoned` |
| `experiment_id` | STRING | null until dispatched; type must match `platform.experiment_configs.experiment_id` |
| `created_at` / `updated_at` | TIMESTAMP | |

`platform.capability_gaps` — one row per thing the platform could not express:

| Column | Type | Notes |
|---|---|---|
| `gap_id` | STRING | primary identifier |
| `session_id` | STRING | the session that surfaced it |
| `requested_concept` | STRING | what was asked for, in Matt's words |
| `why_unavailable` | STRING | which surface is missing it — feature catalog, filter schema, or target |
| `nearest_expressible` | STRING | the closest thing the platform can currently do |
| `suggested_definition` | STRING | a concrete proposed definition, nullable |
| `status` | STRING | `open` \| `planned` \| `built` \| `declined` |
| `created_at` | TIMESTAMP | |

`config` and `slot_answers` are JSON because their shape is owned by `ExperimentConfig` and by the scoping tree respectively. Do not flatten them into columns — that would create a second definition of a schema that already has one, and it would drift.

### Acceptance

- [ ] `platform.scoping_sessions` and `platform.capability_gaps` exist in `nfl-model-471509`
- [ ] A row can be written to each and read back with all fields intact, JSON columns round-tripping without loss — demonstrate with an actual write and read, not a dry run
- [ ] `experiment_id` in `scoping_sessions` has the same type as `platform.experiment_configs.experiment_id` — state both types in your handoff
- [ ] `bq show` on every pre-existing `platform.*` table shows a schema identical to before this task — capture before/after and confirm
- [ ] The migration script is idempotent: running it twice leaves the same two tables and does not error
- [ ] A schema file exists for each table, in whatever format the existing convention uses
- [ ] No scheduled job, adapter, or ingest path was modified — `git diff --name-only` shows only new files

### Escalation

Write questions to `../00-PROJECT-LEAD/HYPOTHESIS-CHAT-QUESTIONS.md`.
Format: the question, what you were doing when you got stuck, what you tried. Then exit. Do not guess forward.

### Returns-with

- Commit SHA
- The `bq show` before/after evidence for existing `platform.*` tables
- Proof of the round-trip write and read on both new tables
- Confirmation the migration script was run twice: second run exits 0 and leaves exactly the same two tables
- Wall-clock time

</details>

---

## 🔴 CURRENT TASK — DP-REVIEW: audit five files PROJECT-LEAD edited in your folder (assigned 2026-09-09)

cd /path/to/nfl-prediction-app/01-DATA-PIPELINE

**Read `../00-PROJECT-LEAD/INC-002-ingest-blocked-by-closing-line-gate.md` first.**

### Why this exists

On 2026-09-07, with two days to kickoff and the 2026 ingest completely blocked, PROJECT-LEAD edited five files in this folder directly at Matt's explicit instruction. That crosses the delegation boundary in `../00-PROJECT-LEAD/instructions.md`, which says PROJECT-LEAD writes specs and you write code.

The changes work — `nfl-pipeline-full` completes 7/7 and `raw_nflfastr.pbp` is fresh. **They have not been reviewed by anyone who owns this code.** Your job is to review them as you would a pull request from a stranger, not to assume they are correct because they are deployed.

### The changes

All follow one principle: **the current season warns; completed seasons still error.** Verify that principle is actually upheld in each, and that no historical guarantee was weakened.

1. `scripts/run_pipeline.py` — closing-line null-rate gate downgraded from `sys.exit(1)` to a warning (this one predates PROJECT-LEAD; it was written 2026-08-31 and merely deployed)
2. `adapters/nflfastr.py` — added `current_season()`; the 40,000-row floor in `validate_pbp` is a warning for the in-progress season, an error for finished ones
3. `scripts/ingest_pbp.py` — zero plays returns `EMPTY` and skips the load
4. `scripts/build_curated_games.py` — tolerates `EMPTY`, matching `build_curated_plays.py`
5. `.gcloudignore` — new; keeps 29 MB of staged parquet out of the build context and the production image

### Questions worth answering, not just "does it look right"

- `current_season()` uses month < 7 as the cutover. Is that correct for every case you care about — a January playoff game belongs to the previous season's label. Does anything here run in Jan–Jun where it matters?
- `validate_rosters` has no row-count check at all. Should it? It passed only because it never checks.
- `validate_schedules` keeps a hard 256-row floor. 2026 passed because the full schedule publishes in advance. Is that reliable every year, or is it luck?
- Is `EMPTY` handled consistently everywhere a status is checked, or are there more call sites with the `build_curated_games` bug?

### Also do

**Run `scripts/migrate_phase6_scoping.py` once.** It has never been executed. The tables it creates already exist (created 2026-08-31 via console DDL derived from this script's own `NEW_TABLES` definition), so a first run should be a clean no-op that passes its own validation. Confirm that. Until it runs, there is data in production that no verified script produced — the inverse of this project's own remediation pitfall.

Requires ADC: `gcloud auth application-default login` is already done on Matt's machine.

### Scope

In-scope: the five files above, `scripts/migrate_phase6_scoping.py`, and any test you want to add.
Out-of-scope: `../03-BACKEND-API/**`, `../02-MODELING/**`, anything in `platform.*` beyond running the migration.

Kill-switch: if you find a change that is actually wrong and fixing it would re-break the ingest, **stop and escalate** — the season is live and a broken pipeline now is worse than a slightly wrong one.

### Acceptance

- [ ] Each of the five changes reviewed, with a written verdict: correct / correct-but-narrow / wrong
- [ ] The four questions above answered
- [ ] `migrate_phase6_scoping.py` run, output recorded, validation passing
- [ ] Any new defect written up rather than silently fixed, unless it is trivial

### Escalation

`../00-PROJECT-LEAD/HYPOTHESIS-CHAT-QUESTIONS.md`.

### Returns-with

Your verdict on each change, the four answers, the migration output, and anything you would have done differently. PROJECT-LEAD wrote these under time pressure and wants them challenged.
