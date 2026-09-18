# PROMPT-FIX-SPREAD-SIGN-AND-LINE-SNAPSHOTS — fix the inverted favourite/underdog labels in the week analysis, and find out why no line snapshots exist

Start in: C:\Users\OEM\OneDrive\Desktop\nfl-prediction-app
Written: 2026-09-18 by PROJECT-LEAD. Fix stage, between Stage 2 (`PROMPT-WEEK1-ANALYSIS.md`, done) and Stage 3a (PROMPT-BATCH-RUNNER, not written yet).

## Why this exists

PROJECT-LEAD reviewed `week_analysis_2026_wk01.md` against the live data and found the favourite/underdog labels inverted. `analyze_week_explanations.py` reads a positive `home_spread_close` as the home team being the underdog. It is the opposite: **positive means the home team is favoured** (`01-DATA-PIPELINE/scripts/verify_label_convention.py`, C1/C2).

Evidence, 2026 week 1, 15 graded games: re-deriving the ATS label as `margin > home_spread_close` matches the stored `home_covered` on 15 of 15. The other reading matches 13 of 15. Independently, `2026_01_ARI_LAC` has `home_spread_close = +9.5` and a de-vigged home moneyline of 0.787 (LAC heavily favoured), and the report calls ARI the favourite.

This is the fourth sign error near this column (INC-001, 2026-09-10, 2026-09-14, now this one). The fix is not just the sign: the script must derive the favourite from the data, and a test must fail if it ever flips again.

Second, unrelated but also market data: `raw_lines.line_snapshots` is empty. `run_pipeline.py` calls `snapshot()` inside step 1 on every run, in both `full` and `gameday` modes, and swallows failures as non-fatal. So either it has been failing on every run since 2026-09-09 or it never reached that line. Every day this stays broken loses line movement that cannot be recovered.

## Task
When this is done: the two week reports are correct about which team is favoured, a test makes that hard to break again, and Matt knows why no line snapshots exist and what it takes to fix it.

## Read first
- `01-DATA-PIPELINE/scripts/verify_label_convention.py` (the convention, and how it is proven from data)
- `02-MODELING/backtests/analyze_week_explanations.py` (`favorite`, `picked_is_favorite`, the underdog section)
- `01-DATA-PIPELINE/scripts/run_pipeline.py` `run_ingest_schedules()`, `scripts/snapshot_lines.py`, `scripts/run_pipeline_job.py`
- `00-PROJECT-LEAD/HANDOFF-2026-09-18-week1-analysis.md`

## Part A — the sign fix (do this first)
1. Fix the favourite/underdog derivation. Positive `home_spread_close` = home favoured. Check every place the script uses the spread's sign: `favorite`, `picked_is_favorite`, the underdog family table, the key-number section, the hypothesis text.
2. Tests: `home_spread_close = +9.5` makes the home team the favourite; a pick on the home side there is a pick on the favourite; and the ATS label re-derived as `margin > spread` agrees with the stored label on a fixture set. These must fail if the sign flips back.
3. Add a data-derived guard in the script itself: where moneylines exist for the week, the favourite from the spread and the favourite from the de-vigged moneyline must agree on at least 80% of games. Below that, the script exits non-zero and writes nothing.
4. The report says "Closing spread" but uses the spread stored with the pick, which is the line at pick time (`2026_01_ARI_LAC`: report +9.5, `curated.games` +8.5). Report both, labelled: "line at pick time" and "closing line", and use the closing line for the favourite/underdog and key-number sections.
5. Regenerate both reports (2026 weeks 1 and 2) and their CSVs.
6. Commit Part A, and push `80cd3b6` and this commit to `main`. (Nothing under `02-MODELING` triggers a deploy.)

## Part B — the line snapshots
1. Find out what has happened: read the logs of the last few `nfl-pipeline-full` and `nfl-pipeline-gameday` executions for "Line snapshot", "SNAPSHOT_FAILED" and the step summary line. Report the actual error, or the fact that the step never ran.
2. Check `raw_lines.line_snapshots` exists at all, its row count, and whether the dataset or table was ever created.
3. If the cause is a code bug in `snapshot_lines.py` or its caller, fix it, with a test. Don't change the pipeline's step order or its scheduling.
4. Run one snapshot manually against the current slate, from the production Linux image, so this week's lines are captured before they move further. Report the row count inserted.
5. Make the failure visible: a snapshot failure must show up in the pipeline's validation output, not only in the logs. A silent failure that only a person reading logs can find is the same pattern as HC-S6-F6.

## Scope
Allowed to change: `02-MODELING/backtests/analyze_week_explanations.py` and its tests, `02-MODELING/backtests/reports/**`, `01-DATA-PIPELINE/scripts/snapshot_lines.py` and its tests, and the validation output that reports the snapshot step.
Must not change: the ATS label or anything that writes `home_covered`, the pipeline's step order or schedules, stored picks or explanations, any Cloud Run job or image.

## Kill-switch
Stop, write to `00-PROJECT-LEAD/QUESTIONS.md`, and tell Matt if:
- the fix would touch `derive_home_covered()` or anything that writes `home_covered`;
- the moneyline guard fails after the fix (that would mean the convention is not what this prompt says);
- fixing the snapshots needs a pipeline redeploy, a schedule change or an IAM change;
- the snapshot failure turns out to affect other pipeline steps.

## Acceptance (each line true or false)
- [ ] In `week_analysis_2026_wk01.md`, `2026_01_ARI_LAC` shows LAC as the favourite, and the underdog-pick count is recomputed.
- [ ] Every game's favourite in both reports agrees with the de-vigged moneyline favourite, or the disagreements are listed by name with their numbers.
- [ ] Tests exist that fail if the sign flips back. Test counts before and after given.
- [ ] Both reports carry the line at pick time and the closing line, labelled, with the favourite/underdog and key-number sections using the closing line.
- [ ] The hypothesis list is regenerated, with any underdog/favourite wording corrected.
- [ ] `80cd3b6` and the Part A commit are pushed to `main`.
- [ ] The handoff states the actual reason `line_snapshots` is empty, quoting the log line or the error.
- [ ] Either snapshots now insert rows (give the count and the executed command), or the handoff says exactly what change would be needed and why it wasn't made.
- [ ] A snapshot failure appears in the pipeline's validation output (test or run output quoted).

## Returns-with
Write `00-PROJECT-LEAD/HANDOFF-2026-09-<dd>-spread-sign-and-snapshots.md`: goal achieved yes/no (first line), commit SHAs, what the favourite/underdog numbers were before and after, the snapshot root cause with evidence, rows inserted, test counts before and after, anything left open.
