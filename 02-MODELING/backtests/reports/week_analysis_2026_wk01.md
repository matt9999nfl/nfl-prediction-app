# Week analysis — 2026 week 1

**Week 1's explanations are approximate** (`is_approximate=true`, max diff 0.0370). Every number below that says "toward the pick" is re-signed toward the LIVE served pick, not the underlying approximate model's own lean — see the side-mismatch flags.

**3 game(s) disagree on side** between the underlying explanation model and the live served pick: 2026_01_ATL_PIT, 2026_01_GB_MIN, 2026_01_NYJ_TEN. Flagged per-game below and excluded from every "toward the pick" aggregate statistic.

**Regenerated after kickoff** (`clean_forward=false`): 2026_01_NE_SEA, 2026_01_SF_LA.

## 1. Game by game

### ARI @ LAC (`2026_01_ARI_LAC`)

- Approximate explanation (reproduction_max_diff=0.0370).

- Closing spread (home perspective): +9.5 — favourite: ARI
- Live pick: home (LAC), P(home cover) = 0.537
- Result: home_covered=False, correct=0

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| OL pass protection | home_ol_qb_hit_rate | home | 0.219 | 93.8 | +0.118 |
| OL pass protection | away_ol_sack_rate | away | 0.083 | 71.9 | +0.101 |
| weather | roof_dome | game | 1.000 | n/a | +0.079 |
| coverage/defence other | away_def_pass_epa_allowed_per_att | away | 0.152 | 84.4 | -0.068 |
| defence run | home_def_rush_epa_allowed_per_att | home | -0.074 | 9.4 | -0.067 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | +0.107 | +0.182 | +0.289 |
| OL run blocking | +0.030 | -0.028 | +0.002 |
| QB | +0.089 | -0.064 | +0.025 |
| coverage/defence other | -0.083 | -0.051 | -0.134 |
| defence pass rush | +0.018 | +0.049 | +0.067 |
| defence run | -0.121 | -0.028 | -0.149 |
| form | -0.046 | +0.003 | -0.043 |
| record/margin | -0.022 | +0.034 | +0.013 |
| rest | -0.030 | -0.023 | -0.053 |
| run game | -0.026 | +0.036 | +0.010 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 25% of total |contribution|; top 3 carry 54%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - roof_dome (weather family): +0.079 toward the pick
  - temp (weather family): +0.022 toward the pick
  - wind (weather family): -0.013 toward the pick

The model favours LAC over ARI, driven mainly by OL pass protection and weather. Top single driver: home_ol_qb_hit_rate (OL pass protection), LAC at the 94th league percentile, contributing +0.118 log-odds toward the pick.

### ATL @ PIT (`2026_01_ATL_PIT`)

- **SIDE MISMATCH** — the underlying (approximate) explanation model leans AWAY; the live served pick is HOME. Excluded from every "toward the pick" aggregate below.
- Approximate explanation (reproduction_max_diff=0.0370).

- Closing spread (home perspective): +5.5 — favourite: ATL
- Live pick: home (PIT), P(home cover) = 0.511
- Result: home_covered=True, correct=1

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| OL pass protection | away_ol_sack_rate | away | 0.046 | 15.6 | -0.132 |
| OL run blocking | home_ol_rush_yards_per_att | home | 4.466 | 50.0 | +0.093 |
| defence pass rush | away_def_sack_rate | away | 0.097 | 90.6 | +0.056 |
| form | home_rolling_3wk_epa_trend | home | 0.026 | 53.1 | -0.054 |
| QB | home_pass_explosive_rate | home | 0.071 | 25.0 | +0.049 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | +0.027 | -0.168 | -0.142 |
| OL run blocking | +0.098 | -0.067 | +0.031 |
| QB | +0.069 | +0.028 | +0.098 |
| coverage/defence other | +0.017 | +0.036 | +0.053 |
| defence pass rush | +0.037 | +0.072 | +0.109 |
| defence run | -0.077 | +0.038 | -0.040 |
| form | -0.054 | +0.031 | -0.023 |
| record/margin | -0.025 | +0.045 | +0.020 |
| rest | -0.011 | -0.015 | -0.026 |
| run game | -0.018 | -0.017 | -0.034 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 17% of total |contribution|; top 3 carry 48%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - roof_dome (weather family): -0.018 toward the pick
  - temp (weather family): +0.014 toward the pick
  - wind (weather family): -0.010 toward the pick

The model favours PIT over ATL, driven mainly by OL pass protection and OL run blocking. Top single driver: away_ol_sack_rate (OL pass protection), ATL at the 16th league percentile, contributing -0.132 log-odds toward the pick.

### BAL @ IND (`2026_01_BAL_IND`)

- Approximate explanation (reproduction_max_diff=0.0370).

