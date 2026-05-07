# DATA-PIPELINE Spec — Phase 1

**Owner:** PROJECT-LEAD
**Consumer:** DATA-PIPELINE (implements), MODELING (reads curated layer)
**Last updated:** 2026-05-02
**Status:** Active — Phase 1

---

## Purpose

This spec defines everything DATA-PIPELINE must deliver before MODELING can begin Phase 1 work. It covers what to ingest, where to land it in BigQuery, the exact schemas MODELING will read from, closing line sourcing, and the validation checklist that gates the handoff.

Do not start MODELING until all items in the **Handoff Checklist** at the bottom of this document are green.

---

## Scope

Phase 1 data work is **nflfastR + closing lines only.** No FTN, NGS, SIS, PFF, or scraped sources. Those are Phase 3 additions evaluated on backtest contribution.

Seasons in scope: **2015–present** (current completed season).
Season types in scope: **REG only** for the curated layer. Load POST to raw but do not surface it in curated.

---

## BigQuery Dataset Structure

```
nfl-model-471509
├── raw_nflfastr
│   ├── pbp                  ← play-by-play, all columns, 2015–present
│   ├── schedules            ← game schedule + results, 2015–present
│   └── rosters              ← weekly rosters, 2015–present
├── raw_lines
│   └── closing_spreads      ← historical closing spreads, 2015–present
└── curated
    ├── games                ← one row per REG season game, joined + derived
    └── plays                ← filtered play-by-play, REG season, key columns
```

Raw tables are append-tolerant and keep all source columns. Curated tables are the contract surface — MODELING reads only from `curated.*`. Do not change a curated schema without a PROJECT-LEAD review.

---

## Ingestion Tasks

### Task 1 — nflfastR Play-by-Play → `raw_nflfastr.pbp`

**Source:** `nfl_data_py.import_pbp_data(seasons)`
**Seasons:** 2015 through current completed season
**Load all columns** from the source. Do not drop columns at the raw layer.

Partitioning: partition by `season` (INTEGER). Clustering: `game_id`, `posteam`.

Write mode: replace partition per season on full refresh. On incremental runs, replace current season partition only.

---

### Task 2 — nflfastR Schedules → `raw_nflfastr.schedules`

**Source:** `nfl_data_py.import_schedules(seasons)`
**Seasons:** 2015 through current completed season

This table is the source of game metadata and is also the primary candidate for closing line data (see Closing Line Sourcing below). Load all columns.

Partitioning: partition by `season`.
Write mode: replace partition per season.

---

### Task 3 — nflfastR Rosters → `raw_nflfastr.rosters`

**Source:** `nfl_data_py.import_rosters(seasons)` or `import_weekly_rosters(seasons)`
**Seasons:** 2015 through current completed season

Rosters are needed in Phase 1 for OL personnel tracking (identifying which players are on the OL week-to-week). Weekly rosters are preferred over seasonal snapshots.

Partitioning: partition by `season`.
Write mode: replace partition per season.

---

### Task 4 — Closing Lines → `raw_lines.closing_spreads`

See **Closing Line Sourcing Decision** section below. Schema is defined there.

---

### Task 5 — Build `curated.games`

Join `raw_nflfastr.schedules` with `raw_lines.closing_spreads` (or use the spread fields from schedules directly if the sourcing decision lands there). Filter to `season_type = 'REG'`. Derive `home_covered`.

This is a **transformation job**, not a raw ingest. Run after Tasks 2 and 4 complete.

---

### Task 6 — Build `curated.plays`

Filter `raw_nflfastr.pbp` to REG season games only. Select the columns in the schema below. Join to `curated.games` on `game_id` to confirm referential integrity.

This is a transformation job. Run after Tasks 1 and 5 complete.

---

## Schemas

### `curated.games`

One row per regular season game. This is MODELING's primary game-level table.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `game_id` | STRING | NO | nflfastR canonical game ID (e.g. `2019_01_GB_CHI`) |
| `season` | INT64 | NO | 4-digit year |
| `week` | INT64 | NO | 1–18 |
| `game_date` | DATE | NO | |
| `home_team` | STRING | NO | 3-letter code (nflfastR standard) |
| `away_team` | STRING | NO | |
| `home_score` | INT64 | YES | Null if game not yet final |
| `away_score` | INT64 | YES | |
| `home_spread_close` | FLOAT64 | YES | Closing spread, home team perspective. Negative = home favored (e.g. -3.0 means home favored by 3). |
| `total_close` | FLOAT64 | YES | Closing total (over/under) |
| `home_covered` | BOOL | YES | True if home team covered closing spread. Null if spread or score unavailable. Derivation: `(home_score - away_score) > -home_spread_close` |
| `season_type` | STRING | NO | Always 'REG' in this table |
| `roof` | STRING | YES | dome, outdoors, retractable, open |
| `surface` | STRING | YES | grass, turf, etc. |
| `div_game` | BOOL | YES | Divisional matchup flag |
| `stadium` | STRING | YES | |
| `temp` | FLOAT64 | YES | Game-time temperature (Fahrenheit) |
| `wind` | FLOAT64 | YES | Wind speed (mph) |

