# INC-001 Investigation Report — Label Inversion Forensics

**Filed by:** PROJECT-LEAD  
**Date:** 2026-05-17  
**Purpose:** Independent verification of whether the 58-61% rushing-feature ATS results were legitimate or artifacts of inverted labels. This report supersedes the narrative in INC-001-label-inversion.md with evidence drawn directly from source code and prediction files.

---

## Verdict

**The 58-61% results were produced on inverted labels and are not valid.**

Three independent lines of evidence support this: the nflverse sign convention (confirmed from official documentation), the formula logic, and direct game-level verification against real 2019 NFL outcomes that are publicly checkable.

---

## 1. The Sign Convention

The `home_spread_close` column in `curated.games` maps directly from nflverse's `spread_line` field (see `build_curated_games.py` line 63: `"spread_line": "home_spread_close"`).

**nflverse's sign convention (confirmed from nflreadr official documentation):**
- Positive `spread_line` = home team is the favourite
- Negative `spread_line` = away team is the favourite (home team is the underdog)

This is the opposite of the American sportsbook display convention (where favourites are shown as negative). nflverse consistently uses positive = home favoured throughout their dataset.

So in the data:
- NO Saints favoured by 6.5 at home → `home_spread_close = 6.5`
- PHI Eagles favoured by 10.5 at home → `home_spread_close = 10.5`
- BAL Ravens favoured by 13 at home → `home_spread_close = 13.0`

---

## 2. The Formula

**Current formula in `build_curated_games.py` (post-fix, lines 94–99):**
```python
required_margin = home_spread_close
covered[both_valid & (margin > required_margin)] = True
```

With nflverse's positive-for-home-favourite convention, this is correct:
- Home favoured by 6.5 (spread = 6.5): must win by more than 6.5 → `margin > 6.5` ✓
- Home underdog by 6.5 (spread = -6.5): must lose by fewer than 6.5 → `margin > -6.5` ✓

**Pre-fix formula (as reconstructed from INC-001):**
```python
required_margin = -home_spread_close   # negation applied
covered[both_valid & (margin > required_margin)] = True
```

With the same nflverse convention, this inverts the condition:
- Home favoured by 6.5 (spread = 6.5): `required_margin = -6.5` → `margin > -6.5` → home losing by 5 is "covered" ✗
- Home underdog by 6.5 (spread = -6.5): `required_margin = 6.5` → `margin > 6.5` → underdog must win outright by 7+ to "cover" ✗

---

## 3. Game-Level Spot-Checks

These three games are from real 2019 NFL Week 1 and Week 2. Scores and spread outcomes can be independently verified against any sports reference site (Pro Football Reference, ESPN, etc.).

All values below are read directly from the prediction CSV files stored in `02-MODELING/backtests/reports/`.

---

### Game 1: 2019_01_HOU_NO — HOU @ NO, Week 1, 2019

**What happened:** New Orleans Saints hosted the Houston Texans. NO were favoured.  
**Final score:** NO 30, HOU 28 — Saints won by 2  
**Spread:** NO -6.5 (sportsbook display) = `home_spread_close = 6.5` in nflverse  
**Did NO cover?** No. They needed to win by more than 6.5. They won by 2.  
**Correct label:** `home_covered = False`

| Run ID | Date | `actual_home_covered` in file | Correct? |
|--------|------|-------------------------------|----------|
| `20260503_103910_5ffdd7` | May 3 (pre-fix) | `True` | ❌ Wrong |
| `20260503_110052_f6015f` | May 3 (post-PR-001) | `False` | ✅ Correct |
| `20260503_191541_a8c126` | May 3 (post-PR-001) | `False` | ✅ Correct |
| `20260517_003726_2d4031` | May 17 (Phase 4, pre-INC-001) | `True` | ❌ Wrong |

**Verify yourself:** Search "Saints Texans Week 1 2019" — final score NO 30-28.

---

### Game 2: 2019_01_WAS_PHI — WAS @ PHI, Week 1, 2019

**What happened:** Philadelphia Eagles hosted the Washington Redskins. PHI were heavy favourites.  
**Final score:** PHI 32, WAS 27 — Eagles won by 5  
**Spread:** PHI -10.5 (sportsbook display) = `home_spread_close = 10.5` in nflverse  
**Did PHI cover?** No. They needed to win by more than 10.5. They won by 5.  
**Correct label:** `home_covered = False`

| Run ID | Date | `actual_home_covered` in file | Correct? |
|--------|------|-------------------------------|----------|
| `20260503_103910_5ffdd7` | May 3 (pre-fix) | `True` | ❌ Wrong |
| `20260503_110052_f6015f` | May 3 (post-PR-001) | `False` | ✅ Correct |
| `20260503_191541_a8c126` | May 3 (post-PR-001) | `False` | ✅ Correct |
| `20260517_003726_2d4031` | May 17 (Phase 4, pre-INC-001) | `True` | ❌ Wrong |

**Verify yourself:** Search "Eagles Redskins Week 1 2019" — final score PHI 32-27.

---

### Game 3: 2019_02_ARI_BAL — ARI @ BAL, Week 2, 2019

