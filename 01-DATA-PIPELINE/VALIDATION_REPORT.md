# Phase 1 Validation Report

**Generated:** 2026-09-18 03:12 UTC
**Project:** `nfl-model-471509`
**Seasons:** 2015–2026

> Checks for **2026** are advisory: that season is still being played, so completed-season thresholds do not apply to it yet. They are shown as ⚠️ IN-PROGRESS and do not fail this report. Every earlier season is held to the full standard.

1. Row Counts — Raw Tables
==========================


### raw_nflfastr.pbp (all rows including preseason)

| Season | Rows | Check |
|--------|------|-------|
| 2015 | 48,122 | ✅ |
| 2016 | 47,651 | ✅ |
| 2017 | 47,245 | ✅ |
| 2018 | 47,109 | ✅ |
| 2019 | 47,260 | ✅ |
| 2020 | 47,705 | ✅ |
| 2021 | 49,922 | ✅ |
| 2022 | 49,434 | ✅ |
| 2023 | 49,665 | ✅ |
| 2024 | 49,492 | ✅ |
| 2025 | 48,771 | ✅ |
| 2026 | 2,756 | ❌ |

### raw_nflfastr.schedules

| Season | Rows | Check |
|--------|------|-------|
| 2015 | 267 | ✅ |
| 2016 | 267 | ✅ |
| 2017 | 267 | ✅ |
| 2018 | 267 | ✅ |
| 2019 | 267 | ✅ |
| 2020 | 269 | ✅ |
| 2021 | 285 | ✅ |
| 2022 | 284 | ✅ |
| 2023 | 285 | ✅ |
| 2024 | 285 | ✅ |
| 2025 | 285 | ✅ |
| 2026 | 272 | ✅ |

### raw_nflfastr.rosters

| Season | Rows | Check |
|--------|------|-------|
| 2015 | 32,098 | ✅ |
| 2016 | 35,020 | ✅ |
| 2017 | 51,321 | ✅ |
| 2018 | 52,238 | ✅ |
| 2019 | 51,632 | ✅ |
| 2020 | 44,130 | ✅ |
| 2021 | 46,696 | ✅ |
| 2022 | 46,163 | ✅ |
| 2023 | 45,655 | ✅ |
| 2024 | 46,579 | ✅ |
| 2025 | 46,849 | ✅ |
| 2026 | 2,963 | ✅ |

2. Row Counts — Curated Tables
==============================


### curated.games

| Season | Games | Check |
|--------|-------|-------|
| 2015 | 256 | ✅ |
| 2016 | 256 | ✅ |
| 2017 | 256 | ✅ |
| 2018 | 256 | ✅ |
| 2019 | 256 | ✅ |
| 2020 | 256 | ✅ |
| 2021 | 272 | ✅ |
| 2022 | 271 | ✅ |
| 2023 | 272 | ✅ |
| 2024 | 272 | ✅ |
| 2025 | 272 | ✅ |
| 2026 | 272 | ✅ |

### curated.plays

| Season | Plays | Check |
|--------|-------|-------|
| 2015 | 43,799 | ✅ |
| 2016 | 43,395 | ✅ |
| 2017 | 42,929 | ✅ |
| 2018 | 42,697 | ✅ |
| 2019 | 43,012 | ✅ |
| 2020 | 43,004 | ✅ |
| 2021 | 45,049 | ✅ |
| 2022 | 44,558 | ✅ |
| 2023 | 44,877 | ✅ |
| 2024 | 44,686 | ✅ |
| 2025 | 43,868 | ✅ |
| 2026 | 2,616 | ❌ |

3. Null Rate Checks
===================


### curated.games — closing line coverage

| Season | Spread Nulls | Total | Null % | Check |
|--------|-------------|-------|--------|-------|
| 2015 | 0 | 256 | 0.0% | ✅ |
| 2016 | 0 | 256 | 0.0% | ✅ |
| 2017 | 0 | 256 | 0.0% | ✅ |
| 2018 | 0 | 256 | 0.0% | ✅ |
| 2019 | 0 | 256 | 0.0% | ✅ |
| 2020 | 0 | 256 | 0.0% | ✅ |
| 2021 | 0 | 272 | 0.0% | ✅ |
| 2022 | 0 | 271 | 0.0% | ✅ |
| 2023 | 0 | 272 | 0.0% | ✅ |
| 2024 | 0 | 272 | 0.0% | ✅ |
| 2025 | 0 | 272 | 0.0% | ✅ |
| 2026 | 240 | 272 | 88.2% | ❌ |

