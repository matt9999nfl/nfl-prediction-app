# Experiment Log

Every backtest run appends a section here.  
Format: `{experiment_id}` | `{name}` | `{run_at}` | outcome

---



---

## `20260503_103910_5ffdd7` — ol_xgb_v1

**Status: ⛔ INVALIDATED — see `docs/PIPELINE_REMEDIATION_001.md` (PR-001)**

**Run at:** 2026-05-03 10:39 UTC
**Model:** XGBoost (ol_xgb_v1), 6-fold walk-forward 2019–2024

**Overall ATS:** 1083-494-22
**Hit rate:** 68.675% over 1577 games
**Always-home baseline:** 55.929%
**Phase 2 gate:** ~~GATE PASSED~~ — result void, labels incorrect

This run was conducted against a `curated.games.home_covered` column with an inverted sign convention (nflverse `spread_line` positive = home favored was incorrectly treated as negative = home favored). The 68.675% ATS result is an artefact of the label inversion, not model performance. A spread-bin diagnostic confirmed the inversion before this result was reported to the project owner. PR-001 was raised, DATA-PIPELINE rebuilt `curated.games` with the corrected derivation, and the experiment was re-run as `20260503_110052_f6015f`.

**Per-season:**

| Season | W | L | P | Hit rate |
|--------|---|---|---|----------|
| 2019 | 163 | 91 | 2 | 64.173% |
| 2020 | 183 | 68 | 5 | 72.908% |
| 2021 | 173 | 92 | 7 | 65.283% |
| 2022 | 183 | 84 | 4 | 68.539% |
| 2023 | 174 | 94 | 4 | 64.925% |
| 2024 | 207 | 65 | 0 | 76.103% |

**Notes:** All numbers above are invalid due to label inversion. Do not use for any analysis or reporting.

---

## `20260503_110052_f6015f` — ol_xgb_v1

**Run at:** 2026-05-03 11:00 UTC
**Model:** XGBoost (ol_xgb_v1), 6-fold walk-forward 2019–2024

**Overall ATS:** 758-799-42
**Hit rate:** 48.683% over 1557 games
**Always-home baseline:** 48.555%
**Phase 2 gate:** gate not met ❌

**Per-season:**

| Season | W | L | P | Hit rate |
|--------|---|---|---|----------|
| 2019 | 116 | 130 | 10 | 47.154% |
| 2020 | 121 | 135 | 0 | 47.266% |
| 2021 | 139 | 129 | 4 | 51.866% |
| 2022 | 130 | 131 | 10 | 49.808% |
| 2023 | 122 | 136 | 14 | 47.287% |
| 2024 | 130 | 138 | 4 | 48.507% |

**Notes:** OL mismatch subset pending composite approval.

---

## `20260503_191541_a8c126` -- ol_xgb_v2

**Run at:** 2026-05-03 19:15 UTC
**Model:** XGBoost (ol_xgb_v2), 6-fold walk-forward 2019-2024
**Features:** 52 total (23 per-team x2 + game context)

**Overall ATS:** 773-784-42
**Hit rate:** 49.647% over 1557 games
**Always-home baseline:** 48.555%
**Phase 2 gate:** gate not met

**Per-season:**

| Season | W | L | P | Hit rate |
|--------|---|---|---|----------|
| 2019 | 116 | 130 | 10 | 47.154% |
| 2020 | 134 | 122 | 0 | 52.344% |
| 2021 | 134 | 134 | 4 | 50.000% |
| 2022 | 137 | 124 | 10 | 52.490% |
| 2023 | 120 | 138 | 14 | 46.512% |
| 2024 | 132 | 136 | 4 | 49.254% |

**Notes:** Comprehensive nflfastR feature set (QB + OL + defense + situational). This is the May 3 baseline result used as the A2 faithfulness target (49.65%). Standalone runner, seasons 2019–2024.

---

## Phase 4 Experiments — Post-INC-001-Fix Re-run (2026-05-17)

The following three runs re-run the Phase 4 Tier 1 experiments after DATA-PIPELINE rebuilt `curated.games` with the corrected `home_covered` derivation (INC-001). All previous Phase 4 config-runner results (runs `20260517_002840_caf667`, `20260517_003112_c59106`, `20260517_003726_2d4031`) are INVALIDATED — see `PIPELINE_REMEDIATION_002.md` in `01-DATA-PIPELINE/`.

Spread-bin diagnostic confirmed labels clean before any run: home_dog_10+=50.8%, home_dog_3-10=47.5%, home_fav_10+=54.4%, home_fav_3-10=50.7%, pick_em=47.6%.

---

## `20260517_020202_0504ff` — A2: 23-feature faithfulness check

**Status:** ✅ VALID (post-INC-001-fix)

