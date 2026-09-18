# SESSION LOG — 2026-09-15 → 2026-09-17 (PROJECT-LEAD, Cowork)

**Covers:** the week-1 wrap-up, three defect fixes shipped, frontend tests and the
deploy gate, and the prior-season-blend sprint.
**Follows:** `SESSION-HANDOFF-2026-09-14.md`
**Blend sprint details:** `HANDOFF-2026-09-16-prior-season-blend.md` (written by
the Claude Code session) and ADR-013.

---

## Headline

**The sprint goal is done. Week-2 picks now use last season's data as well as
week 1.**

- The blend (N=8) went live on 2026-09-16 at 10:44 UTC, before week-2 TNF.
- Week 2 was regenerated on it straight away.
- Week-2 high-confidence picks went from 9 to 2.
- Week 3 onward uses the blend automatically.

---

## What shipped

| Commit | What | Status |
|---|---|---|
| `608a430` | DEFECT-2: spread sign shown in betting notation (`formatHomeSpread`). DEFECT-3: re-grade after regenerating predictions. `verify_label_convention.py` added. 17 `.pyc` files untracked. | Live |
| `611863f` | Fix for a JSX build error introduced in `608a430` (the first push never deployed) | Live |
| `6c962ac` | Vitest set up with 19 tests (spread sign, picked-side probability, GameCard render). `frontend-deploy.yml` now blocks the deploy unless `typecheck` and `npm test` pass. | Live; the gate passed on its first run |
| `dd09e17` | Dashboard warning when picks rest on fewer than 2 games of 2026 data | Live (later reworded for the blend) |
| `0e1ed14` | Prior-season blend: 22 `_blend` columns, 23 `_prev` columns plus `games_played_this_season`, N passed as a parameter, 19 unit tests. Production switched to the blend at N=8. | Live |
| `0accc22` | Handoff note for the blend go-live | — |

### Modeling image and job

| Date | Refresh job pinned to | Notes |
|---|---|---|
| 2026-09-15 | `sha256:269c67d5…` | DEFECT-3 fix |
| 2026-09-16 | `sha256:fff36d0…c24c6` | Blend. The job still runs `python backtests/run_production_refresh.py`. |

`nfl-experiment-runner` (the hypothesis-chat job) is still on an older image.
That was deliberate and needs a decision.

---

## Verified results (from the live API)

- **Week 1, 2026: 12–3–1 ATS.**
  - 15 graded; NE@SEA is a push and stays ungraded.
  - Probabilities and sides are unchanged through every regeneration since.
  - SF@LA and NE@SEA were regenerated after they were played (the DEFECT-3
    incident), so only 14 of the 16 are clean forward picks. On those the
    record is 11–3. (This session said 10–3 in chat, which was wrong: SF@LA
    was a win, so removing it and the push leaves 11–3.)
- **Label verifier**, all seasons: C1–C6 pass on 2,911 games. Favourites won
  66.3% outright, which confirms that positive `home_spread_close` means the
  home team is favoured.
- **Week-2 confidence tiers** (high / medium / low): 9 / 1 / 6 before the blend,
  2 / 7 / 7 after.

---

## The blend backtest (ADR-013)

- **Runs:** a fresh baseline plus N ∈ {2, 4, 6, 8}, walk-forward, test seasons
  2019–2025, run locally through `run_experiment.py`. All five exist as platform
  records. **No May-2026 run was used.** Matt considers every May run flawed and
  unreliable, so do not use them as comparisons or evidence.
- **Choosing N:** tuned on 2019–2022 using weeks 2–4 log loss. N=8 scored best,
  and it is the largest value tested.
- **Confirmation on 2023–2025 (N=8 vs baseline):**
  - Log loss, weeks 2–4: 0.6892 vs 0.7300.
  - Log loss, all weeks: 0.7351 vs 0.7479.
  - The bar Matt set in advance was met on both.
- **Context, recorded as results and not as go-live conditions:**
  - A constant 0.5 prediction scores 0.6931.
  - Over all weeks, both models score worse than that constant.
  - 2023 weeks 2–4 got worse under N=8.

