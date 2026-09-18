# Data Sources Inventory

**Owner:** PROJECT-LEAD (with input from DATA-PIPELINE and MODELING)
**Last updated:** 2026-09-18 (B1-1, `PLAN-BUCKET1-DATA-COVERAGE.md`)

This is the live registry of every data source the project has evaluated, is using, or is considering. Each entry records license terms, integration status, and whether backtests have validated its contribution.

The 2026-08-30 sourcing pass found that FTN, NGS, OTC contracts, combine, draft, rosters,
snap counts, and PFR advanced stats are all available free through `nfl_data_py` — no
scraping, no paid license. All of it was staged as parquet on 2026-08-30 and loaded to a
new `raw_ol_sources` BigQuery dataset on 2026-09-18 (B1-1). These are raw landing tables
only — nothing below is joined to `curated.games` or turned into a model feature yet. That
is B1-3 (time-varying features) and bucket 2 (proprietary/OL metrics) work.

## Source Status Legend

- **Active** — integrated and feeding the curated layer
- **Planned** — committed for near-term integration
- **Evaluating** — under investigation, no commitment yet
- **Deprioritized** — looked at and set aside; may revisit
- **Rejected** — not pursuing

## Sources

### nflfastR / nflverse — `Active` (primary)
- **License tag:** `open`
- **Coverage:** Play-by-play 1999–present, weekly/seasonal/roster, schedules
- **Access:** `nfl_data_py` Python library
- **Cost:** Free
- **Update cadence:** Nightly during season
- **Notes:** The spine. Includes EPA, WP, CPOE, drive/series. Carries no licensing constraints — safe for public surfaces. `import_schedules()` `spread_line` / `total_line` fields confirmed as closing spreads (sourced from Pro-Football-Reference), 0% null rate across 2015–2025 REG season — used as the closing line source for Phase 1 backtest. No separate odds data source needed.
- **Backtest contribution:** TBD (Phase 1 baseline — currently in MODELING)

### FTN charting (via nflverse) — `Planned`
- **License tag:** `open` (verify before relying on this)
- **Coverage:** Manual play charting, play-level
- **Access:** `nfl_data_py.import_ftn_data()`, through nflverse data releases
- **Cost:** Free with nflverse
- **Notes:** Loaded raw 2026-09-18: `raw_ol_sources.ftn_charting`, 185,215 rows, 2022–2025.
  Gives `n_blitzers`, `n_pass_rushers`, `is_qb_out_of_pocket`, `is_qb_fault_sack`. Play-level —
  needs the same season-to-date, no-lookahead aggregation `ol_metrics.py` already does for
  `curated.plays` before it's feature-ready. Not yet joined to `curated.games`.
- **Backtest contribution:** TBD