- Closing spread (home perspective): -3.5 — favourite: IND
- Live pick: away (BAL), P(home cover) = 0.499
- Result: home_covered=False, correct=1

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| QB | away_qb_epa_under_pressure | away | -1.063 | 21.9 | +0.093 |
| defence run | home_def_rush_yards_allowed_per_att | home | 3.984 | 9.4 | -0.075 |
| QB | away_qb_cpoe | away | 2.992 | 81.2 | +0.056 |
| defence run | home_def_rush_epa_allowed_per_att | home | -0.050 | 28.1 | +0.054 |
| QB | home_pass_explosive_rate | home | 0.077 | 37.5 | -0.053 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | +0.058 | +0.118 | +0.176 |
| OL run blocking | -0.008 | +0.072 | +0.063 |
| QB | +0.077 | -0.161 | -0.084 |
| coverage/defence other | -0.004 | +0.022 | +0.018 |
| defence pass rush | -0.044 | +0.023 | -0.021 |
| defence run | +0.010 | +0.016 | +0.026 |
| form | -0.050 | +0.030 | -0.020 |
| record/margin | -0.021 | +0.021 | +0.000 |
| rest | -0.016 | -0.040 | -0.057 |
| run game | -0.015 | -0.026 | -0.040 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 22% of total |contribution|; top 3 carry 54%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - temp (weather family): +0.037 toward the pick
  - wind (weather family): +0.015 toward the pick
  - roof_dome (weather family): +0.013 toward the pick

The model favours BAL over IND, driven mainly by QB and defence run. Top single driver: away_qb_epa_under_pressure (QB), BAL at the 22nd league percentile, contributing +0.093 log-odds toward the pick.

### BUF @ HOU (`2026_01_BUF_HOU`)

- Approximate explanation (reproduction_max_diff=0.0370).

- Closing spread (home perspective): -1.5 — favourite: HOU
- Live pick: away (BUF), P(home cover) = 0.448
- Result: home_covered=False, correct=1

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| QB | away_qb_cpoe | away | 3.819 | 87.5 | +0.112 |
| defence run | away_def_rush_yards_allowed_per_att | away | 5.225 | 93.8 | +0.109 |
| OL pass protection | away_ol_sack_rate | away | 0.075 | 65.6 | -0.090 |
| defence pass rush | away_def_pressure_proxy_rate | away | 0.244 | 75.0 | -0.079 |
| defence pass rush | away_def_sack_rate | away | 0.072 | 56.2 | +0.068 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | +0.073 | +0.053 | +0.126 |
| OL run blocking | -0.055 | +0.078 | +0.022 |
| QB | +0.080 | -0.188 | -0.108 |
| coverage/defence other | -0.056 | +0.020 | -0.036 |
| defence pass rush | -0.017 | +0.009 | -0.008 |
| defence run | -0.046 | -0.067 | -0.113 |
| form | -0.064 | +0.026 | -0.039 |
| record/margin | -0.030 | +0.034 | +0.005 |
| rest | -0.028 | -0.028 | -0.056 |
| run game | +0.006 | -0.006 | -0.000 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 21% of total |contribution|; top 3 carry 52%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - temp (weather family): +0.027 toward the pick
  - roof_dome (weather family): +0.013 toward the pick
  - wind (weather family): +0.000 toward the pick

The model favours BUF over HOU, driven mainly by QB and defence run. Top single driver: away_qb_cpoe (QB), BUF at the 88th league percentile, contributing +0.112 log-odds toward the pick.

### CHI @ CAR (`2026_01_CHI_CAR`)

- Approximate explanation (reproduction_max_diff=0.0370).

- Closing spread (home perspective): -3.0 — favourite: CAR
- Live pick: away (CHI), P(home cover) = 0.475
- Result: home_covered=False, correct=1

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| OL pass protection | away_ol_sack_rate | away | 0.040 | 9.4 | +0.099 |
| OL run blocking | home_ol_rush_yards_per_att | home | 4.510 | 53.1 | -0.086 |
| OL run blocking | away_ol_rush_epa_per_att | away | 0.075 | 90.6 | -0.085 |
| coverage/defence other | away_def_explosive_pass_allowed_rate | away | 0.108 | 100.0 | +0.073 |
| QB | home_pass_explosive_rate | home | 0.078 | 40.6 | -0.056 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | -0.011 | -0.140 | -0.151 |
| OL run blocking | +0.086 | +0.110 | +0.196 |
| QB | +0.109 | +0.031 | +0.140 |
| coverage/defence other | +0.029 | -0.059 | -0.030 |
| defence pass rush | +0.026 | -0.052 | -0.026 |
| defence run | -0.002 | +0.001 | -0.000 |
| form | -0.043 | +0.038 | -0.005 |
| record/margin | -0.028 | +0.035 | +0.007 |
| rest | -0.014 | -0.013 | -0.027 |
| run game | -0.022 | -0.023 | -0.045 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 22% of total |contribution|; top 3 carry 54%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - temp (weather family): +0.012 toward the pick
  - wind (weather family): +0.011 toward the pick
  - roof_dome (weather family): +0.011 toward the pick

The model favours CHI over CAR, driven mainly by OL pass protection and OL run blocking. Top single driver: away_ol_sack_rate (OL pass protection), CHI at the 9th league percentile, contributing +0.099 log-odds toward the pick.

### CLE @ JAX (`2026_01_CLE_JAX`)

- Approximate explanation (reproduction_max_diff=0.0370).

