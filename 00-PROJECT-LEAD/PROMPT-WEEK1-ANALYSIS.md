# PROMPT-WEEK1-ANALYSIS — what the model weighted on each week-1 pick, the patterns across them, and how they relate to the market

Start in: C:\Users\OEM\OneDrive\Desktop\nfl-prediction-app
Written: 2026-09-18 by PROJECT-LEAD. Stage 2 of 4. Previous: `PROMPT-STAGE1-FINISH-EXPLANATIONS.md` (done, `HANDOFF-2026-09-18-stage1-finish.md`). Next: PROMPT-BATCH-RUNNER (not written yet).

## Matt's request
> I want to analyze the 16 week-1 picks to find out what the model was actually weighting on each game, and whether there's a consistent pattern across the picks that would point to a real edge over the market — not just a good win/loss record.

This stage is analysis only. It reads stored explanations, picks and market data. It builds no model and changes no production behaviour.

## Task
When this is done, Matt can read one report that says, for each of the 16 week-1 games, what the model weighted and why; what patterns repeat across the 16; how those patterns line up with the closing line; and a list of hypotheses the next stage can test on 2015–2025.

## Read first
- `00-PROJECT-LEAD/PROJECT-CHARTER.md`, and `STATE.md` (Decisions section)
- `00-PROJECT-LEAD/context/talking-to-matt.md`
- `00-PROJECT-LEAD/HANDOFF-2026-09-18-stage1-finish.md` — what explanations exist and how they're stored
- `02-MODELING/backtests/explanations.py`, `explanations_bq.py` (row format, pick-direction, family matchup)
- `03-BACKEND-API/app/queries/explanations.py` (how the API picks which explanation run to serve — use the same rule)
- `01-DATA-PIPELINE/scripts/snapshot_lines.py` (the line change-log and what "first seen" means)

## Data honesty rules for this report
- **Week 1's explanations are approximate** (`is_approximate = true`, max diff 0.037). Say so at the top of the report, once.
- **Three games disagree on side** — ATL@PIT, GB@MIN, NYJ@TEN: the approximate model leans the other way from the live pick. Report them, mark them, and keep them out of every "pushed toward the pick" statistic. Give those statistics both ways: 13 games, and all 16.
- **SF@LA and NE@SEA** were regenerated after kickoff (`clean_forward = false`). Mark them.
- Results are a column, never the headline. No claims about whether the model is good.
- May 2026 runs are never used.

## Build
`02-MODELING/backtests/analyze_week_explanations.py --season S --week N`, reusable for any week. Writes `02-MODELING/backtests/reports/week_analysis_<season>_wk<NN>.md` plus the CSVs behind each section.

### 1. Game by game (all 16)
Matchup, closing spread, pick (favourite/underdog, home/away), P(cover), result, the flags above, then:
- top 5 drivers: family, stat name, side, raw value, league percentile, contribution toward the pick;
- the family matchup view;
- share of total absolute contribution carried by the top 1 and top 3 families;
- the strongest interaction pair, if stored; say so plainly if not;
- any contribution from imputed values, weather or `roof_dome`, called out (both are known-buggy);
- a two-sentence plain-English "why", generated from the numbers by template, not free text.

### 2. Patterns across the games
- Mean absolute contribution by family, and how often each family pushed toward the picked side.
- Group the picks by their pick-direction contribution vectors (hierarchical clustering on cosine distance; with n=16 keep it simple and show the groups). Name each group by its dominant families.
- Recurring matchup shapes ("home OL advantage against a weak away pass rush", and so on) with the count of games in each.
- For each pattern: its games, picks and results.

### 3. Against the market
- Model P(cover) against the closing spread, per game.
- Where the model disagrees most with the market, and which families drive that disagreement.
- Favourite/underdog and line size: which families push toward underdogs, and behaviour around 3 and 7.
- Line movement from `raw_lines.line_snapshots`: first-seen against close, and whether the close moved toward or away from the pick. Snapshots only began 2026-09-09, so report what exists and state the limit.
- Moneylines: check which seasons of `raw_nflfastr.schedules` actually have `home_moneyline` / `away_moneyline` populated before using them. If 2026 is populated, show de-vigged market probability beside the model's. If not, say so and skip it.
- Per family, the correlation between its net contribution and the closing spread across the 16 games. A family tracking the spread is largely repeating the market; one that doesn't is where an edge would have to come from.

### 4. Hand-off list
End with numbered testable hypotheses, each phrased so the next stage can run it on 2015–2025 (for example: "picks where OL pass protection is the top driver and the model backs the underdog").

### 5. Also run it for week 2
Run the same script for week 2 (explanations there are exact) and write its report. Week 2's games are being played this weekend, so leave its results columns empty rather than filling them in.

## Scope
Allowed to change: `02-MODELING/backtests/analyze_week_explanations.py` and its tests, `02-MODELING/backtests/reports/**`.
Must not change: any other code, any BigQuery table, any job or schedule, stored picks or explanations.
Don't press "Generate predictions" and don't run `run_production_refresh.py`: week 2 is being played.

## Kill-switch
Stop, write to `00-PROJECT-LEAD/QUESTIONS.md`, and tell Matt if:
- fewer than 16 games in either week have explanations, or a game's contributions don't reconstruct its stored probability within 1e-4;
- the stored explanation run for a game disagrees with the served pick beyond the three known games;
- the analysis needs a change outside the allowed list.

## Acceptance (each line true or false)
- [ ] `reports/week_analysis_2026_wk01.md` exists and has a section for each of the 16 week-1 `game_id`s, and `week_analysis_2026_wk02.md` for all 16 week-2 games.
- [ ] The approximate caveat, the three side-mismatch games and the two after-kickoff games are each named in the report.
- [ ] Every "toward the pick" statistic is given on 13 games and on 16.
- [ ] Each game section lists 5 drivers with family, stat name, raw value, league percentile and signed contribution.
- [ ] The patterns section names each group, its games and its dominant families.
- [ ] The market section states which moneyline seasons are populated, and how many week-1 games have a first-seen line in `line_snapshots`.
- [ ] A per-family correlation table with the closing spread is present, for all 16 games.
- [ ] The report ends with at least 5 numbered testable hypotheses.
- [ ] The script runs for any (season, week) with stored explanations; tests cover the pick-direction sign and the side-mismatch exclusion. Test counts before and after given.

## Returns-with
Write `00-PROJECT-LEAD/HANDOFF-2026-09-<dd>-week1-analysis.md`: goal achieved yes/no (first line), commit SHA, report paths, the run IDs the explanations came from, test counts before and after, and the hypothesis list copied in full.