### NFL Next Gen Stats — `Planned`
- **License tag:** `open` (public release)
- **Coverage:** Tracking-derived metrics, per QB/RB per week
- **Access:** `nfl_data_py.import_ngs_data()` — the public release covers this; no
  club-credentialed API needed (settled 2026-08-30, corrects this entry's prior "Evaluating
  — public-facing tables only, access path unclear")
- **Cost:** Free
- **Notes:** Loaded raw 2026-09-18: `raw_ol_sources.ngs_passing` (5,933 rows, 2016–2025:
  `avg_time_to_throw`, `completion_percentage_above_expectation`, `aggressiveness`) and
  `raw_ol_sources.ngs_rushing` (6,059 rows, 2016–2025: `rush_yards_over_expected`,
  `avg_time_to_los`). Not yet joined to `curated.games`.
- **Backtest contribution:** TBD

### Official injury reports (via nflverse) — `Planned`
- **License tag:** `open`
- **Coverage:** Weekly injury report status (Questionable/Doubtful/Out) and practice
  participation
- **Access:** `nfl_data_py.import_injuries()` — free and official, no scraping (settled
  2026-08-30; supersedes the "PFN scraper" entry below)
- **Cost:** Free
- **Notes:** Loaded raw 2026-09-18, filtered to OL positions: `raw_ol_sources.nflverse_ol_injuries`,
  10,937 rows, 2015–2025. B1-3 gates feature work on this on a point-in-time verification
  (week-grain report vs. final-state overwrite) — not yet done. Not yet joined to `curated.games`.
- **Backtest contribution:** TBD

### Official depth charts (via nflverse) — `Planned`
- **License tag:** `open`
- **Coverage:** Weekly depth chart, position-labelled (LT/LG/C/RG/RT for OL)
- **Access:** `nfl_data_py.import_depth_charts()` — free and official, no scraping (settled
  2026-08-30; supersedes the "PFN scraper" entry below)
- **Cost:** Free
- **Notes:** Loaded raw 2026-09-18, filtered to OL positions: `raw_ol_sources.nflverse_ol_depth_charts`,
  61,912 rows, 2015–2025. Same B1-3 point-in-time verification gate as injury reports above.
  Not yet joined to `curated.games`.
- **Backtest contribution:** TBD

### OverTheCap contracts (via nflverse) — `Planned`
- **License tag:** `open`
- **Coverage:** Player-contract grain: cap value, APY, guaranteed $, draft round/pick,
  weight, college, DOB
- **Access:** `nfl_data_py.import_contracts()`, flattened
- **Cost:** Free
- **Notes:** Loaded raw 2026-09-18: `raw_ol_sources.otc_contracts_flat`, 52,103 players
  (8,558 LT/LG/C/RG/RT). The nested `contracts.parquet` (season-by-season struct columns)
  was deliberately not loaded — it OOMs a naive read; `contracts_flat.parquet` is the
  loaded replacement. Not yet joined to `curated.games`.
- **Backtest contribution:** TBD

### NFL combine testing (via nflverse) — `Planned`
- **License tag:** `open`
- **Coverage:** Raw combine testing: forty, bench, vertical, broad jump, cone, shuttle,
  height, weight
- **Access:** `nfl_data_py.import_combine_data()`
- **Cost:** Free
- **Notes:** Loaded raw 2026-09-18: `raw_ol_sources.nflverse_combine`, 8,649 rows (1,423
  OL), 2000–2025 draft classes. Raw ingredients for a RAS-equivalent athleticism composite
  (RAS itself was not scraped — no clear bulk-access terms on ras.football). Not yet joined
  to `curated.games`.
- **Backtest contribution:** TBD

### NFL draft picks (via nflverse) — `Planned`
- **License tag:** `open`
- **Coverage:** Pick-level draft capital plus PFR career-value fields (`seasons_started`,
  `games`, `w_av`, `car_av`, `dr_av`)
- **Access:** `nfl_data_py.import_draft_picks()`
- **Cost:** Free
- **Notes:** Loaded raw 2026-09-18: `raw_ol_sources.nflverse_draft_picks`, 9,328 rows
  (1,557 OL), 1990–2025. Authoritative for original drafting team/slot — cross-check against
  `otc_contracts_flat` above, which records draft info as of second-contract signing. Not
  yet joined to `curated.games`.
- **Backtest contribution:** TBD

### Seasonal rosters (via nflverse) — `Planned`
- **License tag:** `open`
- **Coverage:** Age, weight, college, years of experience, entry year, draft number, per
  team/season
- **Access:** `nfl_data_py.import_seasonal_rosters()`
- **Cost:** Free
- **Notes:** Loaded raw 2026-09-18: `raw_ol_sources.nflverse_seasonal_rosters`, 33,184 rows
  (5,615 OL: T/G/C/OL), 2015–2025 — matches the existing pipeline's season range. Not yet
  joined to `curated.games`.
- **Backtest contribution:** TBD

### OL snap counts (via nflverse) — `Planned`
- **License tag:** `open`
- **Coverage:** Per-player, per-game offense snap counts/percentage
- **Access:** `nfl_data_py.import_snap_counts()`, filtered to OL positions
- **Cost:** Free
- **Notes:** Loaded raw 2026-09-18: `raw_ol_sources.nflverse_ol_snap_counts`, 51,281 rows,
  2013–2025. Continuity signal — detects in-season snap-share collapse better than a
  boolean start/didn't-start flag. Not yet joined to `curated.games`.
- **Backtest contribution:** TBD

### PFR advanced stats — QB pressure and rushing YBC (via nflverse) — `Planned`
- **License tag:** `open`
- **Coverage:** QB pocket_time/times_pressured/times_hit/times_blitzed (seasonal and
  weekly grain); rushing yards-before-contact per ball-carrier-season
- **Access:** `nfl_data_py.import_seasonal_pfr()` / `import_weekly_pfr()`
- **Cost:** Free
- **Notes:** Loaded raw 2026-09-18: `raw_ol_sources.pfr_qb_pressure` (848 rows, 2018–2025,
  season grain), `raw_ol_sources.pfr_weekly_qb_pressure` (5,424 rows, 2018–2025, per-game
  grain — better fit for the walk-forward weekly backtest), `raw_ol_sources.pfr_rushing_yards_before_contact`
  (2,820 rows, 2018–2025 — needs aggregation to team level). Independent, non-nflfastR-derived
  cross-checks against `ol_pressure_proxy_rate`. Not yet joined to `curated.games`.
- **Backtest contribution:** TBD

### Sports Info Solutions (SIS) — `Evaluating`
- **License tag:** `licensed_commercial` (when licensed)
- **Coverage:** Granular OL/DL data, charting
- **Access:** Requires license; pricing inquiry pending
- **Cost:** TBD — license-dependent
- **Notes:** Closest commercial alternative for granular OL data. License terms will determine whether it can appear in the public API.
- **Backtest contribution:** TBD

### PFF — `Deprioritized`
- **License tag:** `personal_use_only` (PFF+ subscription)
- **Coverage:** Player grades, charting
- **Access:** Personal subscription, no commercial API
- **Cost:** Subscription
- **Notes:** Recent restructuring + negative sentiment + ratings not matching eye test last season. May reappear later as one signal among many. Will never serve as the spine. If used at all, derived features carry `personal_use_only` and are filtered from public API responses.
- **Backtest contribution:** TBD

### PFN scraper — `Rejected`
- **License tag:** `open` (scraped public web pages)
- **Coverage:** Depth charts, injury reports
- **Access:** HTML scrape; respect robots.txt and rate limits
- **Cost:** Free
- **Notes:** Superseded 2026-08-30 — both depth charts and injury reports are free and
  official through nflverse (`import_depth_charts()`, `import_injuries()`), no scraping
  needed. See the "Official injury reports" and "Official depth charts" entries above.

### Covers / ESPN scrapers — `Evaluating`
- **License tag:** `open` (scraped public web pages)
- **Coverage:** Lines, lineups, basic stats
- **Access:** HTML scrape; respect robots.txt and rate limits
- **Cost:** Free
- **Notes:** Use sparingly; prefer official sources where they exist. For market lines specifically, official odds APIs may be a better long-term answer.

## Promotion Criteria

A source moves from `Evaluating` to `Planned` to `Active` based on:
1. License terms compatible with intended use (public API or personal-only)
2. Reliable access pattern (won't disappear in 6 months)
3. **For non-spine sources:** measurable backtest contribution beyond what nflfastR alone provides

A source moves to `Deprioritized` when its contribution doesn't justify integration cost, or its reliability becomes questionable.