- Closing spread (home perspective): +8.5 — favourite: CLE
- Live pick: home (JAX), P(home cover) = 0.534
- Result: home_covered=True, correct=1

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| OL pass protection | away_ol_sack_rate | away | 0.084 | 78.1 | +0.128 |
| OL pass protection | away_ol_qb_hit_rate | away | 0.221 | 96.9 | +0.091 |
| QB | away_qb_cpoe | away | -5.681 | 3.1 | +0.083 |
| QB | away_ol_pass_epa_per_att | away | -0.286 | 3.1 | +0.082 |
| QB | away_qb_epa_under_pressure | away | -1.183 | 12.5 | -0.062 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | +0.006 | +0.257 | +0.263 |
| OL run blocking | -0.036 | -0.014 | -0.050 |
| QB | +0.062 | +0.109 | +0.170 |
| coverage/defence other | -0.050 | +0.050 | +0.000 |
| defence pass rush | -0.088 | +0.061 | -0.027 |
| defence run | -0.017 | -0.067 | -0.085 |
| form | -0.056 | -0.047 | -0.103 |
| record/margin | -0.024 | +0.018 | -0.007 |
| rest | -0.029 | -0.042 | -0.071 |
| run game | -0.012 | +0.016 | +0.003 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 25% of total |contribution|; top 3 carry 58%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - roof_dome (weather family): -0.017 toward the pick
  - wind (weather family): -0.005 toward the pick
  - temp (weather family): -0.004 toward the pick

The model favours JAX over CLE, driven mainly by OL pass protection and QB. Top single driver: away_ol_sack_rate (OL pass protection), CLE at the 78th league percentile, contributing +0.128 log-odds toward the pick.

### DAL @ NYG (`2026_01_DAL_NYG`)

- Approximate explanation (reproduction_max_diff=0.0370).

- Closing spread (home perspective): -3.0 — favourite: NYG
- Live pick: home (NYG), P(home cover) = 0.554
- Result: home_covered=True, correct=1

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| QB | away_qb_epa_under_pressure | away | -0.503 | 100.0 | +0.142 |
| defence run | home_def_rush_epa_allowed_per_att | home | 0.165 | 100.0 | +0.120 |
| coverage/defence other | home_def_epa_per_play | home | 0.061 | 84.4 | +0.117 |
| OL pass protection | away_ol_sack_rate | away | 0.048 | 18.8 | -0.092 |
| OL run blocking | home_ol_rush_yards_per_att | home | 4.386 | 46.9 | +0.071 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | -0.111 | -0.135 | -0.246 |
| OL run blocking | +0.063 | +0.050 | +0.113 |
| QB | +0.032 | +0.208 | +0.240 |
| coverage/defence other | +0.139 | -0.111 | +0.028 |
| defence pass rush | +0.000 | -0.023 | -0.023 |
| defence run | +0.089 | +0.078 | +0.168 |
| form | -0.071 | +0.063 | -0.007 |
| record/margin | -0.030 | +0.060 | +0.029 |
| rest | -0.004 | -0.015 | -0.019 |
| run game | -0.014 | +0.041 | +0.026 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 16% of total |contribution|; top 3 carry 47%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - temp (weather family): +0.020 toward the pick
  - roof_dome (weather family): -0.006 toward the pick
  - wind (weather family): +0.005 toward the pick

The model favours NYG over DAL, driven mainly by QB and defence run. Top single driver: away_qb_epa_under_pressure (QB), DAL at the 100th league percentile, contributing +0.142 log-odds toward the pick.

### DEN @ KC (`2026_01_DEN_KC`)

- Approximate explanation (reproduction_max_diff=0.0370).

- Closing spread (home perspective): +2.5 — favourite: DEN
- Live pick: away (DEN), P(home cover) = 0.459
- Result: home_covered=True, correct=0

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| OL pass protection | home_ol_qb_hit_rate | home | 0.194 | 81.2 | +0.097 |
| defence pass rush | away_def_sack_rate | away | 0.104 | 100.0 | -0.082 |
| form | home_rolling_3wk_epa_trend | home | 0.034 | 65.6 | +0.073 |
| defence pass rush | away_def_pressure_proxy_rate | away | 0.331 | 100.0 | -0.062 |
| defence run | home_def_rush_epa_allowed_per_att | home | -0.043 | 37.5 | +0.057 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | -0.167 | -0.046 | -0.213 |
| OL run blocking | +0.079 | +0.031 | +0.111 |
| QB | -0.027 | +0.016 | -0.011 |
| coverage/defence other | -0.008 | -0.004 | -0.012 |
| defence pass rush | +0.068 | +0.160 | +0.227 |
| defence run | -0.094 | +0.002 | -0.092 |
| form | -0.073 | +0.040 | -0.033 |
| record/margin | -0.012 | +0.025 | +0.013 |
| rest | -0.013 | -0.002 | -0.014 |
| run game | -0.026 | -0.034 | -0.060 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 18% of total |contribution|; top 3 carry 48%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - wind (weather family): -0.035 toward the pick
  - temp (weather family): +0.014 toward the pick
  - roof_dome (weather family): +0.011 toward the pick

