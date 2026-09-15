# SESSION HANDOFF — 2026-09-14

**For:** a cold PROJECT-LEAD session
**From:** PROJECT-LEAD session of 2026-09-10 → 2026-09-14
**Covers:** the 2026 week-1 slate, three production defects found and fixed, and the ordered queue that follows
**Paste this whole file as your opening prompt, or point at it from the repo.**

---

## 0. Who you are and what this project is

You are **PROJECT-LEAD** on Matt's NFL prediction app (GCP project `nfl-model-471509`,
repo `matt9999nfl/nfl-prediction-app`, local at
`C:\Users\OEM\OneDrive\Desktop\nfl-prediction-app`).

**Read `00-PROJECT-LEAD/PROJECT-CHARTER.md` before anything else.** The one-line
version:

> **This is an app-building project.** The deliverable is a platform for running
> endless experiments on NFL data. Modelling happens later, *through* the
> platform, during and after the 2026 season.

It is **not** a project about proving that markets undervalue offensive-line
performance. That was the starting hypothesis in early 2026, it was tested, it
failed, and **ADR-005** retired the framing on 2026-05-03. **ADR-006** retired the
project-level ≥54% ATS gate on the same day. Both are still quietly encoded in
places — the charter's appendix inventories them as A-1…A-6. If you find OL-hypothesis
framing or a 54% project gate anywhere, treat it as a defect and log it.

When proposing work, state which **platform capability** it creates or protects.
"Does this make the model more accurate?" is the wrong question right now.

### How Matt wants to be talked to

**Commands and instructions he must act on go FIRST, in a fenced block, with the
stop/check condition immediately adjacent.** Explanation goes after the action,
never before.

He is on **Windows** — give `cmd.exe` syntax (`findstr`, not `grep`; backticks are
literal in cmd but escape characters in PowerShell). He is a self-taught, AI-first
developer running this solo alongside a demanding job; be concrete and don't pad.

**A hard STOP must be its own step.** On 2026-09-14 a gating query returned a STOP
value and he read straight past it, because the condition was a comment line inside
a seven-step block and scrolled by in the terminal output. Give gating checks alone
and wait for the answer.

---

## 1. Verified state — 2026-09-14 ~04:20 UTC

Checked against the live service, not taken from documents. Re-verify rather than
trusting this file if more than a day has passed.

| | State | How to re-check |
|---|---|---|
| API | Live, `commit: 3cbf12f` | `curl -s https://nfl-backend-api-rmaehdhzhq-uc.a.run.app/health` |
| Frontend | Live, bundle `index-q7hXLH7x.js` | `curl -s http://34.49.20.115/ \| findstr /C:"assets/index-"` |
| Week-1 predictions | Live, 16 games, `gate_passed: false` | `/api/v1/predictions?season=2026&week=1` |
| Week-1 grading | **0/16 graded** — see §2 | same endpoint, check `correct` |
| Week-1 results | **2 of 16 games ingested** | `/api/v1/games?season=2026&week=1&limit=50` |
| Hypothesis chat backend | **Live** — all 8 `/api/v1/scoping/*` endpoints, auth-gated (401 anon) | `/openapi.json` |
| Hypothesis chat UI | **Live** at `/experiments/hypothesis` | it has been live since ~2026-09-06 |

### The scheduled jobs (all UTC)

| Job | Schedule | Purpose |
|---|---|---|
| `nfl-pipeline-gameday-sunday` | Mon 05:00 | ingest Sunday's results |
| `nfl-pipeline-gameday-monday` | Tue 07:00 | ingest MNF |
| `nfl-pipeline-full-weekly` | Tue 11:00 | full rebuild |
| `nfl-production-refresh-weekly` | Tue 14:00 | grade finished weeks, predict the next |
| `nfl-pipeline-gameday-thursday` | Fri 05:00 | ingest TNF |

At the time of writing, Monday 05:00 had not yet fired — which is why only the two
Thursday games had scores. **That was the schedule working, not a fault.** Confirm
before treating missing scores as a defect.

---

## 2. What happened in week 1

