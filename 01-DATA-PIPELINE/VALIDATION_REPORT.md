# Phase 1 Validation Report

**Generated:** 2026-05-03 10:57 UTC
**Project:** `nfl-model-471509`
**Seasons:** 2015–2025

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

### curated.plays

| Season | Plays | Check |
|--------|-------|-------|
| 2015 | 46,141 | ✅ |
| 2016 | 45,707 | ✅ |
| 2017 | 45,268 | ✅ |
| 2018 | 45,120 | ✅ |
| 2019 | 45,339 | ✅ |
| 2020 | 45,406 | ✅ |
| 2021 | 47,651 | ✅ |
| 2022 | 47,157 | ✅ |
| 2023 | 47,399 | ✅ |
| 2024 | 47,274 | ✅ |
| 2025 | 46,452 | ✅ |

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

### curated.plays — EPA null rate on pass/run plays

| Season | EPA Nulls | Total Pass/Run | Null % | Check |
|--------|-----------|----------------|--------|-------|
| 2015 | 0 | 32,594 | 0.0% | ✅ |
| 2016 | 0 | 32,391 | 0.0% | ✅ |
| 2017 | 0 | 32,068 | 0.0% | ✅ |
| 2018 | 0 | 31,880 | 0.0% | ✅ |
| 2019 | 1 | 32,157 | 0.0% | ✅ |
| 2020 | 0 | 32,572 | 0.0% | ✅ |
| 2021 | 0 | 34,139 | 0.0% | ✅ |
| 2022 | 0 | 33,770 | 0.0% | ✅ |
| 2023 | 0 | 33,957 | 0.0% | ✅ |
| 2024 | 0 | 33,471 | 0.0% | ✅ |
| 2025 | 0 | 32,937 | 0.0% | ✅ |

### curated.plays — qb_hit / sack null rate (must be 0%)

- qb_hit nulls: 0 / 508,914  ✅
- sack nulls:   0 / 508,914  ✅

4. Integrity Checks
===================


- Orphan plays (game_id not in curated.games): 0  ✅
- Duplicate game_ids in curated.games: 0  ✅
- Season range in curated.games: 2015–2025  ✅

5. Check Summary
================

**Total checks:** 71  |  **Passed:** 71  |  **Failed:** 0

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