The model favours DEN over KC, driven mainly by OL pass protection and defence pass rush. Top single driver: home_ol_qb_hit_rate (OL pass protection), KC at the 81st league percentile, contributing +0.097 log-odds toward the pick.

### GB @ MIN (`2026_01_GB_MIN`)

- **SIDE MISMATCH** — the underlying (approximate) explanation model leans AWAY; the live served pick is HOME. Excluded from every "toward the pick" aggregate below.
- Approximate explanation (reproduction_max_diff=0.0370).

- Closing spread (home perspective): +1.5 — favourite: GB
- Live pick: home (MIN), P(home cover) = 0.530
- Result: home_covered=True, correct=1

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| defence pass rush | home_def_qb_hit_rate | home | 0.192 | 96.9 | +0.137 |
| QB | away_qb_cpoe | away | 5.950 | 96.9 | -0.122 |
| weather | roof_dome | game | 1.000 | n/a | +0.084 |
| coverage/defence other | away_def_explosive_pass_allowed_rate | away | 0.071 | 21.9 | +0.078 |
| OL pass protection | home_ol_qb_hit_rate | home | 0.225 | 100.0 | +0.072 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | +0.039 | -0.031 | +0.008 |
| OL run blocking | +0.007 | +0.009 | +0.016 |
| QB | +0.007 | -0.124 | -0.117 |
| coverage/defence other | -0.100 | +0.091 | -0.010 |
| defence pass rush | +0.204 | -0.089 | +0.115 |
| defence run | -0.014 | -0.025 | -0.040 |
| form | +0.019 | +0.012 | +0.031 |
| record/margin | -0.021 | +0.028 | +0.007 |
| rest | -0.014 | -0.008 | -0.022 |
| run game | -0.034 | +0.002 | -0.032 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 21% of total |contribution|; top 3 carry 53%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - roof_dome (weather family): +0.084 toward the pick
  - wind (weather family): -0.022 toward the pick
  - temp (weather family): +0.016 toward the pick

The model favours MIN over GB, driven mainly by defence pass rush and QB. Top single driver: home_def_qb_hit_rate (defence pass rush), MIN at the 97th league percentile, contributing +0.137 log-odds toward the pick.

### MIA @ LV (`2026_01_MIA_LV`)

- Approximate explanation (reproduction_max_diff=0.0370).

- Closing spread (home perspective): +3.0 — favourite: MIA
- Live pick: away (MIA), P(home cover) = 0.469
- Result: home_covered=True, correct=0

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| form | home_rolling_3wk_epa_trend | home | -0.215 | 3.1 | -0.171 |
| weather | roof_dome | game | 1.000 | n/a | -0.107 |
| run game | home_rush_explosive_rate | home | 0.085 | 6.2 | -0.102 |
| QB | away_qb_epa_under_pressure | away | -1.032 | 34.4 | +0.076 |
| OL pass protection | home_ol_qb_hit_rate | home | 0.196 | 87.5 | +0.074 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | -0.064 | +0.008 | -0.055 |
| OL run blocking | -0.103 | +0.007 | -0.096 |
| QB | +0.106 | -0.058 | +0.048 |
| coverage/defence other | -0.059 | -0.017 | -0.076 |
| defence pass rush | -0.036 | -0.105 | -0.141 |
| defence run | -0.056 | -0.024 | -0.079 |
| form | +0.171 | +0.006 | +0.176 |
| record/margin | -0.031 | +0.039 | +0.008 |
| rest | -0.014 | -0.009 | -0.023 |
| run game | +0.102 | -0.015 | +0.088 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 20% of total |contribution|; top 3 carry 45%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - roof_dome (weather family): -0.107 toward the pick
  - wind (weather family): +0.010 toward the pick
  - temp (weather family): -0.010 toward the pick

The model favours MIA over LV, driven mainly by form and weather. Top single driver: home_rolling_3wk_epa_trend (form), LV at the 3rd league percentile, contributing -0.171 log-odds toward the pick.

### NE @ SEA (`2026_01_NE_SEA`)

- **Regenerated after kickoff** (`clean_forward=false`) — not a clean forward pick.
- Approximate explanation (reproduction_max_diff=0.0370).

- Closing spread (home perspective): +3.0 — favourite: NE
- Live pick: away (NE), P(home cover) = 0.460
- Result: home_covered=push, correct=n/a

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| QB | away_qb_cpoe | away | 10.681 | 100.0 | +0.306 |
| QB | away_qb_epa_under_pressure | away | -0.667 | 93.8 | -0.206 |
| defence run | home_def_rush_yards_allowed_per_att | home | 3.832 | 3.1 | -0.162 |
| QB | away_pass_explosive_rate | away | 0.125 | 100.0 | +0.065 |
| coverage/defence other | home_def_epa_per_play | home | -0.137 | 3.1 | +0.064 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | +0.040 | +0.009 | +0.050 |
| OL run blocking | -0.043 | -0.013 | -0.057 |
| QB | -0.056 | -0.203 | -0.258 |
| coverage/defence other | -0.086 | +0.005 | -0.081 |
| defence pass rush | +0.023 | -0.044 | -0.020 |
| defence run | +0.147 | +0.002 | +0.150 |
| form | -0.039 | +0.019 | -0.019 |
| record/margin | -0.020 | +0.041 | +0.021 |
| rest | -0.011 | -0.033 | -0.044 |
| run game | +0.005 | -0.010 | -0.005 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 43% of total |contribution|; top 3 carry 71%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - temp (weather family): -0.018 toward the pick
  - roof_dome (weather family): +0.013 toward the pick
  - wind (weather family): +0.003 toward the pick

