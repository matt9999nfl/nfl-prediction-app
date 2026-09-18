# PROJECT CHARTER — NFL Prediction App

**Owner:** Matt (project owner) · **Maintained by:** PROJECT-LEAD
**Status:** Authoritative. **Supersedes every framing statement in every other document in this repo.**
**Established:** 2026-09-10

> **Read this before `ROADMAP.md`, before any phase status document, and before
> any `instructions.md`.** If another document in this repo implies a different
> purpose for this project, that document is wrong and should be corrected, not
> reconciled.

---

## 1. What this project is

**This is an app-building project. The deliverable is a platform for running
endless experiments on NFL data.**

The platform's job is to let a hypothesis be stated, scoped, run, measured and
recorded — honestly, reproducibly, and without hand-editing code. Whether any
particular hypothesis turns out to be true is a *result the platform produces*,
not a thing the platform is judged by.

## 2. What this project is not

**It is not an attempt to prove that the market undervalues offensive-line
performance.**

That hypothesis was the project's starting point in early 2026. It was the first
thesis loaded into the platform, it was tested, and it did not clear its
threshold. That is a finished, recorded experimental result — one row in the
experiment log. It is not the project's premise, its goal, or its measure of
success, and it has not been either of those things since **ADR-005**
(2026-05-03): *"Project goal is a comprehensive NFL prediction platform, not an
OL hypothesis validator."*

**There is no project-level success gate.** ADR-006 (2026-05-03) retired the
≥54% ATS / ≥250 games gate and moved gates onto individual experiments, where
each defines its own criteria. Any document, config, code comment, database
column or UI element implying a project-wide 54% threshold is a survival from
before that decision.

## 3. Sequencing — the part that keeps getting lost

**Build the app first. Model later, through the app, during and after the 2026
season.**

Modelling and prediction work is *downstream* of the platform being finished and
trustworthy. Right now the correct question about any proposed piece of work is:

> Does this make the platform better able to state, run, measure or record an
> experiment?

and **not**:

> Does this make the model more accurate?

The second question is legitimate and will matter — later, and it will be
answered *by running experiments through the platform*, not by editing feature
lists by hand. Improving a model outside the platform is not progress on this
project; it is a bypass of the thing being built (ADR-011).

## 4. The distinction to hold onto

There are two projects here, and they are easy to conflate:

| | Project A | Project B |
|---|---|---|
| **Goal** | A trustworthy, useful experimentation platform | Finding a real edge |
| **Status** | Nearly there | Has not happened |
| **Active now** | ✅ Yes — this is the work | ❌ Not yet |
| **Success looks like** | An experiment can be run end-to-end, and its result believed | A model clears its own stated gate |

Everything currently in flight belongs to **Project A**. Live forward prediction
(DEC-A) belongs to Project A: it makes the platform do something it could not do
before. It does not, on its own, make any model better, and the app must not
imply otherwise (DEC-C).

*(This restates §6 of `PRE_SEASON_STATUS_2026-08-31.md`, which had it right. It
is promoted here because a standing note buried at the end of a dated status
document does not survive contact with a cold session.)*

## 5. How a capability gap is framed

When the platform cannot express something, that is a **capability gap** — a
platform defect. It is not a modelling finding.

Worked example, from the 2026-09-09/10 sprint: the model cannot see the betting
line, because spread, total and moneyline are not in the feature catalog. The
wrong way to state that is *"we should add the spread as a feature because the
market's price is what the hypothesis is about."* That is a modelling
recommendation dressed as a platform one, and it smuggles the retired OL premise
back in.

The right way to state it:

> The feature catalog cannot express the market's own price, so an entire class
> of hypothesis cannot be *stated* on this platform at all. Closing the gap means
> making spread, total and moneyline **selectable features**. Whether any of them
> earns a place in a model is then answered by running an experiment through the
> runner and its gate — which is exactly what the architecture exists to enforce.

The same test applies to calibration: whether the app *measures* calibration is a
platform capability, and belongs in the queue. What the calibration turns out to
be is a model result, and belongs in the experiment log.

## 6. Standing instruction to every agent and every future session

1. Do not describe this project as being about offensive-line statistics, market
   inefficiency, or proving any hypothesis. It is about building an app.
2. Do not introduce, restore or cite a project-level 54% ATS gate. ADR-006
   retired it.
3. When proposing work, state which platform capability it creates or protects.
   If it creates none, say so plainly — it may still be worth doing, but it is
   not platform progress.
4. `gate_passed = false` on a served prediction means *no experiment has cleared
   its own stated criteria*. It does not mean the project has failed a test.
5. If you find OL-hypothesis framing or a 54% gate anywhere in this repo — prose,
   comment, config, schema or UI — treat it as a defect and log it, rather than
   working around it.

---

## Appendix — known survivals of the retired framing

Recorded 2026-09-10 so they can be cleared deliberately rather than
rediscovered. These are why the old premise keeps resurfacing: **it is still
encoded in the running system, not merely in stale prose.**

| # | Where | What |
|---|---|---|
| A-1 | `02-MODELING/backtests/predict_upcoming.py` (`build_config_payload`, `build_run_row`) | Writes `"success_threshold": 0.54` into `experiment_configs.evaluation` and `backtest_runs.success_criteria` on **every production run**. The app therefore re-asserts the retired project-level gate every Tuesday. |
| A-2 | Dashboard honest-evaluation banner | Driven by `gate_passed = false`, which is measured against A-1's 0.54. Every visitor is told the app failed a gate the project abolished on 2026-05-03. |
| A-3 | `02-MODELING/models/ol_xgb.py` docstring | *"If the gate is missed … the hypothesis may need to be revisited before the model architecture does."* Framing from before ADR-005, in the model file. |
| A-4 | `experiments.backtest_predictions.ol_mismatch_flag` | An OL-hypothesis-specific column carried through the production forward-prediction schema. |
| A-5 | `00-PROJECT-LEAD/ROADMAP.md` | Header claims Phase 5 complete / Phase 6 active; the table says Phase 4 ✅ Complete; the Phase 4 section says "🔄 IN PLANNING, not yet started". Three claims, one document. |
| A-6 | `docs/DECISIONS.md` ordering | ADRs run 005, 007, 009, 008, 010, 011, **006**, 012. ADR-006 — the decision that retires the gate — is filed out of sequence near the bottom, where a session skimming the file will miss it. |

**A-1 and A-2 are the load-bearing ones.** Prose drift is annoying; a retired
gate that the production pipeline rewrites into the database weekly and the UI
renders to users is the actual mechanism by which the old framing keeps coming
back.