**The platform produced, served and displayed live forward predictions for a real
NFL week for the first time.** That milestone is real and worth recording.

Three defects were found during and after the slate. All three are **fixed in
source and committed**; see §3 for what is and is not deployed.

### DEFECT-1 — confidence percentage showed the wrong side *(fixed, deployed)*
`predicted_home_cover_prob` is always the **home** team's probability, but the game
card printed it beside whichever team was picked. An away pick showed the home
team's number — "WAS (33%)" for a game the model gave WAS a 67% chance, sitting next
to a correctly-computed "High confidence" badge. Affected the 10 of 16 games that
were away picks. Fixed in `GameCard.tsx`; deployed 2026-09-10.

### DEFECT-2 — spread sign inverted on every game *(fixed, NOT yet deployed)*
Two opposite conventions, no translation between them:

- nflverse `spread_line` — **positive means the home team is FAVOURED**
- betting notation — **negative means favoured** ("PHI -6.0")

`formatSpread()` printed the raw value, so the UI showed `PHI +6.0` for a game PHI
were favoured to win by six. **All 16 week-1 games displayed the favourite as the
underdog and vice versa.**

The data is correct and so is `derive_home_covered()` — display only. Proven
empirically: `2026_01_NE_SEA` finished SEA 13–10, margin exactly **+3** against a
`home_spread_close` of **+3.0**, and `home_covered` is **NULL** — a push. A push
requires margin == spread, which holds only under the positive-means-home-favoured
reading.

Fixed by a new `formatHomeSpread()` in `04-FRONTEND/src/lib/formatters.ts`, used in
`GameCard.tsx` and `GameDetailPage.tsx`. `formatSpread` was deliberately left alone —
silently changing a generic formatter's meaning is how this class of bug happens.

### DEFECT-3 — regenerating predictions silently erased grading *(fixed, NOT deployed)*
`replace_week_predictions()` deletes the week's rows and re-inserts with
`correct = NULL`. It was written to be idempotent for re-runs *before* kickoff; after
a game completes it is destructive.

Matt pressed the dashboard's **"Generate predictions"** button on Sunday
2026-09-13 21:51 NZ, after the Thursday opener had finished. `2026_01_SF_LA` — the
model's first ever graded forward pick, **and a correct one** — came back with
`actual_home_covered: false` and `correct: null`. The running record reset and
nothing said so.

Fixed by calling `grade_completed()` immediately after `replace_week_predictions()`
in both `predict_upcoming.py` and `run_production_refresh.py`, re-deriving from
`curated.games` rather than carrying old values forward. A warning now logs how many
graded rows are about to be overwritten, so a failed re-grade is visible.

### New tooling — `01-DATA-PIPELINE/scripts/verify_label_convention.py`
Six checks (C1–C6) over `curated.games`, exits non-zero on failure so it can gate CI.
**Validated adversarially** — on 400 synthetic games it passes clean data, and on an
inverted sign convention C1 fails at 32.1% (favourites should win ~66–70%), while an
INC-001-shaped label flip fails C2 at 389/400.

**C1 is the one that matters**: it decides the sign convention from outright results
alone, with no document to read. Every previous time this question came up it was
answered by reading a comment, and one of those comments was wrong.

---

## 3. Actions outstanding — Matt must run these

```
STEP 1 — GATE. Nothing else until this passes.
Confirm Sunday's results ingested (job fires Mon 05:00 UTC):

  curl -s "https://nfl-backend-api-rmaehdhzhq-uc.a.run.app/api/v1/games?season=2026&week=1&limit=50" | findstr /C:"home_score"

  14+ games with real scores -> continue to STEP 2
  still only 2 games        -> STOP. Sunday ingest failed silently. Investigate
                               before anything else; this is the failure mode
                               DP-R-02 describes, where a skipped season generates
                               no check and the pipeline reports ALL CHECKS PASSED.
```