The model favours NE over SEA, driven mainly by QB and defence run. Top single driver: away_qb_cpoe (QB), NE at the 100th league percentile, contributing +0.306 log-odds toward the pick.

### NO @ DET (`2026_01_NO_DET`)

- Approximate explanation (reproduction_max_diff=0.0370).

- Closing spread (home perspective): +7.0 — favourite: NO
- Live pick: away (NO), P(home cover) = 0.414
- Result: home_covered=False, correct=1

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| OL pass protection | away_ol_sack_rate | away | 0.077 | 68.8 | -0.099 |
| defence pass rush | away_def_pressure_proxy_rate | away | 0.234 | 56.2 | +0.081 |
| weather | roof_dome | game | 1.000 | n/a | -0.074 |
| form | home_rolling_3wk_epa_trend | home | 0.081 | 81.2 | +0.073 |
| OL pass protection | home_ol_qb_hit_rate | home | 0.192 | 78.1 | +0.070 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | -0.132 | +0.052 | -0.080 |
| OL run blocking | +0.029 | -0.027 | +0.002 |
| QB | +0.016 | -0.002 | +0.014 |
| coverage/defence other | -0.045 | +0.001 | -0.045 |
| defence pass rush | +0.029 | -0.079 | -0.050 |
| defence run | -0.071 | +0.007 | -0.064 |
| form | -0.073 | -0.023 | -0.096 |
| record/margin | -0.014 | +0.039 | +0.026 |
| rest | -0.018 | -0.015 | -0.034 |
| run game | -0.020 | +0.031 | +0.010 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 21% of total |contribution|; top 3 carry 52%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - roof_dome (weather family): -0.074 toward the pick
  - temp (weather family): -0.017 toward the pick
  - wind (weather family): +0.013 toward the pick

The model favours NO over DET, driven mainly by OL pass protection and defence pass rush. Top single driver: away_ol_sack_rate (OL pass protection), NO at the 69th league percentile, contributing -0.099 log-odds toward the pick.

### NYJ @ TEN (`2026_01_NYJ_TEN`)

- **SIDE MISMATCH** — the underlying (approximate) explanation model leans HOME; the live served pick is AWAY. Excluded from every "toward the pick" aggregate below.
- Approximate explanation (reproduction_max_diff=0.0370).

- Closing spread (home perspective): +1.5 — favourite: NYJ
- Live pick: away (NYJ), P(home cover) = 0.495
- Result: home_covered=False, correct=1

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| coverage/defence other | away_def_pass_epa_allowed_per_att | away | 0.254 | 100.0 | +0.113 |
| form | away_rolling_3wk_epa_trend | away | -0.132 | 12.5 | +0.106 |
| coverage/defence other | home_def_epa_per_play | home | 0.056 | 78.1 | -0.102 |
| OL pass protection | away_ol_sack_rate | away | 0.109 | 93.8 | -0.094 |
| QB | away_qb_cpoe | away | -4.105 | 6.2 | -0.086 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | -0.121 | +0.187 | +0.067 |
| OL run blocking | -0.020 | -0.018 | -0.038 |
| QB | +0.015 | +0.026 | +0.041 |
| coverage/defence other | +0.122 | -0.199 | -0.078 |
| defence pass rush | +0.015 | +0.118 | +0.133 |
| defence run | +0.040 | +0.040 | +0.080 |
| form | +0.042 | -0.106 | -0.064 |
| record/margin | -0.022 | +0.029 | +0.006 |
| rest | -0.030 | -0.021 | -0.051 |
| run game | -0.025 | -0.001 | -0.026 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 29% of total |contribution|; top 3 carry 63%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - wind (weather family): +0.012 toward the pick
  - roof_dome (weather family): +0.010 toward the pick
  - temp (weather family): -0.006 toward the pick

The model favours NYJ over TEN, driven mainly by coverage/defence other and form. Top single driver: away_def_pass_epa_allowed_per_att (coverage/defence other), NYJ at the 100th league percentile, contributing +0.113 log-odds toward the pick.

### SF @ LA (`2026_01_SF_LA`)

- **Regenerated after kickoff** (`clean_forward=false`) — not a clean forward pick.
- Approximate explanation (reproduction_max_diff=0.0370).

