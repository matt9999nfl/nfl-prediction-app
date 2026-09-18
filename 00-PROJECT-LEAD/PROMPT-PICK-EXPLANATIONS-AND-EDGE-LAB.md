# TASK PROMPT — Per-game pick explanations, the week-1 analysis, and testing on past results

**For:** a new Claude Code session on Matt's Windows PC, repo at
`C:\Users\OEM\OneDrive\Desktop\nfl-prediction-app`
**Written:** 2026-09-17 (NZ) by the PROJECT-LEAD session (Cowork)
**Priority:** top build priority for the platform.

You can run commands yourself. Do so. Matt wants you to run as much as possible
and hand him only the decisions.

---

## 0. What Matt wants (his words)

> I want to analyze the 16 week-1 picks to find out what the model was actually
> weighting on each game, and whether there's a consistent pattern across the
> picks that would point to a real edge over the market — not just a good
> win/loss record. The blocker: no per-game feature breakdown currently exists
> for those production picks, so that has to be built or approximated before the
> "why" question can be answered properly.
>
> I think we need to add extensive back testing and reverse experiments to find
> an edge. Why aren't we running as many tests as possible each week to find
> what data has the most effect and potential edges this season?

Three deliverables come out of that:

1. **Per-game explanations** — a permanent platform feature: every pick, live or
   backtest, stores what the model weighted and by how much.
2. **The week-1 analysis** — the 16 picks explained one by one, the patterns
   across them, and how those patterns relate to the market.
3. **Testing on past results at volume** — backtests with explanations,
   reverse experiments (ablation), market-aware tests, and a weekly suite that
   runs itself.

### Framing — read this twice

This is a **platform-building project**. Per-game explanations are a core part
of any prediction platform and this one has never had them; that was an
oversight and this task fixes it. **Do not frame this work, its reports or your
messages around how good or bad the current model is.** Report what the
explanations and tests show, neutrally, and let Matt draw conclusions. Don't add
caveats about luck or sample size unless Matt asks.

---

## 1. Read first

1. `00-PROJECT-LEAD/PROJECT-CHARTER.md` — work goes *through* the platform
   (ADR-011). No project-level 54% gate (ADR-006).
2. `00-PROJECT-LEAD/SESSION-LOG-2026-09-15-to-17.md` — especially "Traps found".
3. `docs/DECISIONS.md` ADR-013 — the prior-season blend (live, N=8) and the
   tuning/confirmation season split it used.
4. In full, before changing anything:
   - `02-MODELING/backtests/predict_upcoming.py`
   - `02-MODELING/backtests/run_production_refresh.py`
   - `02-MODELING/backtests/run_experiment.py`
   - `02-MODELING/backtests/walk_forward.py`
   - `02-MODELING/backtests/bq_writer.py`
   - `02-MODELING/backtests/create_blend_backtest_configs.py` (pattern for creating config rows)
   - `02-MODELING/models/ol_xgb.py`, `02-MODELING/models/xgb_v2.py`
   - `02-MODELING/features/ol_metrics.py`, `comprehensive.py`, `situational.py`
   - `01-DATA-PIPELINE/scripts/snapshot_lines.py`, `build_curated_games.py`
   - `03-BACKEND-API/app/queries/features.py` (feature catalog)

### Standing rulings (do not re-ask)

- **May-2026 runs are never used** as comparisons or evidence. Every
  comparison in this task uses runs made in this task (or the 2026-09-16 blend
  runs).
- `n_jobs=1` stays on every model. Reproducibility beats speed; parallelise
  across runs, never inside one.
- Existing feature columns never change meaning. New things are new columns.
- **Never rewrite a pick or explanation for a game that has kicked off.**
- "Generate predictions" is not pressed between a week's first kickoff and the
  end of that week's games.

### How Matt wants to be talked to

- **When Matt must act or decide, put that first**, in a fenced block, with the
  stop/check condition right next to it. Explanation after.
- **When a stage finishes, lead with whether its goal was achieved**
  ("explanations are live — every week-1 and week-2 pick has one"), then details.