```
STEP 2 — repair the lost grade, then verify the data layer

  cd C:\Users\OEM\OneDrive\Desktop\nfl-prediction-app\02-MODELING
  python backtests\predict_upcoming.py --season 2026 --week 1 --grade

  cd C:\Users\OEM\OneDrive\Desktop\nfl-prediction-app\01-DATA-PIPELINE
  python scripts\verify_label_convention.py --season 2026 --week 1
  python scripts\verify_label_convention.py

  The second run covers 2015-2026 (~2,900 games) and is the real test.
  ANY [FAIL] -> STOP, report the output, do not push.
```

```
STEP 3 — ship the UI fix

  cd C:\Users\OEM\OneDrive\Desktop\nfl-prediction-app
  git add -A
  git commit -m "fix: correct home spread sign convention in UI; preserve grading on prediction re-runs; add label convention verifier"
  git push

  Wait for Actions green, then:
  curl -s http://34.49.20.115/ | findstr /C:"assets/index-"

  hash changed from index-q7hXLH7x.js -> good. Ctrl+F5, confirm NO @ DET shows DET -7.0
  hash unchanged after green          -> STOP. CDN cache, not a build failure.
```

```
STEP 4 — rebuild the modeling image (not urgent, this week is fine)

  cd C:\Users\OEM\OneDrive\Desktop\nfl-prediction-app\02-MODELING
  gcloud builds submit --config cloudbuild.yaml .
  gcloud run jobs update nfl-production-refresh --image gcr.io/nfl-model-471509/nfl-experiment-runner:latest --region us-central1

  Why not urgent: Tuesday's refresh grades week 1 then predicts week 2, so it calls
  replace_week_predictions on week 2 only. Week 1's grades are not at risk. DEFECT-3
  bites on manual regeneration and forced re-runs.
```

---

## 4. The queue, in order

Ordered by what unblocks what and by damage-prevented per hour. **The argument for
this ordering: six days produced six defects, and a human eye caught every one.
Nothing was caught by CI, a test, or an alert. That is the thing to fix.**

### Now — small, cheap, aimed at bugs that actually happened

1. **Frontend unit tests.** There is no vitest, no jest, no testing-library. Both
   defects Matt found by eye were in **pure functions** — `formatHomeSpread` and the
   GameCard pick/probability logic. One test file with ~10 assertions catches both
   permanently. Highest value-per-hour on the board.
2. **Wire `verify_label_convention.py` into the Tuesday pipeline job.** Written,
   tested, exits non-zero. It currently has nowhere to run — which is the whole
   problem in one sentence.
3. **Grade on Monday's ingest, not Tuesday's refresh.** Closes the ~33-hour window
   where the dashboard shows final scores beside ungraded picks.
4. **Rebuild the modeling image** (STEP 4 above) so DEFECT-3's fix is actually live.

### Next — the structural fix

5. **Backend tests runnable without GCP credentials.** They 500 on
   `DefaultCredentialsError` because `get_bq_client` resolves before request
   validation, so even a test asserting a 422 fails. **This gates item 6** and is the
   single highest-leverage structural item.
6. **CI runs the test suite.** 91 backend tests have never gated a deploy. Three
   display defects shipped past green pipelines in six days.

### Then — the feature worth having

7. **The season ATS record on the dashboard.** Nothing in the app currently shows how
   the model is doing. The three stat cards are "Scheduled games", "Completed
   experiments", and "Gate passed: None yet". After grading, Matt has a real 2026 ATS
   record and nowhere to see it.

   Three reasons this is the right next feature, not self-indulgence:
   - It is the honest measurement the platform exists to produce, and the first
     output about 2026 rather than closed seasons.
   - It replaces "Gate passed: None yet" — charter item A-2, the retired 54% gate
     rendered as a headline stat to every visitor.
   - It closes the loop. "Is the model any good?" becomes answerable by looking,
     every Tuesday, instead of only by running a backtest.

   Data is already in `experiments.backtest_predictions` with `correct` populated.
   It is a query and a card.

### Deliberately deferred

- **AI features / sandboxed chat agent in the platform.** Matt wants this and it is
  a good direction. See §6 for the design constraint that must hold.
- **Market data (spread / total / moneyline) as selectable features.** Real
  capability gap, on the roadmap. `raw_lines.line_snapshots` already captures the
  data including the moneylines previously discarded.
