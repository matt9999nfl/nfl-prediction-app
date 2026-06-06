# Situational Filtering Experiment Plan

**Owner:** PROJECT-LEAD  
**Filed:** 2026-05-17  
**Phase:** 4 — Track 5  
**Agent:** MODELING  
**Status:** 🟡 Pending — awaiting MODELING implementation

---

## Context

Phase 4 Track 1 established that the v2 feature set produces no detectable ATS edge across the full regular-season game universe (48.8% on correct labels, 1,582 games). The rushing features similarly showed no edge.

The situational filtering hypothesis is: the v2 feature set may have signal in specific game subsets that gets averaged to noise across all 1,582 games. If the model finds edge in a meaningful subset, that is a real and exploitable result — it does not need to work on all games.

This plan defines: (1) the runner change needed, and (2) the experiments to run.

---

## Part A — Runner Change: `game_universe` Filter

### What needs to change

`run_experiment.py` currently loads all REG season games and passes them all to the walk-forward harness. A new optional `game_universe` key in the methodology config will allow filtering to a subset before the harness runs.

### Where to add the filter

After line 648 (the `build_feature_matrix` call), before line 656 (`run_walk_forward`). The feature matrix is built from all plays and all games first — season-to-date features must use the full season's data regardless of which games are being predicted. The filter is applied to `game_features` only, not to `plays` or `games` used for feature computation.

```python
# ── 4b. Apply game universe filter (optional) ─────────────────────────────
game_universe = methodology.get("game_universe")
if game_universe:
    field    = game_universe["field"]
    operator = game_universe.get("operator", "eq")
    value    = game_universe["value"]

    if field not in game_features.columns:
        raise ValueError(
            f"game_universe filter field {field!r} not found in game_features columns. "
            f"Available: {list(game_features.columns)}"
        )

    before = len(game_features)
    if operator == "eq":
        game_features = game_features[game_features[field] == value].copy()
    elif operator == "gte":
        game_features = game_features[game_features[field] >= value].copy()
    elif operator == "lte":
        game_features = game_features[game_features[field] <= value].copy()
    elif operator == "ne":
        game_features = game_features[game_features[field] != value].copy()
    else:
        raise ValueError(
            f"Unsupported game_universe operator {operator!r}. "
            "Supported: eq, gte, lte, ne"
        )

    after = len(game_features)
    logger.info(
        f"game_universe filter applied: {field} {operator} {value!r} — "
        f"{before:,} → {after:,} games ({before - after:,} excluded)"
    )

    if after < 100:
        raise ValueError(
            f"game_universe filter left only {after} games — too few to run a "
            "meaningful backtest. Widen the filter or use the full universe."
        )
```

Add this filter description to the BQ notes string so filtered runs are clearly labelled in the experiment log:

```python
if game_universe:
    notes_str = (
        notes_str
        + f" [UNIVERSE: {game_universe['field']} {game_universe.get('operator','eq')} {game_universe['value']}]"
    ).strip()
```

### Methodology config schema addition

The `game_universe` key is optional. When absent or null, behaviour is unchanged (all games used).

```json
"methodology": {
    "start_season": 2015,
    "end_season": 2025,
    "train_seasons": 4,
    "test_seasons": 1,
    "random_seed": 42,
    "game_universe": {
        "field": "div_game",
        "operator": "eq",
        "value": true
    }
}
```

Supported fields (all present in `game_features` after matrix build):
- `div_game` — boolean, divisional game flag from `curated.games`
- `week` — integer, NFL week number

### No other files need to change

`walk_forward.py` and `bq_writer.py` receive the already-filtered `game_features` and are unaware of the filter. No schema changes needed.

---

## Part B — Experiments to Run

Run these two experiments in order. Do not run both simultaneously — if sit_div fails the gate, the result informs how to interpret sit_late.

### Experiment 1: sit_div — Divisional Games Only

**Hypothesis:** OL matchup features carry more signal in divisional games where teams know each other well and game plans are more OL-focused.

**Universe filter:**
```json
"game_universe": {"field": "div_game", "operator": "eq", "value": true}
```

**Expected sample size:** ~90 divisional games/season × 6 test folds ≈ 540 total test games. Well above the 250-game gate minimum.

**Feature set:** v2 feature set (23 curated per-team features). Same as the baseline experiment (run_id `20260517_020202_0504ff`).

**Methodology:**
```json
{
    "start_season": 2015,
    "end_season": 2025,
    "train_seasons": 4,
    "test_seasons": 1,
    "random_seed": 42,
    "game_universe": {"field": "div_game", "operator": "eq", "value": true}
}
```

**Gate:** 54% hit rate on ≥250 games across all folds combined.

**What to look for:** Not just the overall hit rate — log the per-fold hit rates. Consistent signal (≥4/6 folds near or above 54%) is more meaningful than one outlier fold pulling up the average.

---

### Experiment 2: sit_late — Late-Season Games (Weeks 15–18)

**Hypothesis:** In Weeks 15–18, playoff positioning creates motivation asymmetries (teams resting starters, teams fighting for seeds) that the OL feature set partially captures through roster continuity proxies.

**Universe filter:**
```json
"game_universe": {"field": "week", "operator": "gte", "value": 15}
```

**Expected sample size:** ~64 games/season × 6 test folds ≈ 384 total test games. Above the 250-game minimum, but closer to the boundary — note this in the run log.

**Feature set:** v2 feature set (23 curated per-team features). Same feature set as sit_div.

**Methodology:**
```json
{
    "start_season": 2015,
    "end_season": 2025,
    "train_seasons": 4,
    "test_seasons": 1,
    "random_seed": 42,
    "game_universe": {"field": "week", "operator": "gte", "value": 15}
}
```

**Gate:** 54% hit rate on ≥250 games. If total test games are below 250, note in the results — the gate cannot be formally cleared but the hit rate is still informative.

---

## Part C — Reporting

For each experiment, report:

1. Overall hit rate (W-L-P, total games)
2. Per-fold hit rate table (same format as Track 1 Tier 1)
3. Total test game count — flag if below 250
4. Top 5 features by importance
5. Whether the gate is formally met or not

Update `PHASE4_STATUS.md` Track 5 with results as each experiment completes.

If either experiment clears 54% with ≥4/6 folds consistent, file a Tier 2 plan with PROJECT-LEAD before running further experiments. Do not expand the investigation unilaterally.

---

## Out of Scope

- Thursday-game filter (short week): ~15 games/season × 6 folds = ~90 total games. Below the minimum for any meaningful gate evaluation. Do not run this without PROJECT-LEAD sign-off.
- Combined filters (e.g., divisional + late-season): likely 20-30 games/season, too small. Do not run without sign-off.
- New features: this track uses the existing v2 feature set only. Feature additions are a separate workstream.
- Primetime filter: `gametime` is not in `curated.games`. Would require DATA-PIPELINE work. Deferred.
