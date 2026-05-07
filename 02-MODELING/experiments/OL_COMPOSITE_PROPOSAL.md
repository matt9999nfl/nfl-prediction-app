# OL Mismatch Composite — Definition Proposal

**From:** MODELING
**To:** PROJECT-LEAD
**Status:** AWAITING APPROVAL — do not run subset analysis until approved in writing

---

## Background

Per MODELING_SPEC_PHASE1.md §"OL Mismatch Subset — Definition Approval Required",
MODELING must propose the OL composite definition and receive PROJECT-LEAD approval
before running any subset analysis.  This document is that proposal.

---

## 1. Which features combine into the OL composite

The OL composite is an **offensive pressure-resistance score** — a single number
summarizing how well a team's offensive line protects the quarterback, built from
two complementary signals:

**Component A — Pressure proxy rate** (`ol_pressure_proxy_rate`)
Definition: (sacks + QB hits) / pass attempts, season-to-date through the prior week.
Rationale: This is the most direct measure of whether the OL is getting beat on pass
plays.  Sacks represent complete failures; QB hits represent near-misses that
still disrupt timing.  Their sum per attempt captures the full pressure frequency.
Direction: **lower is better** for the offense.

**Component B — Pass EPA per attempt** (`ol_pass_epa_per_att`)
Definition: Mean EPA on pass attempts, season-to-date.
Rationale: EPA captures the *outcome* of pass plays after accounting for down,
distance, and field position.  Even if the sack/hit rate is low, if the team is
repeatedly losing expected points on pass plays the OL is not enabling the offense.
Including EPA alongside the mechanical pressure rate adds a results-based sanity
check.
Direction: **higher is better** for the offense.

No other features are included in the composite.  Adding run-blocking features
(rush EPA, rush yards) would dilute the signal — the hypothesis is specifically
about pass-blocking mismatch, not overall OL quality.

---

## 2. How the composite is scaled / normalized

For each game's OL composite value, we use the **season-to-date features as computed
at prediction time** (i.e., the same feature values that feed the model — no
additional computation).

The composite is computed as a **signed Z-score combination**:

```
ol_composite = Z(ol_pass_epa_per_att)  -  Z(ol_pressure_proxy_rate)
```

Where Z(x) is the **within-season Z-score** of feature x across all teams through
the current week of the current season.

- `ol_pass_epa_per_att` enters **positively** (higher EPA = better OL)
- `ol_pressure_proxy_rate` enters **negatively** (higher pressure rate = worse OL)
- Adding the two Z-scores produces a single number where higher = better OL

**Important:** the Z-score standardization is computed separately for each season,
using only the teams and weeks *within* that season up to the current week.
This means the composite is always relative to contemporaneous competition — a
2022 OL is not directly compared to a 2016 OL in the mismatch flag.

For the test season, the Z-scores are computed using only the teams and weeks
available through that point (no leakage from future weeks of the test season).

---

## 3. How quartile boundaries are computed

Quartile boundaries are computed **per season**, using only the teams present
in that season up to the week of the game being evaluated.

Specifically, for a game in (season=S, week=W):
- All teams' `ol_composite` values for games in season S through week W-1
  form the reference distribution
- The 25th and 75th percentiles of that distribution define the quartile cutoffs
- A team is "top-quartile OL offense" if their composite ≥ 75th percentile
- A team is "bottom-quartile OL defense" if their composite ≤ 25th percentile
  (where the defensive composite is the equivalent: `Z(def_pass_epa_allowed_per_att)` − `Z(def_pressure_proxy_rate)`)

Using per-season, per-week boundaries prevents early-season (small sample)
values from being compared against late-season (stabilized) values, and prevents
cross-season talent inflation/deflation from distorting the quartile labels.

---

## 4. The exact mismatch filter

A game is flagged `ol_mismatch_flag = 1` when:

> **The home team's OL composite is in the top quartile of offensive OL quality**
> **AND the away team's defensive composite is in the bottom quartile of defensive OL resistance**

In words: the home team has an elite pass-blocking line relative to their
contemporaneous peers, and they are facing a defense that is among the worst at
generating pass rush.

The mirror case (away team has elite OL, home defense is soft) is tracked
separately as `ol_mismatch_flag = 2` for diagnostic purposes, but the primary
hypothesis test is flag = 1 (testing the home team edge specifically, to avoid
confounding with the general home-field advantage).

**Why the home-team frame only (flag = 1) for the primary test:**
Including both directions (home elite OL vs. soft away D, and away elite OL vs.
soft home D) would be cleaner for sample size, but mixing them risks confounding
the OL signal with home-field advantage in ways that are hard to decompose.
The secondary diagnostic (flag = 2) lets us check whether the away-OL version
shows the same pattern or a different one.

---

## Sample size estimate

Based on the data available (2019–2024 test seasons, ~272 games/season):
- Roughly 25% of teams qualify as top-quartile OL offense in any given week
- Roughly 25% of defenses qualify as bottom-quartile
- If independent: ~6.25% of games would qualify → ~17 games/season → ~100 games
  over 6 test seasons

This is a small subset.  That is expected.  The mismatch subset result is
**diagnostic only** per the spec — it does not gate Phase 2.  A small sample
means we will not draw confident conclusions from it, but we can at least report
the directional result and whether it warrants further investigation.

---

## What I am NOT proposing (and why)

**Not using roster/depth chart changes as the mismatch trigger:** That would
require OL injury/lineup-change data that is not in `curated.*` for Phase 1.
The composite approach uses only what is available from play-by-play and can
be computed without the roster tables.

**Not using a cross-season distribution:** Quartiles computed across all seasons
would conflate era-level changes in league-wide pass-rush rates (which have
increased substantially over the 2015–2024 window) with true team-level variance.

**Not including run-blocking in the composite:** The hypothesis is about
pass-blocking mismatch specifically.  Diluting with run-blocking features would
muddy the test.

---

## PROJECT-LEAD Decision

**Status:** 🔄 APPROVED WITH ONE REQUIRED MODIFICATION
**Reviewed by:** PROJECT-LEAD
**Date:** 2026-05-03

### Required change — defensive composite formula direction

The defensive composite as proposed:

```
Z(def_pass_epa_allowed_per_att) − Z(def_pressure_proxy_rate)
```

is directionally inconsistent with the quartile filter. With this formula, a HIGH value = bad defense (allows lots of EPA, generates little pressure). The filter then applies "bottom quartile" (≤ 25th percentile), which selects GOOD defenses — the opposite of the intended mismatch.

**Change the defensive composite to:**

```
Z(def_pressure_proxy_rate) − Z(def_pass_epa_allowed_per_att)
```

This makes the defensive composite directionally consistent with the offensive composite: higher = better defense (generates more pressure, allows less EPA). "Bottom quartile" (≤ 25th percentile) now correctly identifies the weakest defenses — those least capable of resisting an elite OL.

### Everything else approved as written

- Two-component composite (pressure proxy rate + pass EPA per attempt) ✅
- Within-season Z-score standardization ✅
- Per-season, per-week quartile boundaries (no cross-season comparison) ✅
- Home-team-primary mismatch as flag=1, away-team mirror as flag=2 ✅
- Pass-blocking-only scope (no run-blocking dilution) ✅
- Diagnostic-only status (does not gate Phase 2) ✅

### Cleared to proceed

Implement the corrected defensive composite formula and proceed with the subset analysis. No further approval needed for this definition.