Partitioned by `season`. Clustered by `home_team`, `away_team`.

---

### `curated.plays`

One row per play, REG season only. MODELING derives all OL features from this table.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `play_id` | INT64 | NO | nflfastR play_id |
| `game_id` | STRING | NO | FK → curated.games.game_id |
| `season` | INT64 | NO | |
| `week` | INT64 | NO | |
| `posteam` | STRING | NO | Team with possession |
| `defteam` | STRING | NO | Defending team |
| `play_type` | STRING | NO | pass, run, punt, kickoff, field_goal, extra_point, qb_kneel, qb_spike, no_play |
| `down` | INT64 | YES | 1–4, null on kickoffs/punts |
| `ydstogo` | INT64 | YES | |
| `yardline_100` | INT64 | YES | Distance to end zone (1–99) |
| `yards_gained` | INT64 | YES | |
| `epa` | FLOAT64 | YES | Expected points added |
| `wpa` | FLOAT64 | YES | Win probability added |
| `qb_hit` | BOOL | NO | QB was hit on this play (default false) |
| `sack` | BOOL | NO | Play resulted in a sack (default false) |
| `touchdown` | BOOL | NO | |
| `interception` | BOOL | NO | |
| `fumble` | BOOL | NO | |
| `fumble_lost` | BOOL | NO | |
| `cpoe` | FLOAT64 | YES | Completion % over expected (null on non-pass plays) |
| `air_yards` | FLOAT64 | YES | Intended air yards (null on non-pass plays) |
| `yards_after_catch` | FLOAT64 | YES | |
| `score_differential` | INT64 | YES | posteam score minus defteam score at snap |
| `game_half` | STRING | YES | Half1, Half2, OT |
| `passer_player_id` | STRING | YES | |
| `passer_player_name` | STRING | YES | |
| `rusher_player_id` | STRING | YES | |
| `rusher_player_name` | STRING | YES | |
| `receiver_player_id` | STRING | YES | |
| `receiver_player_name` | STRING | YES | |
| `penalty` | BOOL | NO | |
| `penalty_type` | STRING | YES | |
| `penalty_team` | STRING | YES | |

Partitioned by `season`. Clustered by `game_id`, `posteam`.

---

## Closing Line Sourcing Decision

nflfastR play-by-play does not include betting lines. Closing spreads must be sourced and loaded separately. DATA-PIPELINE owns this decision, but must notify PROJECT-LEAD of the chosen source so `docs/DATA_SOURCES.md` can be updated before MODELING begins.

**Evaluate in this order:**

### Option 1 — nflverse schedules spread fields (check first)
`nfl_data_py.import_schedules()` includes `spread_line` and `total_line` fields. Before sourcing externally:
1. Confirm whether these are opening or closing lines (check nflverse documentation / source)
2. Check null rate across seasons 2015–present
3. If null rate < 5% and these are confirmed closing lines: **use this source.** Land them in `raw_nflfastr.schedules` (already loaded by Task 2) and derive `curated.games` fields directly. No separate `raw_lines.closing_spreads` table needed.

### Option 2 — nflverse game lines table
nflverse publishes a `game_lines` or similar table via `nfl_data_py`. Check whether this is available and what it covers.

### Option 3 — the-odds-api historical data
Requires API key. Covers historical odds back to ~2017 depending on tier. If used:
- Register the source in `docs/DATA_SOURCES.md` under license tag `open` (verify ToS)
- Land raw response in `raw_lines.closing_spreads`
- Coverage gap: check whether 2015–2016 is available; if not, document the gap

### Option 4 — Pro Football Reference spreads
Available via scrape. Covers back to 1978. If used, observe rate limits, verify ToS, and register in `docs/DATA_SOURCES.md`.

**Decision rule:** prefer the option with the cleanest access path and highest historical coverage. If Option 1 checks out, use it — fewer moving parts. Report your choice to PROJECT-LEAD before proceeding to curated layer builds.