- Closing spread (home perspective): +3.5 — favourite: SF
- Live pick: away (SF), P(home cover) = 0.495
- Result: home_covered=False, correct=1

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| QB | away_qb_cpoe | away | 5.434 | 93.8 | +0.163 |
| defence run | away_def_explosive_rush_allowed_rate | away | 0.090 | 15.6 | +0.112 |
| OL pass protection | away_ol_sack_rate | away | 0.045 | 12.5 | +0.082 |
| QB | home_pass_explosive_rate | home | 0.117 | 96.9 | +0.080 |
| weather | roof_dome | game | 1.000 | n/a | -0.074 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | +0.120 | -0.110 | +0.010 |
| OL run blocking | +0.034 | +0.026 | +0.060 |
| QB | -0.008 | -0.202 | -0.210 |
| coverage/defence other | -0.036 | +0.014 | -0.022 |
| defence pass rush | +0.088 | +0.045 | +0.133 |
| defence run | -0.061 | -0.099 | -0.160 |
| form | -0.012 | +0.030 | +0.018 |
| record/margin | -0.026 | +0.043 | +0.017 |
| rest | -0.011 | -0.017 | -0.028 |
| run game | -0.030 | +0.060 | +0.030 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 24% of total |contribution|; top 3 carry 54%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - roof_dome (weather family): -0.074 toward the pick
  - wind (weather family): +0.027 toward the pick
  - temp (weather family): -0.025 toward the pick

The model favours SF over LA, driven mainly by QB and defence run. Top single driver: away_qb_cpoe (QB), SF at the 94th league percentile, contributing +0.163 log-odds toward the pick.

### TB @ CIN (`2026_01_TB_CIN`)

- Approximate explanation (reproduction_max_diff=0.0370).

- Closing spread (home perspective): +3.5 — favourite: TB
- Live pick: home (CIN), P(home cover) = 0.528
- Result: home_covered=True, correct=1

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| defence run | home_def_rush_epa_allowed_per_att | home | 0.085 | 90.6 | +0.166 |
| coverage/defence other | home_def_epa_per_play | home | 0.089 | 90.6 | +0.068 |
| form | home_rolling_3wk_epa_trend | home | -0.008 | 40.6 | -0.065 |
| QB | away_qb_cpoe | away | -2.483 | 21.9 | +0.061 |
| defence run | away_def_rush_epa_allowed_per_att | away | -0.072 | 12.5 | -0.054 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | +0.015 | -0.040 | -0.025 |
| OL run blocking | +0.041 | +0.026 | +0.068 |
| QB | +0.118 | +0.003 | +0.121 |
| coverage/defence other | +0.103 | +0.048 | +0.152 |
| defence pass rush | -0.051 | -0.045 | -0.095 |
| defence run | +0.145 | -0.068 | +0.077 |
| form | -0.065 | +0.044 | -0.021 |
| record/margin | -0.006 | +0.041 | +0.035 |
| rest | -0.006 | -0.013 | -0.019 |
| run game | -0.001 | -0.019 | -0.020 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 23% of total |contribution|; top 3 carry 59%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - roof_dome (weather family): -0.017 toward the pick
  - temp (weather family): +0.015 toward the pick
  - wind (weather family): +0.006 toward the pick

The model favours CIN over TB, driven mainly by defence run and coverage/defence other. Top single driver: home_def_rush_epa_allowed_per_att (defence run), CIN at the 91st league percentile, contributing +0.166 log-odds toward the pick.

### WAS @ PHI (`2026_01_WAS_PHI`)

- Approximate explanation (reproduction_max_diff=0.0370).

- Closing spread (home perspective): +6.0 — favourite: WAS
- Live pick: away (WAS), P(home cover) = 0.329
- Result: home_covered=False, correct=1

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| coverage/defence other | away_def_pass_epa_allowed_per_att | away | 0.201 | 93.8 | +0.108 |
| defence pass rush | away_def_sack_rate | away | 0.072 | 59.4 | +0.071 |
| coverage/defence other | away_def_epa_per_play | away | 0.113 | 96.9 | +0.062 |
| form | home_rolling_3wk_epa_trend | home | 0.027 | 56.2 | +0.059 |
| QB | away_ol_pass_epa_per_att | away | -0.006 | 46.9 | +0.059 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | -0.018 | +0.015 | -0.004 |
| OL run blocking | -0.001 | +0.014 | +0.013 |
| QB | -0.012 | -0.048 | -0.060 |
| coverage/defence other | -0.050 | -0.123 | -0.173 |
| defence pass rush | +0.027 | -0.148 | -0.121 |
| defence run | -0.062 | -0.029 | -0.091 |
| form | -0.059 | -0.020 | -0.079 |
| record/margin | -0.023 | +0.039 | +0.017 |
| rest | -0.013 | -0.011 | -0.024 |
| run game | -0.019 | -0.006 | -0.026 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 25% of total |contribution|; top 3 carry 57%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - temp (weather family): -0.019 toward the pick
  - roof_dome (weather family): +0.012 toward the pick
  - wind (weather family): +0.005 toward the pick

The model favours WAS over PHI, driven mainly by coverage/defence other and defence pass rush. Top single driver: away_def_pass_epa_allowed_per_att (coverage/defence other), WAS at the 94th league percentile, contributing +0.108 log-odds toward the pick.

## 2. Patterns across the games

**Mean |contribution| by family, and how often it pushed toward the picked side:**

