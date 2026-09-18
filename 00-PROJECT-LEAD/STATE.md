# STATE — 2026-09-17 (NZ)

The only work board for PROJECT-LEAD. Overwritten at each handoff (old copies go to `archive/`). First written 2026-09-17 from `SESSION-LOG-2026-09-15-to-17.md`, `HANDOFF-2026-09-16-prior-season-blend.md` and Matt's 09-17 chat.

## Current state

Verified 2026-09-17 ~10:00 UTC against the live API, the live site in Chrome and git on Matt's PC:

| | State |
|---|---|
| API | Live, `/health` commit `224a424` |
| Frontend | Live, bundle `index-CiXuYERa.js`. Panel, chip, live-pick heading and the side-mismatch warning checked in the browser 2026-09-18 |
| Explanations | All 32 week-1/week-2 games. `live_predicted_side` matches the served pick on all 32 (checked 2026-09-18). No null percentiles among team-side top drivers. Week 2 exact; week 1 approximate (max diff 0.037) |
| Week 2 2026 picks | Live, `generated_at` 2026-09-16T10:44:14Z, blend N=8 |

From `HANDOFF-2026-09-17-pick-explanations.md` (not re-checked, needs gcloud):

- Production refresh job image: `nfl-experiment-runner@sha256:219c721…5739b`, built from `cb9ad34`. The build also picked up uncommitted local files in `02-MODELING`; the handoff says the Python code is unaffected. It has not run yet; its first scheduled run is Tue 22 Sep 14:00 UTC, and that run is the first test of explanations written in the same run as picks.
- `nfl-experiment-runner` (hypothesis-chat job) is still on an older image. Matt hasn't decided whether to move it.
- Week 1 2026: 12–3 ATS on 15 graded games (NE@SEA push). SF@LA and NE@SEA were regenerated after kickoff, so 14 of 16 are clean forward picks.
- Hypothesis chat UI and backend: live since ~2026-09-06.

Scheduled jobs (UTC): Mon 05:00 gameday-sunday ingest · Tue 07:00 gameday-monday ingest · Tue 11:00 full rebuild · Tue 14:00 production refresh (grade + predict) · Fri 05:00 gameday-thursday ingest.

Tooling: Cowork can read and write `00-PROJECT-LEAD` on Matt's PC and reach the live API (verified 2026-09-17). Other repo folders aren't connected to Cowork. The 09-15 note saying Cowork can't reach local folders is out of date. Code changes run in Claude Code on Matt's PC.

## Decisions (standing rulings — don't re-ask)

- 2026-09-10: This is a platform-building project. The offensive-line hypothesis is one finished experiment, not the premise. No project-level 54% gate (ADR-005, ADR-006).
- 2026-09-15: May 2026 experiment runs are flawed and are never used as comparisons or evidence.
- 2026-09-15: Chose a fresh production model trained on 2015–2025 over reusing a May config.
- 2026-09-16: Prior-season blend (N=8) is live (ADR-013). Go-live bar: lower log loss in weeks 2–4 and no worse overall; ATS for context only.
- 2026-09-16: Model-quality findings (calibration, beating a flat 50% guess) are later platform work, not blockers to app fixes.
- 2026-09-17: Per-game explanations are the top build priority. Finding an edge is active work, done through the platform: many backtests and reverse experiments every week.
- 2026-09-17: Don't comment on current model performance unless Matt asks. Don't add luck or sample-size caveats unless Matt asks.
- 2026-09-17: Runs whose numbers must match production or count as evidence run in the production Linux image, not on Windows (added to `CLAUDE.md`).
- 2026-09-17: If an approximate explanation leans the other way from the live pick, the panel names the live pick and shows a warning. Chose this over hiding the panel.
- 2026-09-17: Try BigQuery time travel to recover the pre-09-15 curated tables for exact week-1 explanations. Exact rows are appended; existing explanation rows are never deleted.
- 2026-09-17: Move `nfl-experiment-runner` to the current modeling image (in `PROMPT-STAGE1-FINISH-EXPLANATIONS.md`).
- 2026-09-17: One prompt per stage from now on. Order: Stage 1 finish, then week-1 analysis, then batch runner and standing suite, then market/pattern/bug-fix grids, then the weekly job, then the results pages.
- Standing: `n_jobs=1` on every model. Existing feature columns never change meaning. Never rewrite a pick for a game that has kicked off. Don't press "Generate predictions" between a week's first kickoff and the end of that week's games.

## Open items

### Matt's current priority