- **Prior-season lagged features.** A real gap, discovered the correct way — see §5.

Both of the last two add surface area to a system that cannot yet catch its own
regressions. Do them after CI works.

---

## 5. The hypothesis chat — used once, for real

**Correction to earlier reporting:** this feature was described in the sprint board
as undeployed and untested. **Both were wrong.** The UI has been live at
`/experiments/hypothesis` since ~2026-09-06 and Matt took a real hypothesis through
it end to end on 2026-09-09.

- Session `338c6866-4a93-422b-81b6-7d8375add71c`, approved 11:11, dispatched.
- Experiment `eb7a8d37-e7d4-417d-8558-b858b3f2e3af`, run completed.
- Result: **47.65% ATS over 1,828 games.** Feature importances near-uniform (top
  0.0428 against a 26-feature baseline of 0.0385) — `div_game` and `rest_differential`
  rank as high as the rushing metrics the hypothesis was about. A clean null.

### RULING — Q5(b), HC-S6-FIX-2 may proceed

The gate in `DELEGATIONS.md` said *"zero stored approvals → proceed; non-zero → the
ruling is void."* The count is **1**, but the gate asked the wrong question. What
matters is whether an approval is **pending dispatch**. This one has `experiment_id`
populated and a completed run — it is terminal, so the `config_hash` → `approval_hash`
rename cannot break it.

- **BACKEND-API is unblocked. Land HC-S6-FIX-2.**
- **Do not delete the session** — it is the first real run and it is the record.
- **Amend the gate** to: *"any session with `status = approved` and `experiment_id IS NULL`."*

### Two findings from that run, both worth acting on

**A — the config could not test the hypothesis.** The stated hypothesis was *"teams
with the highest rush yards per attempt perform better **in the following season**
against the spread"* — a cross-season lagged claim. Every selected feature is
current-season season-to-date. Nothing carries prior-season performance except the
week-1 cold-start fill. So the run tested a different question, and one Phase 4 had
already answered NO-GO at 48.8%.

→ **Capability gap: the feature catalog cannot express a lagged prior-season
aggregate.** This is not in `platform.capability_gaps` and should be.

**B — the falsifier was set below the null.** Matt pre-registered *"Below 47%"* as
falsifying. The result was 47.65% — so the hypothesis survived its own falsification
test while performing worse than a coin flip and worse than always backing the home
team. The governor checks sample size, multiple comparisons and cold-start; it does
not check whether a falsifier is weaker than the null.

**Positive note:** the config carried `success_threshold: 0.53`, not 0.54. Matt set
his own per-experiment gate. **That is ADR-006 working exactly as designed** — the
platform-level architecture is right, and only `predict_upcoming.py` still hardcodes
the retired project gate (charter A-1).

---

## 6. Design constraint for any future AI feature

Matt has proposed more AI in the platform, including a sandboxed chat agent. This is
a reasonable direction but it crosses the boundary ADR-011 and ADR-012 drew
deliberately, so it needs an ADR that supersedes, not feature creep.

The test to hold any AI feature to is ADR-012's own: **what can the agent do that a
wizard user could not?** The right answer stays *"nothing — just faster, with better
questions."* Widen what is **expressible**, never what is **privileged**.

The risk with a code- or SQL-executing agent is not security — it is Matt's own data
and he is the only user. **It is epistemic.** A number from this platform is
trustworthy because it went through the runner, the folds, the leakage guards and a
declared gate. An agent that writes its own SQL produces numbers that bypass all of
that and look identical to ones that did not. INC-001 was exactly that failure, and
it at least left an experiment record to audit; an ad-hoc query leaves nothing.

Three AI features that pass the test cleanly:

1. **A semantic-correspondence check** — does the config actually answer the stated
   hypothesis? Would have caught both §5 findings. The governor's checks are
   statistical and all passed that config. This is what an LLM is good at and a rule
   is bad at. **Strongest candidate.**
2. **A results interpreter** — read-only over `experiments.*`, explains a completed
   run including "this is noise". Does the thing Matt would otherwise open a chat for,
   but with the run data in front of it.