**Run at:** 2026-05-17 02:04 UTC
**Config:** `v2-23base-faithfulness-check` (experiment_config_id: `6ec7deac-3c62-4954-a8d4-a7bfb21b410f`)
**Model:** XGBoost (v2), 6-fold walk-forward 2020–2025 (train_seasons=4, start=2016)
**Features:** 52 total (23 per-team base x2 + game context + rest_differential)

**Overall ATS:** 794-788-33
**Hit rate:** 50.190% over 1,582 games
**Gate (54%, 250+ games):** NOT MET
**Purpose:** A2 runner faithfulness check — target ≈49.65% (±1 pp). Result within 0.54 pp of target. PASS.

**Per-season:**

| Season | W | L | P | Hit rate |
|--------|---|---|---|----------|
| 2020 | 134 | 122 | 0 | 52.344% |
| 2021 | 134 | 134 | 4 | 50.000% |
| 2022 | 137 | 124 | 10 | 52.490% |
| 2023 | 120 | 138 | 14 | 46.512% |
| 2024 | 132 | 136 | 4 | 49.254% |
| 2025 | 137 | 134 | 1 | 50.554% |

**Notes:** Runner faithfulness confirmed. The config-driven runner produces results consistent with the May 3 standalone script (49.647%) on the same feature set. The slight difference (0.54 pp) is attributable to the expanded season range (2020–2025 vs 2019–2024) and is within tolerance. Infrastructure is trustworthy.

---

## `20260517_020425_38cf03` — A3: shuffled-label leakage test

**Status:** ✅ VALID (post-INC-001-fix) — leakage-detection run, gate_passed forced False

**Run at:** 2026-05-17 02:06 UTC
**Config:** `test3-shuffle-labels-leakage-test` (experiment_config_id: `decaa551-b991-43af-9a71-ab70b9580af7`)
**Model:** XGBoost (v2), 6-fold walk-forward 2020–2025 (train_seasons=4, start=2016)
**Features:** 16 total (5 rush per-team base x2 + game context + rest_differential)
**shuffle_labels:** True — home_covered randomly permuted within each season before training

**Overall ATS:** 808-774-33
**Hit rate:** 51.075% over 1,582 games
**Gate:** NOT MET (forced False for shuffle runs)
**Purpose:** A3 leakage detection — target ≈50%. Result 51.1%. PASS — no leakage.

**Per-season:**

| Season | W | L | P | Hit rate |
|--------|---|---|---|----------|
| 2020 | 140 | 116 | 0 | 54.688% |
| 2021 | 135 | 133 | 4 | 50.373% |
| 2022 | 130 | 131 | 10 | 49.808% |
| 2023 | 128 | 130 | 14 | 49.612% |
| 2024 | 128 | 140 | 4 | 47.761% |
| 2025 | 147 | 124 | 1 | 54.244% |

**Notes:** Shuffled labels produce ~51% hit rate as expected. The slight deviation from 50% is random noise from a finite sample (1,582 games). The fold-1 result of 54.7% on shuffled labels is within the expected variance range for ~256 games. No systematic leakage detected. The feature pipeline is clean. BQ notes field tagged [SHUFFLE_LABELS=True].

---

## `20260517_020637_245bc9` — test3: rush features (corrected labels)

**Status:** ✅ VALID (post-INC-001-fix)

**Run at:** 2026-05-17 02:08 UTC
**Config:** `test3` (experiment_config_id: `19a50bf1-e812-4745-b153-042c6db46a00`)
**Model:** XGBoost (v2), 6-fold walk-forward 2020–2025 (train_seasons=4, start=2016)
**Features:** 16 total (5 rush per-team base x2 + game context + rest_differential)

**Overall ATS:** 772-810-33
**Hit rate:** 48.799% over 1,582 games
**Gate (54%, 250+ games):** NOT MET

**Per-season:**

| Season | W | L | P | Hit rate |
|--------|---|---|---|----------|
| 2020 | 119 | 137 | 0 | 46.484% |
| 2021 | 148 | 120 | 4 | 55.224% |
| 2022 | 126 | 135 | 10 | 48.276% |
| 2023 | 133 | 125 | 14 | 51.550% |
| 2024 | 126 | 142 | 4 | 47.015% |
| 2025 | 120 | 151 | 1 | 44.280% |

**Notes (A1 decision rule):** Only 1/6 folds exceeds 54% (2021: 55.2%). 5/6 folds are below 52%. The overall result of 48.8% is below the market (closing line ≈50%). This is the definitive corrected result for the 10-rushing-feature experiment. The prior 58.3% result (all three test1/test2/test3 runs) was entirely a label-inversion artifact — the model was learning to predict the inverted outcome. With correct labels, the rushing features show no detectable edge over the closing line. The OL rushing hypothesis is not supported by this experiment on real labels. Feature importance is heavily distributed (no single dominant feature), consistent with a model fitting noise rather than a real signal. Next step is PROJECT-LEAD Go/No-Go on whether to reformulate the experiment with different features or hypothesis.