| Family | Mean |contribution| | Toward pick (all games) | Toward pick (excl. side-mismatches) |
|---|---|---|---|
| OL pass protection | 0.1189 | 50% (n=16) | 54% (n=13) |
| QB | 0.1091 | 69% (n=16) | 77% (n=13) |
| defence run | 0.0884 | 56% (n=16) | 69% (n=13) |
| defence pass rush | 0.0823 | 62% (n=16) | 62% (n=13) |
| coverage/defence other | 0.0592 | 81% (n=16) | 85% (n=13) |
| OL run blocking | 0.0587 | 50% (n=16) | 38% (n=13) |
| form | 0.0487 | 56% (n=16) | 54% (n=13) |
| weather | 0.0408 | 50% (n=16) | 46% (n=13) |
| rest | 0.0318 | 62% (n=16) | 69% (n=13) |
| run game | 0.0286 | 62% (n=16) | 69% (n=13) |
| record/margin | 0.0144 | 31% (n=16) | 23% (n=13) |
| venue/context | 0.0040 | 44% (n=16) | 46% (n=13) |

**Groups by pick-direction contribution vector (hierarchical, cosine distance, average linkage):**

- Group 1 — dominant: QB, OL pass protection — games: 2026_01_ATL_PIT, 2026_01_BAL_IND, 2026_01_BUF_HOU, 2026_01_DAL_NYG, 2026_01_NE_SEA, 2026_01_SF_LA, 2026_01_TB_CIN
- Group 2 — dominant: defence pass rush, defence run — games: 2026_01_NYJ_TEN
- Group 3 — dominant: OL pass protection, OL run blocking — games: 2026_01_ARI_LAC, 2026_01_CHI_CAR, 2026_01_CLE_JAX, 2026_01_DEN_KC
- Group 4 — dominant: coverage/defence other, form — games: 2026_01_NO_DET, 2026_01_WAS_PHI
- Group 5 — dominant: form, defence pass rush — games: 2026_01_MIA_LV
- Group 6 — dominant: QB, defence pass rush — games: 2026_01_GB_MIN