**What happened:** Baltimore Ravens hosted the Arizona Cardinals. BAL were very heavy favourites.  
**Final score:** BAL 23, ARI 17 — Ravens won by 6  
**Spread:** BAL -13 (sportsbook display) = `home_spread_close = 13.0` in nflverse  
**Did BAL cover?** No. They needed to win by more than 13. They won by 6.  
**Correct label:** `home_covered = False`

| Run ID | Date | `actual_home_covered` in file | Correct? |
|--------|------|-------------------------------|----------|
| `20260503_103910_5ffdd7` | May 3 (pre-fix) | `True` | ❌ Wrong |
| `20260503_110052_f6015f` | May 3 (post-PR-001) | `False` | ✅ Correct |
| `20260503_191541_a8c126` | May 3 (post-PR-001) | `False` | ✅ Correct |
| `20260517_003726_2d4031` | May 17 (Phase 4, pre-INC-001) | `True` | ❌ Wrong |

**Verify yourself:** Search "Ravens Cardinals Week 2 2019" — final score BAL 23-17.

---

## 4. Why 58-61% Instead of 39-42%

This is the question that rightly prompted further investigation. If labels were simply binary-flipped, a model scoring 58% on inverted labels should score ~42% on correct labels — not 48.8%. The explanation is that these are two different models, not the same model re-evaluated.

The walk-forward backtest works like this: for each test fold, a new model is trained from scratch on the training seasons and evaluated on the test season. The reported accuracy reflects that trained model on that label set.

- **Pre-fix model** (test1/test2/test3, run after May 7): trained on inverted labels, evaluated against inverted labels → 58-61%
- **Post-fix model** (test3 rerun, May 17): trained on correct labels, evaluated against correct labels → 48.8%

These are not the same model. The post-fix model learned different patterns. So the 39-42% argument — while logically correct for a static model — doesn't apply here because retraining on correct labels produces a new model that finds whatever signal exists in the real data, which in this case is essentially none (48.8% ≈ random).

The 39-42% prediction would be tested by taking the pre-fix trained model and evaluating it against correct labels without retraining. That test was not run, but the game-level spot-checks above provide direct confirmation that the pre-fix labels were wrong, making the question moot.

---

## 5. How the Model Was Trained on Inverted Labels Without Anyone Noticing

This is the most important question from a process perspective.

The inversion was first discovered and fixed in **PR-001 on May 3**. But critically, PR-001 fixed the **data in BigQuery** — it manually rebuilt the `curated.games` table with the correct labels. It did **not** fix the formula in `build_curated_games.py`. The script remained buggy.

On **May 7**, Phase 3 deployment activated the **Cloud Scheduler** — a weekly pipeline job that automatically runs `build_curated_games.py` to refresh the data. When it ran, it executed the still-buggy script and silently overwrote the correctly-rebuilt BigQuery table with inverted labels again. There was no alert, no validation gate, no comparison to the previous state.

The rushing experiments (test1, test2, test3) were run on **May 9**, two days after this silent overwrite. MODELING read from `curated.games`, which now had inverted labels. The model was trained on this data, evaluated against this data, and reported 58-61%. Since 58%+ sounds like a significant positive result (rather than the obviously wrong 86%+ that would ring alarm bells), and since no one had reason to re-audit the data quality after PR-001 was filed, the result was logged and treated as a genuine finding.

The 86.8%/6.3% spread-bin diagnostic values were not computed at that time — they were computed in Phase 4 as part of the Tier 1 investigation. Until that diagnostic was run, there was no automated check that would have surfaced the problem.

---

## 6. The Process Failure

This was not a communication failure between MODELING and DATA-PIPELINE. Both agents operated correctly within their defined scope. The failure was architectural:

**PR-001 treated a code bug as a data problem.** It fixed the output (the BQ table) without fixing the source (the script). This is equivalent to correcting a typo in a printed report without fixing the template — the next print run produces the same typo.

**The weekly scheduler had no validation gate.** When `build_curated_games.py` runs, it writes to BigQuery unconditionally. There was no check that the resulting `home_covered` distribution looked plausible before committing the write. A simple sanity check (cover rate in each spread bucket should be 45-55%) would have caught this immediately on the first scheduler run.

**Prevention (now implemented):** INC-001 triggered two fixes:
1. The script formula was corrected (the root cause)
2. A spread-bin sanity check was added to `validate_and_report.py` — if cover rates fall outside 45-55% in any spread bucket, the pipeline fails loudly and does not write to the table

---

## 7. Summary

| Question | Answer |
|----------|--------|
| Were the 58-61% results legitimate? | No — produced on inverted labels |
| Is the nflverse sign convention non-standard? | Yes — positive = home favourite, confirmed from official docs |
| Was the original formula wrong? | Yes — negating the spread with nflverse's convention inverts the label |
| Is the post-fix formula correct? | Yes — verified against 3 real games |
| Is the rushing hypothesis dead? | Yes — 48.8% on correct labels, no edge |
| Was this a communication failure? | No — it was an incomplete fix (code bug treated as data bug) |
| Could automated checks have caught this? | Yes — the validation gate added in INC-001 would have blocked the re-inversion |