- A hard STOP is its own message.
- Windows `cmd.exe` syntax for any command you hand him. Command blocks contain
  runnable lines only — no prose, no `>` characters (cmd treats `>` as a
  redirect; this created stray files on 09-15).
- Be concrete. Don't pad.

---

## 2. Where things stand today

- The production model is `OLXGBModelV2` (an `XGBClassifier` wrapped with a
  mean imputer + `StandardScaler`), target `home_covered` against the closing
  spread. Features: `PRODUCTION_FEATURE_LIST` (the blended team stats, home_ and
  away_ prefixed) + `GAME_CONTEXT_FEATURES` + `rest_differential`.
- `predict_upcoming.generate_predictions()` retrains on every completed game
  before the target week, predicts, and **discards the model**. The only
  explanation kept is the top-25 **global** gain importance in
  `backtest_runs.feature_importances`. Nothing per game exists anywhere.
- Picks live in `experiments.backtest_predictions` under
  `PRODUCTION_EXPERIMENT_ID = 00000000-0000-4000-8000-00000000f0re`.
- Week 1 2026: 16 picks. SF@LA and NE@SEA were regenerated after kickoff
  (DEFECT-3 incident). Keep them in the analysis, flagged
  `clean_forward = False`.
- Week 2 2026 picks are already made. TNF is Fri 18 Sep 12:15 NZ.
- The model does **not** see the market: `walk_forward.py` says "closing spread
  is the LABEL, not a feature".
- Market data available:
  - `curated.games`: `home_spread_close`, `total_close` (all seasons).
  - `raw_nflfastr.schedules`: nflverse also publishes `home_moneyline`,
    `away_moneyline`, `home_spread_odds`, `away_spread_odds` — **verify which
    seasons are populated** before relying on them.
  - `raw_lines.line_snapshots`: append-only line change-log, live since
    2026-09-09. "First seen" is the first line the pipeline captured, not the
    true market open (see the module docstring).
- Known feature bugs, still open: `roof_dome` checks for `retractable` but the
  data uses `closed`/`open`; training uses actual game-day weather while
  predictions get median temperature and zero wind. The explanations will make
  both visible — report their contribution where they appear. Testing the fixes is
  Stage 3.5.

---

## STAGE 1 — Per-game explanations (the platform feature)

### 1.1 Method: exact TreeSHAP from XGBoost itself

No new dependency. XGBoost computes exact per-row SHAP values natively:

```python
import xgboost as xgb
booster = model.model.get_booster()
dm = xgb.DMatrix(X_scaled)   # booster was fit on a numpy array, so no feature names;
                             # map columns back via model._feature_names (same order)
contribs = booster.predict(dm, pred_contribs=True)  # (n_games, n_features + 1); last col = bias
```

- Each row sums to the raw log-odds of P(home covers). **Assert this**
  (tolerance 1e-4) every time explanations are produced.
- Contributions are computed on the scaled/imputed matrix the booster saw.
  Store the **raw** (unscaled) value beside each one.
- Flag imputed inputs (`was_imputed = True`).
- Also compute **SHAP interaction values** (`pred_interactions=True`) for the
  week-1 slate and the backtest summaries only (not every live row — it's
  n_features² per game). This is what shows pairings like "home pass
  protection × away pass rush".

### 1.2 Build

1. **Refactor, don't fork.** `generate_predictions()` also returns the fitted
   model and the raw + scaled test matrices (a small dataclass, or private
   keys in `meta`). Existing callers and `test_predict_upcoming.py` keep
   passing unchanged.
2. **`explain(X_raw) -> DataFrame`** on `OLXGBModel` in `models/ol_xgb.py`, so
   every model in the registry that inherits it has it. Long format, one row
   per game × feature:
   `game_id, feature, side (home/away/game), family, raw_value,
   league_pctile, was_imputed, contribution_logodds, abs_rank`
   - **`family`** — one constant map in the repo, used everywhere. Suggested
     families: OL pass protection, OL run blocking, defence pass rush,
     defence run, coverage/defence other, QB, run game, form, record/margin,
     rest, weather, venue/context. Every feature in `PRODUCTION_FEATURE_LIST`,
     the base 23, the `_prev` columns and the context features must map, or a
     test fails.
   - **`league_pctile`** — percentile of the raw value across all 32 teams for
     that season-week.
   - **Matchup view** — per game, per family: home contribution, away
     contribution, and net. This is the view that reads as "the model liked
     KC's pass protection against BAL's pass rush".
   - **Pick-direction view** — every contribution re-signed so positive means
     "pushed toward the side the model picked".
