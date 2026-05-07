# Experiment Log

Every backtest run appends a section here.  
Format: `{experiment_id}` | `{name}` | `{run_at}` | outcome

---



---

## `20260503_103910_5ffdd7` — ol_xgb_v1

**Run at:** 2026-05-03 10:39 UTC
**Model:** XGBoost (ol_xgb_v1), 6-fold walk-forward 2019–2024

**Overall ATS:** 1083-494-22
**Hit rate:** 68.675% over 1577 games
**Always-home baseline:** 55.929%
**Phase 2 gate:** GATE PASSED ✅

**Per-season:**

| Season | W | L | P | Hit rate |
|--------|---|---|---|----------|
| 2019 | 163 | 91 | 2 | 64.173% |
| 2020 | 183 | 68 | 5 | 72.908% |
| 2021 | 173 | 92 | 7 | 65.283% |
| 2022 | 183 | 84 | 4 | 68.539% |
| 2023 | 174 | 94 | 4 | 64.925% |
| 2024 | 207 | 65 | 0 | 76.103% |

**Notes:** OL mismatch subset pending composite approval.

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

**Notes:** Comprehensive nflfastR feature set (QB + OL + defense + situational).