### curated.plays — EPA null rate on pass/run plays

| Season | EPA Nulls | Total Pass/Run | Null % | Check |
|--------|-----------|----------------|--------|-------|
| 2015 | 0 | 32,594 | 0.0% | ✅ |
| 2016 | 0 | 32,391 | 0.0% | ✅ |
| 2017 | 0 | 32,068 | 0.0% | ✅ |
| 2018 | 0 | 31,880 | 0.0% | ✅ |
| 2019 | 1 | 32,157 | 0.0% | ✅ |
| 2020 | 0 | 32,575 | 0.0% | ✅ |
| 2021 | 0 | 34,139 | 0.0% | ✅ |
| 2022 | 0 | 33,770 | 0.0% | ✅ |
| 2023 | 0 | 33,957 | 0.0% | ✅ |
| 2024 | 0 | 33,470 | 0.0% | ✅ |
| 2025 | 0 | 32,941 | 0.0% | ✅ |
| 2026 | 0 | 1,911 | 0.0% | ✅ |

### curated.plays — qb_hit / sack null rate (must be 0%)

- qb_hit nulls: 0 / 484,490  ✅
- sack nulls:   0 / 484,490  ✅

3b. Semantic Check — home_covered Cover Rate
============================================


This check guards against a sign-inversion bug in `derive_home_covered`.
Because closing spreads represent the market's best estimate, the home team
cover rate in every spread bin must be approximately 50% (efficient market
hypothesis). A monotonic pattern (e.g. heavy favourites covering at <10%,
heavy underdogs covering at >90%) is a definitive sign of label inversion.
See INC-001 and PIPELINE_REMEDIATION_002.md for history.

| Spread Bucket | Covers | Total | Cover % | Check |
|---------------|--------|-------|---------|-------|
| home_dog_10+ | 135 | 266 | 50.8% | ✅ |
| home_dog_3-10 | 536 | 1128 | 47.5% | ✅ |
| home_fav_10+ | 43 | 79 | 54.4% | ✅ |
| home_fav_3-10 | 350 | 692 | 50.6% | ✅ |
| pick_em | 320 | 672 | 47.6% | ✅ |

- **Overall cover rate (2015–2026):** 48.8%  (1384/2837)  ✅

3c. Line Snapshot Freshness
===========================


`raw_lines.line_snapshots` is written by `snapshot_lines.py`, called
non-fatally from `run_ingest_schedules()` on every pipeline run so a snapshot
failure never blocks PBP/rosters ingest. Non-fatal previously also meant
invisible: the failure (or the deployed image simply not containing this
code) was only ever a line in Cloud Logging, never in this report or the
run's exit code -- the same silent-failure-only-logs-can-find pattern as
HC-S6-F6. This check makes a stale or empty snapshot table fail the run
visibly.

- `line_snapshots`: 3,300 row(s) total, latest capture 0.0 day(s) old (latest capture 2026-09-18 03:06:54.556173+00:00)  ✅

4. Integrity Checks
===================


- Orphan plays (game_id not in curated.games): 0  ✅
- Duplicate game_ids in curated.games: 0  ✅
- Season range in curated.games: 2015–2026  ✅

5. Check Summary
================

**Total checks:** 84  |  **Passed:** 81  |  **Failed:** 0

**Overall:** ✅ ALL CHECKS PASSED — ready for handoff

6. Closing Line Source
======================


**Source chosen:** nflverse schedules (`spread_line` / `total_line` fields via `nfl_data_py.import_schedules()`)

**Rationale:** nflverse documents `spread_line` as the closing spread (home-team perspective,
negative = home favored), sourced from Pro-Football-Reference historical lines.
Null rate analysis above confirms coverage ≤ 5% across 2015–present for REG season games.
No separate `raw_lines.closing_spreads` table is needed (Option 1 from spec).

**Columns used:**
- `spread_line` → `curated.games.home_spread_close`
- `total_line`  → `curated.games.total_close`

**home_covered derivation:** `(home_score - away_score) > home_spread_close`
nflverse sign convention: positive spread_line = home favored (home must win by that amount).
Push (exactly equal) is stored as `NULL`.