3. **Storage.** New table `experiments.prediction_explanations`, partitioned by
   season, clustered by `experiment_id, week`. Columns: the long format above
   plus `run_id, experiment_id, model_name, feature_list_hash, blend_n,
   predicted_side, predicted_home_cover_prob, bias_logodds, created_at`.
   Add the DDL beside the existing experiments DDL. Add the table to
   `preflight()` in `predict_upcoming.py`.
4. **Live picks write explanations in the same run.**
   `predict_upcoming.py` (and so `run_production_refresh.py`) writes
   explanations alongside picks, delete-then-insert for the week exactly like
   `replace_week_predictions`, skipping any game that has kicked off.
5. **Backtests write explanations too.** `walk_forward.py` /
   `run_experiment.py` compute and store explanations for every test game of
   every fold, keyed to that experiment's `run_id`. Gate it behind a config flag
   defaulting to **on**.
6. **`explain_picks.py --season S --week N`** for picks made before this
   feature existed:
   - Retrain exactly as production did, re-predict, and compare with the
     stored probabilities.
   - **Reproduction guard — hard STOP if it fails.** If any game differs by
     more than 1e-6, write nothing and report the diffs to Matt. A mismatch
     means the data under the model has changed since the picks were made (the
     unexplained side flips of 09-15 are a live example), and the explanation
     would describe a model that never made those picks. Offer Matt the
     options: explain the stored picks with the nearest reproducible model
     (clearly labelled as approximate), or investigate the data change first.
   - On pass, store the explanations with `clean_forward` set per game.
7. **API.** `GET /api/v1/predictions/{game_id}/explanation` — top drivers,
   the matchup view, and the full feature list. Same auth as the other
   prediction endpoints.
8. **UI.** A "Why this pick" panel on the game detail page: top 5 drivers as a
   signed bar chart (toward pick / against pick), each with raw value and
   league percentile; the family matchup view underneath; imputed values
   marked. A compact "main driver" chip on each game card. Vitest tests; the
   frontend deploy gate must pass.
9. **Tests.** Contributions sum to log-odds; family map covers every feature;
   imputed flag set when input is NaN; reproduction guard refuses on a 1e-3
   perturbation; explanations are not rewritten for a kicked-off game.

### 1.3 Run

1. Build; all tests green.
2. `explain_picks.py --season 2026 --week 1`, then `--week 2`.
3. Deploy the modeling image, API and frontend the same way the 2026-09-16
   blend go-live did (see `HANDOFF-2026-09-16-prior-season-blend.md`), and pin
   the refresh job to the new digest. Hand Matt any command that needs his
   credentials, in the format above.
4. Confirm on the live app that week-1 and week-2 games show the panel.

**Stage 1 done means:** every 2026 pick (weeks 1, 2 and every future week) has a
stored explanation that sums to its probability, visible in the app, and every
new backtest stores explanations for its test games.

---

## STAGE 2 — The week-1 analysis (Matt's original question)