3. **Capability-gap triage** — read `platform.capability_gaps` and propose which
   platform features would unblock the most hypotheses. AI directing platform work.

---

## 7. Known traps — these have each bitten more than once

1. **Nothing in CI runs a test.** `api-deploy.yml` builds, deploys at 0%, curls three
   endpoints, shifts traffic. `frontend-deploy.yml` has no lint and no test step.
2. **Committing Python does not deploy it.** `02-MODELING` ships inside
   `gcr.io/nfl-model-471509/nfl-experiment-runner:latest`, built by hand via
   `cloudbuild.yaml`. There is **no** GitHub workflow for it — only api-deploy,
   frontend-deploy and tf-plan.
3. **You cannot tell what the frontend is running.** `/health` gives the API's commit
   SHA; the frontend has no equivalent. Check the bundle hash instead. **Worth fixing —
   surface the commit SHA in the frontend build.**
4. **The board has been wrong about what is deployed three separate times** — the
   scoping backend (said not deployed, was), the dashboard fixes (said fixed, were not
   deployed), and HC-S7 (said blocked, was live). **Verify, never assume.**
5. **BigQuery code written from remembered schemas has caused ~4 live failures.** Read
   `bq_writer.py` and the pydantic models directly. `preflight()` in
   `predict_upcoming.py` is the pattern to copy.
6. **`require_api_key` fails open.** `dependencies.py:62` — no `OWNER_API_KEY` means
   every write endpoint is unauthenticated, on a service open to `allUsers`. Fix:
   require it in production, assert at startup.
7. **Terraform and CI both declare the Cloud Run service spec.** `cloud_run.tf` vs
   `api-deploy.yml`'s `--set-env-vars` / `--memory` / `--concurrency`. Run
   `terraform plan` and reconcile *before* anyone runs `apply` for an unrelated reason.
8. **Traffic shifts to `LATEST`, not the smoke-tested revision** (`api-deploy.yml`).
   The revision name is already captured in `steps.revision.outputs.revision` and then
   not used. One-line fix.
9. **`.pyc` files are tracked in git.** `git add -A` swept
   `02-MODELING/models/__pycache__/*.pyc` into the repo on 2026-09-14. Add
   `__pycache__/` and `*.pyc` to `.gitignore` and `git rm -r --cached` them.

---

## 8. Documents and their status

| Document | Status |
|---|---|
| `00-PROJECT-LEAD/PROJECT-CHARTER.md` | **Authoritative framing. Read first.** New 2026-09-10 |
| `00-PROJECT-LEAD/REVIEW-2026-09-10.md` | Full state-of-the-app review, process diagnosis, findings N-1…N-6 |
| `00-PROJECT-LEAD/ROADMAP.md` | Rewritten 2026-09-10. Phase 7 (In-Season Operations) is active |
| `00-PROJECT-LEAD/DELEGATIONS.md` | **Stale** — still says nothing is deployed. Needs the §5 ruling and this queue |
| `docs/DECISIONS.md` | ADRs filed out of order (005, 007, 009, 008, 010, 011, **006**, 012). ADR-006 retires the 54% gate and sits near the bottom where a skim misses it. **Reorder it** |
| `00-PROJECT-LEAD/SPRINT-REVIEW-2026-09-10.md` | The 2026-09-09/10 sprint record |

### ADRs still owed

| Subject | Why |
|---|---|
| DEC-C — ungated serving with the honest banner | Governs what the public sees; currently only a session decision |
| `n_jobs=1` reproducibility | Plus the caveat it places on **every** historical experiment: all were run with `n_jobs=-1` and are reproducible only on the machine that produced them |
| The spread sign convention | So the answer lives in a decision record and is verified by C1, not by a comment |

---

## 9. First thing to do in the new session

1. Read `PROJECT-CHARTER.md`.
2. Re-verify §1 against the live service — do not trust this file's timestamps.
3. Give Matt **STEP 1 of §3 alone**, as its own gated step, and wait for the answer.
4. Then work the §4 queue in order.

Do not start new features, do not add surface area, and do not re-litigate the
framing. The platform now works end to end for a real NFL week. The job is making it
able to tell you when it stops working.