1. **Per-game explanations and testing on past results.** Prompt: `PROMPT-PICK-EXPLANATIONS-AND-EDGE-LAB.md` (written 2026-09-17, four stages in one prompt). Matt's checklist:
   1. Explain what the model weighted on each of the 16 week-1 picks.
   2. Find patterns across the picks and how they relate to the market.
   3. Build per-game explanations as a permanent platform feature.
   4. Run extensive backtests and reverse experiments on past results.
   5. Run tests every week this season to find which data matters and where an edge might be.
   - Stage 1 complete and verified (2026-09-18): commits `cb9ad34`, `3b38a6f`, `224a424`; both Cloud Run jobs on one digest built from `224a424`; backtests store explanations; every run records its environment; pre-09-15 `curated` tables saved in `scratch_timetravel`, and 2015–2025 data is confirmed unchanged by the rebuild.
   - Stage 2 (week analysis) done and fixed. Commits `80cd3b6` and `8167091`, both pushed. Reports: `02-MODELING/backtests/reports/week_analysis_2026_wk0{1,2}.md` + CSVs.
   - Spread-sign inversion fixed and verified 2026-09-18: `2026_01_ARI_LAC` now shows LAC as favourite; reports carry the line at pick time and the closing line separately; a moneyline-agreement guard (80%) and tests guard the sign. Week 2's underdog count went 12 → 4 of 16; week 1 stayed 8 of 16. Modeling tests 239 → 251.
   - Line capture: root cause found — the deployed `nfl-data-pipeline:latest` image was built 2026-09-08, before `snapshot_lines.py` existed, so no scheduled run ever captured a line. A manual catch-up capture on 2026-09-18 wrote 3,300 rows. A freshness check now shows the failure in the validation report. **The image rebuild is still to do**: `PROMPT-DEPLOY-DATA-PIPELINE.md`.
   - Week 1 still can't be reproduced exactly. Untested hypothesis: the stored week-1 picks came from image `269c67d`, built before `0e1ed14` rewrote the feature builders. Reproducing with that older code against `scratch_timetravel` is the test. No deadline; the data is saved.
   - Cosmetic: the panel writes "91th/53th pctile"; `home_pass_explosive_rate` is filed under the QB family.

### Waiting on Matt

(nothing)

### Background list (not the agenda — see `context/handling-requests.md`)

Raise only if Matt asks or one blocks his request.

- Deploy risk (raised 2026-09-18): Terraform still declares `:latest` for every job and service, so an `apply` would undo the digest pins just set on both modeling jobs. Both data-pipeline jobs still run `:latest` (DP-R-13, unfixed).
- Security/deploy: `require_api_key` fails open without `OWNER_API_KEY`; `api-deploy.yml` shifts traffic to `LATEST`, not the tested revision; Terraform has drifted from live (refresh job digest, timeout, memory).
- Pipeline/tests: wire `verify_label_convention.py` into the Tuesday pipeline; grade on Monday's ingest; backend tests runnable without GCP credentials (29 already fail); backend tests in CI.
- App: season ATS record on the dashboard; lock predictions at kickoff; week `generated_at` is per-experiment, not per-week; `formatHomeSpread(null)` shows "PK"; frontend has no build SHA and failed deploys raise no alert; `def_qb_hit_rate` missing from the API feature catalog.
- Features: `roof_dome` checks `retractable` but data uses `closed`/`open`; training uses game-day weather, predictions use median temperature and zero wind (both covered by the active prompt's Stage 3.5).
- Platform: runs do not record the image digest or package versions that produced them (found 2026-09-17 while chasing the week-1/2 reproduction gap).
- Platform: no calibration or flat-50% reference metrics; confidence tiers have no evidence behind them (DEC-C); May 2026 experiments still listed as completed (retire them); determinism check for the 09-15 side flips.
- Retired framing still in code: `predict_upcoming.py` writes `success_threshold: 0.54` on every run (charter A-1); dashboard "Gate passed" card (A-2); A-3 to A-6 in the charter appendix.
- Unfinished agent tasks from 2026-09-09 (checked against code 2026-09-17): BACKEND-API HC-S6-FIX-2 not landed (no dispatched-status guard in `set_approved_hash`, flat 272 games/season, `approval_hash` still optional; F7 was called a live defect in the hypothesis chat); TESTING-QA HC-S6-CLEANUP not done (8 `xfail` markers remain; blocked on HC-S6-FIX-2); DEVOPS DO-HARDEN only partly done (`/health` commit fixed in `b95295d`; alerts, freshness check and `INCIDENTS.md` not done); DATA-PIPELINE DP-REVIEW done, but its DP-R-01..13 follow-ups aren't tracked anywhere.
- Agent instructions: all six rewritten 2026-09-17 (old versions in each folder's `archive/`). Root `CLAUDE.md` added, so Claude Code sessions load the standing rules automatically. Root `README.md` rewritten to match the charter.
- Repo: tracked junk files (`vite.config.ts.timestamp-*.mjs`, `procs*.txt`, `dist-new/`, `pipeline.log`, `test_output.txt`, old `build-deploy*` scripts).
- Paperwork: ADRs owed for DEC-C, `n_jobs=1` reproducibility, the spread sign convention. `ROADMAP.md` is stale.
- Follow-up experiment: blend N > 8 with 2026 as holdout (included in the active prompt's standing suite).

## Next action

1. `PROMPT-DEPLOY-DATA-PIPELINE.md` — rebuild and repoint the pipeline jobs, in a gap between scheduled runs, so line capture runs from now on.
2. `PROMPT-BATCH-RUNNER.md` — Stage 3a: `run_grid.py` and the standing reverse-experiment suite, run remote on 2015–2025.
3. Wed 23 Sep: check that week 3's picks from the Tue 22 Sep 14:00 UTC refresh came with explanations, and that the Tue 11:00 UTC rebuild captured line snapshots.

Then: PROMPT-MARKET-AND-PATTERN-GRIDS (the week-1 hypotheses and the market tests), the weekly job, and the results pages.

## Resume prompt

```
Read 00-PROJECT-LEAD/instructions.md, then STATE.md, and pick up from Next action.
```