Script: `02-MODELING/backtests/analyze_week_explanations.py --season 2026 --week 1`
(reusable for any week). Reads only stored explanations + picks + market data.
Output: `02-MODELING/backtests/reports/week_analysis_2026_wk01.md` + CSVs, and
the same content on a "Week analysis" page in the app (Stage 4 builds the page;
the script's output feeds it).

### 2.1 Game by game (all 16)

For each game: matchup, spread, pick (favourite or underdog; home or away),
P(cover), result, `clean_forward`, then:

- top 5 drivers (family, side, raw value, league percentile, contribution
  toward the pick);
- the family matchup view;
- share of the total |contribution| carried by the top 1 and top 3 families
  (was the pick driven by one thing or many?);
- the strongest interaction pair;
- any contribution from imputed values, weather or `roof_dome` (known bug
  areas), called out;
- a two-sentence plain-English "why" generated from the numbers (template,
  not free text).

### 2.2 Patterns across the 16

- Mean |contribution| by family, and how often each family pushed toward the
  picked side.
- Cluster the 16 picks by their pick-direction contribution vectors
  (e.g. hierarchical clustering on cosine distance; with n=16 keep it simple
  and show the dendrogram / groups). Name each group by its dominant families.
- Recurring matchup shapes (e.g. "home OL advantage vs weak away pass rush"
  appearing in k of 16 games).
- For each pattern: its games, picks, and results. Present results as a
  column, not as the headline.

### 2.3 Against the market

This is the "real edge over the market" part.

- **Model vs line.** For each game: the model's P(cover) against the closing
  spread, and — where moneylines exist — the market-implied win probability
  (de-vigged) next to the model's view.
- **Where the model disagrees with the market most**, and which families drive
  that disagreement.
- **Favourite/underdog and line size.** Which families push the model toward
  underdogs vs favourites; behaviour around key numbers (3, 7).
- **Line movement.** From `raw_lines.line_snapshots`: first-seen line vs close
  for each week-1 game, and whether the close moved toward or away from the
  model's pick. (Snapshots began 09-09, the day before week 1, so movement
  will be small — report what is there.)
- **What the market already knows.** For each family, the correlation between
  its net contribution and the closing spread across the 16 games. A family
  that tracks the spread closely is mostly repeating the market; one that
  doesn't is where any edge would have to come from. Stage 3 runs the same
  measure on the full 2015–2025 backtest.

### 2.4 Hand-off into Stage 3

End the report with a list of **testable patterns** — each written as a
hypothesis the Stage 3 tools can run on 2015–2025 (e.g. "picks where OL pass
protection is the top driver and the model backs the underdog"). Stage 3's
first batch runs these.

---

## STAGE 3 — Testing on past results

### 3.1 Batch runner

`02-MODELING/backtests/run_grid.py --grid <file.yaml>`:

- Each grid cell → one `platform.experiment_configs` row, created the way
  `create_blend_backtest_configs.py` does it, then run through
  `run_experiment.py`. Records are indistinguishable from wizard-built
  experiments (ADR-011).
- Runs cells in parallel as separate processes locally, or as parallel
  executions of the experiment-runner Cloud Run job (`--remote`). Check which
  image `nfl-experiment-runner` is on and move it to the current modeling
  image as part of this stage — tell Matt before switching it.
- Each grid has a `name`, a `question` and a `baseline` cell. Results land in a
  grid summary table (`experiments.grid_results`: grid_id, cell, config_id,
  run_id, metrics) so a grid can be read as one thing.
- Idempotent: re-running a grid skips cells already completed with the same
  config hash.

Standard metrics for every cell, overall and per season, and for weeks 1, 2–4
and 5+: log loss, Brier score, ATS hit rate, number of games, and a seeded
bootstrap 95% interval on each cell's difference from its grid baseline.
Include constant-0.5 and market-implied (where available) as reference rows.

Default season split, same as ADR-013: tune on 2015–2022 folds, confirm on
2023–2025. 2026 forward results are reported separately as they accumulate.

### 3.2 Reverse experiments (the standing suite)

`grids/standing_suite.yaml`:

1. **Leave-one-family-out** — drop each family; measure the change against the
   full production feature set.
2. **One-family-only** — each family alone (+ venue/context).
3. **Add-one-family** — base context + each family, to see marginal value.
4. **Permutation importance** on stored backtest predictions — shuffle one
   feature/family at a time in the test matrix of each fold's fitted model;
   no retraining. Fast; run every week.
5. **Counterfactual swaps on live picks** — for the current week, replace each
   family's values with league average (or swap home and away values) and
   record how each pick's probability and side change. Stored per game, shown
   in the "Why this pick" panel as "what would flip this pick".
6. **Blend weight** — N ∈ {8, 10, 12, 16} (N > 8 was already queued).
7. **Home/away symmetry** — the model sees home_ and away_ versions of each
   stat separately; test a differenced version (home − away) per stat.

### 3.3 Market-aware experiments

`grids/market.yaml`:

1. Add `home_spread_close` and `total_close` as features.
2. Add market-implied win probability (moneylines, where populated).
3. Change the target: predict home margin (regression), derive
   edge = predicted margin − line, pick when |edge| exceeds a threshold;
   sweep the threshold.
4. Slice results by favourite/underdog, line size buckets, and key numbers.
5. Restrict to games where the model disagrees most with the market (top
   quartile of |model prob − market-implied prob|).

### 3.4 Pattern tests from the explanations

- For every backtest with stored explanations: results grouped by top-driver
  family, by explanation cluster (same method as 2.2, fit on training folds
  only), and by the Stage 2 testable patterns.
- Family-vs-market correlation from 2.3, on the full 2015–2025 backtest.
- These run as a grid (`grids/patterns.yaml`) reading stored explanations, so
  new patterns can be added as one YAML entry.

### 3.5 Bug-fix tests

Each as its own before/after grid, so the effect is isolated:

1. `roof_dome` fixed to use `closed`/`open`.
2. Prediction-time weather: use forecast (or a documented stand-in) at
   prediction time and the same definition in training.

Report results; don't switch production to either without Matt's go-ahead.

### 3.6 Weekly automation

- A weekly job runs after the Tuesday grade-and-predict refresh finishes:
  1. explanations for the new week's picks (already done in-line by Stage 1);
  2. `analyze_week_explanations.py` for the week just graded and the week just
     predicted;
  3. the standing suite's fast parts (permutation importance, counterfactual
     swaps) every week; the full retraining grids when the feature set or data
     has changed, or on Matt's request;
  4. any grids Matt has queued.