**Recurring top-driver shapes (family + side of the #1 driver):**

- QB (away) — 5 game(s): 2026_01_BAL_IND (away), 2026_01_BUF_HOU (away), 2026_01_DAL_NYG (home), 2026_01_NE_SEA (away), 2026_01_SF_LA (away)
- OL pass protection (away) — 4 game(s): 2026_01_ATL_PIT (home), 2026_01_CHI_CAR (away), 2026_01_CLE_JAX (home), 2026_01_NO_DET (away)
- OL pass protection (home) — 2 game(s): 2026_01_ARI_LAC (home), 2026_01_DEN_KC (away)
- coverage/defence other (away) — 2 game(s): 2026_01_NYJ_TEN (away), 2026_01_WAS_PHI (away)
- defence pass rush (home) — 1 game(s): 2026_01_GB_MIN (home)
- defence run (home) — 1 game(s): 2026_01_TB_CIN (home)
- form (home) — 1 game(s): 2026_01_MIA_LV (away)

## 3. Against the market

**Model P(home cover) vs. closing spread, per game (sorted by disagreement with the market):**

| Game | Closing spread | Favourite | Pick | P(home cover) | |P-0.5| |
|---|---|---|---|---|---|
| 2026_01_WAS_PHI | +6.0 | WAS | away | 0.329 | 0.171 |
| 2026_01_NO_DET | +7.0 | NO | away | 0.414 | 0.086 |
| 2026_01_DAL_NYG | -3.0 | NYG | home | 0.554 | 0.054 |
| 2026_01_BUF_HOU | -1.5 | HOU | away | 0.448 | 0.052 |
| 2026_01_DEN_KC | +2.5 | DEN | away | 0.459 | 0.041 |
| 2026_01_NE_SEA | +3.0 | NE | away | 0.460 | 0.040 |
| 2026_01_ARI_LAC | +9.5 | ARI | home | 0.537 | 0.037 |
| 2026_01_CLE_JAX | +8.5 | CLE | home | 0.534 | 0.034 |
| 2026_01_MIA_LV | +3.0 | MIA | away | 0.469 | 0.031 |
| 2026_01_GB_MIN | +1.5 | GB | home | 0.530 | 0.030 |
| 2026_01_TB_CIN | +3.5 | TB | home | 0.528 | 0.028 |
| 2026_01_CHI_CAR | -3.0 | CAR | away | 0.475 | 0.025 |
| 2026_01_ATL_PIT | +5.5 | ATL | home | 0.511 | 0.011 |
| 2026_01_SF_LA | +3.5 | SF | away | 0.495 | 0.005 |
| 2026_01_NYJ_TEN | +1.5 | NYJ | away | 0.495 | 0.005 |
| 2026_01_BAL_IND | -3.5 | IND | away | 0.499 | 0.001 |

Families driving the largest market disagreements:
- 2026_01_WAS_PHI (|P-0.5|=0.171): top family coverage/defence other (25% of total |contribution|)
- 2026_01_NO_DET (|P-0.5|=0.086): top family OL pass protection (21% of total |contribution|)
- 2026_01_DAL_NYG (|P-0.5|=0.054): top family QB (16% of total |contribution|)

**Underdog picks: 8 of 16.**

Families pushing toward the pick specifically on underdog picks:

| Family | Toward pick (all underdog picks) | Toward pick (excl. mismatches) |
|---|---|---|
| OL pass protection | 50% (n=8) | 50% (n=6) |
| QB | 75% (n=8) | 83% (n=6) |
| defence run | 38% (n=8) | 50% (n=6) |
| defence pass rush | 75% (n=8) | 67% (n=6) |
| OL run blocking | 50% (n=8) | 33% (n=6) |
| coverage/defence other | 62% (n=8) | 67% (n=6) |
| weather | 75% (n=8) | 83% (n=6) |
| rest | 38% (n=8) | 50% (n=6) |
| form | 50% (n=8) | 50% (n=6) |
| run game | 62% (n=8) | 83% (n=6) |
| record/margin | 50% (n=8) | 33% (n=6) |
| venue/context | 50% (n=8) | 50% (n=6) |

**Around key numbers:** 8 game(s) within 0.5 of a 3-point spread (2026_01_BAL_IND, 2026_01_CHI_CAR, 2026_01_DAL_NYG, 2026_01_DEN_KC, 2026_01_MIA_LV, 2026_01_NE_SEA, 2026_01_SF_LA, 2026_01_TB_CIN); 1 game(s) within 0.5 of a 7-point spread (2026_01_NO_DET).

Line movement: `raw_lines.line_snapshots` has no rows for this week (snapshots only began 2026-09-09 and none have been captured yet for this slate).

Moneyline population by season — 2015: 267/267, 2016: 267/267, 2017: 266/267, 2018: 267/267, 2019: 267/267, 2020: 269/269, 2021: 285/285, 2022: 284/284, 2023: 285/285, 2024: 285/285, 2025: 285/285, 2026: 32/272. 2026 week 1 is fully populated for this slate; de-vigged market probability shown below.

| Game | Home devigged win prob (moneyline) | Model P(home cover) |
|---|---|---|
| 2026_01_NO_DET | 0.734 | 0.414 |
| 2026_01_SF_LA | 0.657 | 0.495 |
| 2026_01_DAL_NYG | 0.400 | 0.554 |
| 2026_01_WAS_PHI | 0.681 | 0.329 |
| 2026_01_ATL_PIT | 0.718 | 0.511 |
| 2026_01_BUF_HOU | 0.496 | 0.448 |
| 2026_01_DEN_KC | 0.543 | 0.459 |
| 2026_01_MIA_LV | 0.604 | 0.469 |
| 2026_01_NYJ_TEN | 0.517 | 0.495 |
| 2026_01_TB_CIN | 0.645 | 0.528 |
| 2026_01_NE_SEA | 0.600 | 0.460 |
| 2026_01_CHI_CAR | 0.400 | 0.475 |
| 2026_01_BAL_IND | 0.407 | 0.499 |
| 2026_01_CLE_JAX | 0.791 | 0.534 |
| 2026_01_ARI_LAC | 0.787 | 0.537 |
| 2026_01_GB_MIN | 0.532 | 0.530 |
Note: moneyline win probability and P(home cover) measure different things (straight-up win vs. ATS cover) — shown side by side, not equated.

**Per-family correlation with the closing spread (home-cover-oriented, not pick-direction):**

| Family | n games | corr with closing spread |
|---|---|---|
| OL run blocking | 16 | -0.529 |
| defence run | 16 | -0.478 |
| weather | 16 | 0.450 |
| OL pass protection | 16 | 0.353 |
| form | 16 | -0.300 |
| coverage/defence other | 16 | -0.283 |
| run game | 16 | 0.196 |
| rest | 16 | -0.156 |
| record/margin | 16 | 0.093 |
| venue/context | 16 | 0.047 |
| defence pass rush | 16 | 0.009 |
| QB | 16 | 0.007 |

## 4. Hand-off list — testable on 2015-2025

1. Picks where coverage/defence other is the top driver and it pushed toward the pick (true in 85% of the 13 non-mismatched games) — test ATS performance on 2015-2025 for games where this family is the #1 driver.
2. Picks where QB is the top driver and it pushed toward the pick (true in 77% of the 13 non-mismatched games) — test ATS performance on 2015-2025 for games where this family is the #1 driver.
3. OL run blocking correlates most with the closing spread (r=-0.53) and is largely repeating the market — test whether excluding it from the feature set changes backtest log loss.
4. QB correlates least with the closing spread (r=0.01) — test whether picks driven by this family beat the market ATS on 2015-2025, independent of the spread.
5. Picks where the model backs the underdog and QB is the top driver — test ATS performance on 2015-2025 for underdog picks split by this family's direction.
6. Games whose #1 driver is QB on the away side (5 of this week's games) — test whether this shape recurs and beats the market ATS on 2015-2025.
7. Games within half a point of the 3 or 7 key numbers — test whether the model's calibration (P(cover) vs. actual cover rate) differs near these numbers on 2015-2025.