---

## Decisions made by Matt this session

1. **Blend approach:** blended stats go live; separate prior-season stats become
   selectable features.
2. **Scope:** all team stats. N is chosen by backtest from {2, 4, 6, 8}.
3. **Go-live bar:** log loss in weeks 2–4 lower than baseline AND overall log
   loss not higher. ATS is context only.
4. **Deadline and fallback:** live before week-2 TNF; if not, keep the picks and
   show a warning.
5. **May runs:** never used as comparisons.
6. **Focus:** model-quality findings (calibration, beating a coin flip) are
   later platform work. They do not block app fixes. The project is app-first.

---

## Traps found this session

- **Build error from an unchecked edit:** `608a430` shipped a JSX syntax error
  because the build wasn't run before pushing. The frontend deploy gate now
  catches this.
- **Instruction text pasted into cmd:** it created stray `STOP` and `paste`
  files, because cmd treats `>` as a redirect. Command blocks must contain
  runnable lines only.
- **Cowork can't reach the local folders:** Cowork `device_bash` cannot mount
  them because of the Windows update of 8 September. Terminals only allow
  click-level control. Use **Claude Code** for anything that has to run on
  Matt's machine.
- **"Generate predictions" is not safe after kickoff.** The refresh
  regenerates the week that still has unplayed games, which includes games
  already played. No lock exists. **Don't press it between the week's first
  kickoff and the end of that week's games.**
- **Picks changed between two runs on 2026-09-15** (22:08 NZ and 02:00 NZ):
  3 sides flipped. The likely cause is the full data rebuild at 23:00 NZ, but
  it was never confirmed. Run a determinism check (press the button twice with
  no data job in between, then compare).

---

## Outstanding — in order

### Live risks (next)

1. `require_api_key` fails open when `OWNER_API_KEY` is missing (trap 6).
2. `api-deploy.yml` shifts traffic to `LATEST`, not the smoke-tested revision
   (trap 8).
3. Terraform has drifted from the live setup (trap 7). The refresh job's digest
   pin, timeout and memory all differ. Reconcile before any `apply`.

### Handoff queue

- Wire `verify_label_convention.py` into the Tuesday pipeline.
- Grade on Monday's ingest, not Tuesday's refresh.
- Make backend tests run without GCP credentials. 29 backend tests fail
  already, before this session's changes.
- Run the backend tests in CI.
- Show the season ATS record on the dashboard. Week 1's result is not visible
  anywhere in the app.

### New platform gaps and defects from this session

- Lock predictions at kickoff, so neither the button nor the refresh can
  rewrite a played game's pick.
- Roof bug: `roof_dome` checks for `retractable`, but the data uses `closed` and
  `open`.
- Weather mismatch: training uses actual game-day weather, while predictions
  get the median temperature and zero wind.
- No calibration or null-model metrics in the platform, and no "must beat
  constant 0.5" check in thresholds.
- Confidence tiers have no evidence behind them. Their presentation is a DEC-C
  decision.
- Week 1's `generated_at` shows the latest run for every week, not per week.
- May-2026 experiments are still listed as completed. Delete them or mark them
  retired.
- Frontend has no build SHA (trap 3), and failed deploys raise no alert.
- `formatHomeSpread(null)` shows "PK" on the game detail page.
- Tracked junk files: `vite.config.ts.timestamp-*.mjs`, `procs*.txt`,
  `dist-new/`, `pipeline.log`, `test_output.txt`, old `build-deploy*` scripts.
- Decide whether `nfl-experiment-runner` moves to the new image.
- Follow-up experiment: N > 8, using 2026 as the unseen holdout.

### Retired framing (charter appendix)

- A-1: `success_threshold: 0.54` in `predict_upcoming.py`.
- A-2: the gate banner and the "Gate passed" stat card.
- A-3 to A-6 are unchanged.

### Paperwork

- `DELEGATIONS.md` is stale. It needs the HC-S6-FIX-2 ruling, the amended gate
  and this queue.
- ADRs still owed: DEC-C, `n_jobs=1` reproducibility, the spread sign
  convention.