- Schedule it the same way the existing weekly refresh job is scheduled. Hand
  Matt any infra change before applying it.
- Queue: a `grids/queue/` folder (and later the hypothesis chat) — a grid file
  placed there runs on the next weekly cycle, or immediately with
  `run_grid.py --now`.

---

## STAGE 4 — Results in the app

- **Week analysis page** — Stage 2's report for any week: game cards with
  drivers, the patterns section, the market section.
- **Experiments leaderboard** — every grid, its cells, the standard metrics
  and intervals, reference rows, and a filter by family / grid / season split.
- **Feature family page** — for each family: its stored contribution over time
  (2015–2026), its leave-one-out / one-only / permutation results, and its
  market correlation.
- Frontend tests for each page; the deploy gate must pass.

---

## Order, stop points, and what to send Matt

| Step | Stop / check |
|---|---|
| Stage 1 build + tests | Tests green before any deploy |
| `explain_picks.py` weeks 1–2 | **STOP if the reproduction guard fails** — report diffs and options |
| Stage 1 deploy | Hand Matt credentialed commands first; confirm the panel on the live app |
| Stage 2 report, week 1 | Send Matt the report's summary: per-game drivers, patterns, market section |
| Stage 3 runner + standing suite | Tell Matt before moving `nfl-experiment-runner` to the new image |
| Stage 3 market, pattern, bug-fix grids | Report results; no production change without Matt |
| Stage 3 weekly job | Hand Matt any scheduler/infra change before applying |
| Stage 4 pages | Deploy gate must pass |

After each stage, update `00-PROJECT-LEAD/ROADMAP.md` and write an ADR for the
explanation method and table (next ADR number in `docs/DECISIONS.md`). At the
end, write `00-PROJECT-LEAD/HANDOFF-<date>-pick-explanations.md` in the same
style as the 2026-09-16 handoff.

## Done means

- Every pick, live and backtest, has a stored per-game explanation that sums to
  its probability, visible in the app.
- Matt has the week-1 analysis: what the model weighted on each of the 16
  games, the patterns across them, and how they relate to the market.
- Matt can run a batch of tests on 2015–2025 from one YAML file, and the
  standing reverse-experiment suite, market tests and pattern tests run weekly
  without him, with results on the leaderboard.
