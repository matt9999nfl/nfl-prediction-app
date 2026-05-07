# Data Sources Inventory

**Owner:** PROJECT-LEAD (with input from DATA-PIPELINE and MODELING)
**Last updated:** 2026-05-03

This is the live registry of every data source the project has evaluated, is using, or is considering. Each entry records license terms, integration status, and whether backtests have validated its contribution.

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
- **Coverage:** Manual play charting
- **Access:** Through nflverse data releases
- **Cost:** Free with nflverse
- **Notes:** Pairs well with nflfastR for charting-derived features (defensive alignment, blitz indicators, etc.)
- **Backtest contribution:** TBD

### NFL Next Gen Stats — `Evaluating`
- **License tag:** depends on access path
- **Coverage:** Tracking-derived metrics
- **Access:** Public-facing tables only; no scraping the closed API
- **Cost:** Free for public tables
- **Notes:** Useful for context features (separation, time-to-throw) but limited public surface
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

### PFN scraper — `Evaluating`
- **License tag:** `open` (scraped public web pages)
- **Coverage:** Depth charts, injury reports
- **Access:** HTML scrape; respect robots.txt and rate limits
- **Cost:** Free
- **Notes:** Useful for current-week lineup context. Verify scraping policy and identify the user agent honestly.

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