### `raw_lines.closing_spreads` schema (if external source is needed)

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `game_id` | STRING | NO | Must match nflfastR game_id format exactly |
| `season` | INT64 | NO | |
| `week` | INT64 | NO | |
| `game_date` | DATE | NO | |
| `home_team` | STRING | NO | |
| `away_team` | STRING | NO | |
| `home_spread_close` | FLOAT64 | YES | Home perspective, negative = home favored |
| `total_close` | FLOAT64 | YES | |
| `source` | STRING | NO | e.g. 'the-odds-api', 'pfr-scrape' |
| `loaded_at` | TIMESTAMP | NO | When this row was ingested |

Partitioned by `season`.

**Critical:** The `game_id` in this table must match the nflfastR game_id format (`{season}_{week:02d}_{away}_{home}`) so the join to `curated.games` is unambiguous. If the source uses a different ID scheme, DATA-PIPELINE must build and maintain the crosswalk.

---

## Validation Criteria

All of the following must pass before DATA-PIPELINE marks the handoff as complete.

### Row count checks

| Table | Expected range | Notes |
|-------|---------------|-------|
| `raw_nflfastr.pbp` | ~40,000–65,000 rows per REG season | Higher end post-2021 (17-game season) |
| `raw_nflfastr.schedules` | 256–285 rows per REG season | 256 pre-2021, 272 from 2021+ |
| `curated.games` | Matches schedule count for REG | All games must be present |
| `curated.plays` | ~35,000–55,000 rows per REG season | After filtering to REG, scrimmage plays |

### Coverage checks

| Check | Pass threshold |
|-------|---------------|
| `curated.games.home_spread_close` null rate | ≤ 5% of REG season games |
| `curated.games.home_covered` null rate | ≤ 5% of games with final scores |
| `curated.plays.epa` null rate on pass/run plays | ≤ 5% |
| `curated.plays.qb_hit` null rate | 0% (default false if source null) |
| `curated.plays.sack` null rate | 0% (default false if source null) |

### Integrity checks

| Check | Expected |
|-------|---------|
| All `curated.plays.game_id` values exist in `curated.games` | 100% match |
| All `curated.games` seasons in range 2015–present | No out-of-range seasons |
| No duplicate `game_id` in `curated.games` | 0 duplicates |
| `home_team` values use consistent 3-letter codes | Matches nflfastR team abbreviation list |

### Validation report

DATA-PIPELINE must produce a short written validation report (Markdown or notebook) before handoff. It must include:
- Row counts per season for each table
- Null rate summary for key columns
- Closing line coverage % by season
- Any anomalies found and how they were handled
- The closing line source chosen and why

---

## Handoff Checklist

All boxes must be checked before MODELING begins:

- [ ] `raw_nflfastr.pbp` loaded and queryable, 2015–present
- [ ] `raw_nflfastr.schedules` loaded and queryable, 2015–present
- [ ] `raw_nflfastr.rosters` loaded and queryable, 2015–present
- [ ] Closing line source identified and reported to PROJECT-LEAD
- [ ] `docs/DATA_SOURCES.md` updated with closing line source
- [ ] `curated.games` built and passing all validation checks
- [ ] `curated.plays` built and passing all validation checks
- [ ] Validation report written and shared
- [ ] PROJECT-LEAD has acknowledged the handoff

---

## Out of Scope for Phase 1

- FTN charting data
- NFL Next Gen Stats (NGS)
- SIS data
- PFF data
- Any scraped sources (PFN, Covers, ESPN)
- Totals or player prop lines
- Current-week ingest or live data
- Cloud Scheduler setup (DEVOPS, Phase 3)

---

## Notes for DATA-PIPELINE

- Use `nfl_data_py` as the primary access library for nflfastR data. Do not scrape nflfastR GitHub directly.
- Team abbreviation standardization matters: nflfastR uses its own codes (e.g. `LA` not `LAR`, `LV` not `OAK`). Ensure closing line source is mapped to these codes, not ESPN or PFR codes.
- Franchise moves affect team codes over the 2015–present window (Raiders: OAK → LV 2020; Rams: STL → LA 2016; Chargers: SD → LAC 2017). Handle these consistently — use the code that nflfastR uses for that season.
- `home_covered` derivation: `(home_score - away_score) > -home_spread_close`. A push (exactly covering the spread) should be stored as `NULL`, not `TRUE` or `FALSE`.
