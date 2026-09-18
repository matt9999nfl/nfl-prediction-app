# Week analysis — 2026 week 2

Week 2's explanations are exact reproductions of the live picks.

No games disagree on side between the underlying explanation model and the live served pick.

No games in this week were regenerated after kickoff.

Week 2 has not finished playing — result columns are left empty by design.

## 1. Game by game

### CAR @ ATL (`2026_02_CAR_ATL`)

- Line at pick time (home perspective): -1.5 · Closing line: -1.5 — favourite (by closing line): CAR
- Live pick: away (CAR), P(home cover) = 0.432
- Result: home_covered=not yet played, correct=n/a

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| QB | home_qb_cpoe_blend | home | -3.736 | 6.2 | +0.186 |
| QB | away_qb_epa_under_pressure_blend | away | -0.747 | 81.2 | -0.100 |
| OL pass protection | home_ol_pressure_proxy_rate_blend | home | 0.190 | 31.2 | -0.079 |
| defence pass rush | away_def_qb_hit_rate_blend | away | 0.099 | 3.1 | +0.065 |
| coverage/defence other | away_def_epa_per_play_blend | away | 0.093 | 93.8 | +0.061 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | +0.121 | +0.044 | +0.165 |
| OL run blocking | +0.068 | -0.006 | +0.062 |
| QB | -0.161 | +0.103 | -0.058 |
| coverage/defence other | -0.039 | -0.072 | -0.111 |
| defence pass rush | +0.027 | -0.089 | -0.062 |
| defence run | -0.033 | -0.047 | -0.080 |
| form | -0.005 | -0.055 | -0.060 |
| record/margin | -0.050 | +0.007 | -0.043 |
| rest | +0.005 | +0.002 | +0.006 |
| run game | -0.026 | +0.005 | -0.021 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 29% of total |contribution|; top 3 carry 54%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - temp (weather family): +0.009 toward the pick
  - roof_dome (weather family): +0.003 toward the pick
  - wind (weather family): -0.000 toward the pick

The model favours CAR over ATL, driven mainly by QB and OL pass protection. Top single driver: home_qb_cpoe_blend (QB), ATL at the 6th league percentile, contributing +0.186 log-odds toward the pick.

### CIN @ HOU (`2026_02_CIN_HOU`)

- Line at pick time (home perspective): +3.0 · Closing line: +3.0 — favourite (by closing line): HOU
- Live pick: away (CIN), P(home cover) = 0.398
- Result: home_covered=not yet played, correct=n/a

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| coverage/defence other | away_def_explosive_pass_allowed_rate_blend | away | 0.101 | 93.8 | +0.123 |
| OL pass protection | away_ol_sack_rate_blend | away | 0.051 | 18.8 | +0.118 |
| run game | home_rush_explosive_rate_blend | home | 0.097 | 15.6 | -0.100 |
| OL pass protection | home_ol_pressure_proxy_rate_blend | home | 0.193 | 34.4 | -0.077 |
| OL run blocking | home_ol_rush_yards_per_att_blend | home | 4.007 | 12.5 | +0.071 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | +0.121 | -0.113 | +0.008 |
| OL run blocking | -0.074 | +0.001 | -0.073 |
| QB | +0.011 | +0.015 | +0.025 |
| coverage/defence other | -0.064 | -0.114 | -0.178 |
| defence pass rush | -0.059 | -0.018 | -0.077 |
| defence run | -0.057 | -0.023 | -0.080 |
| form | -0.059 | -0.002 | -0.061 |
| record/margin | -0.029 | +0.007 | -0.022 |
| rest | +0.016 | -0.003 | +0.013 |
| run game | +0.100 | -0.001 | +0.099 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 19% of total |contribution|; top 3 carry 52%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - temp (weather family): +0.014 toward the pick
  - roof_dome (weather family): +0.007 toward the pick
  - wind (weather family): -0.002 toward the pick

The model favours CIN over HOU, driven mainly by coverage/defence other and OL pass protection. Top single driver: away_def_explosive_pass_allowed_rate_blend (coverage/defence other), CIN at the 94th league percentile, contributing +0.123 log-odds toward the pick.

### CLE @ TB (`2026_02_CLE_TB`)

- Line at pick time (home perspective): +8.5 · Closing line: +8.5 — favourite (by closing line): TB
- Live pick: home (TB), P(home cover) = 0.538
- Result: home_covered=not yet played, correct=n/a

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| QB | away_qb_epa_under_pressure_blend | away | -1.311 | 6.2 | -0.214 |
| OL pass protection | away_ol_sack_rate_blend | away | 0.093 | 84.4 | +0.176 |
| QB | away_qb_cpoe_blend | away | -4.365 | 3.1 | +0.108 |
| QB | home_qb_epa_under_pressure_blend | home | -1.706 | 3.1 | -0.107 |
| OL pass protection | away_ol_pressure_proxy_rate_blend | away | 0.320 | 96.9 | +0.101 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | +0.038 | +0.356 | +0.394 |
| OL run blocking | +0.054 | +0.009 | +0.063 |
| QB | -0.089 | -0.072 | -0.161 |
| coverage/defence other | -0.003 | -0.014 | -0.016 |
| defence pass rush | -0.003 | +0.188 | +0.186 |
| defence run | -0.076 | -0.061 | -0.137 |
| form | -0.045 | -0.091 | -0.137 |
| record/margin | -0.034 | +0.014 | -0.020 |
| rest | +0.009 | +0.004 | +0.013 |
| run game | +0.002 | +0.053 | +0.055 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 28% of total |contribution|; top 3 carry 66%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - temp (weather family): -0.023 toward the pick
  - wind (weather family): -0.010 toward the pick
  - roof_dome (weather family): -0.007 toward the pick

The model favours TB over CLE, driven mainly by QB and OL pass protection. Top single driver: away_qb_epa_under_pressure_blend (QB), CLE at the 6th league percentile, contributing -0.214 log-odds toward the pick.

### DET @ BUF (`2026_02_DET_BUF`)

- Line at pick time (home perspective): +4.5 · Closing line: +4.5 — favourite (by closing line): BUF
- Live pick: away (DET), P(home cover) = 0.489
- Result: home_covered=not yet played, correct=n/a

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| QB | home_pass_explosive_rate_blend | home | 0.119 | 100.0 | +0.415 |
| defence pass rush | away_def_sack_rate_blend | away | 0.082 | 87.5 | -0.161 |
| QB | away_qb_epa_under_pressure_blend | away | -0.713 | 90.6 | -0.138 |
| coverage/defence other | away_def_explosive_pass_allowed_rate_blend | away | 0.097 | 90.6 | +0.117 |
| defence pass rush | home_def_qb_hit_rate_blend | home | 0.179 | 90.6 | -0.091 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | -0.067 | +0.073 | +0.006 |
| OL run blocking | +0.016 | -0.007 | +0.010 |
| QB | -0.424 | +0.112 | -0.311 |
| coverage/defence other | +0.014 | -0.041 | -0.027 |
| defence pass rush | +0.097 | +0.225 | +0.322 |
| defence run | -0.003 | +0.017 | +0.015 |
| form | -0.025 | -0.038 | -0.064 |
| record/margin | +0.096 | -0.032 | +0.064 |
| rest | +0.004 | +0.014 | +0.018 |
| run game | -0.014 | +0.001 | -0.013 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 36% of total |contribution|; top 3 carry 68%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - temp (weather family): +0.007 toward the pick
  - roof_dome (weather family): +0.004 toward the pick
  - wind (weather family): +0.002 toward the pick

The model favours DET over BUF, driven mainly by QB and defence pass rush. Top single driver: home_pass_explosive_rate_blend (QB), BUF at the 100th league percentile, contributing +0.415 log-odds toward the pick.

### GB @ NYJ (`2026_02_GB_NYJ`)

- Line at pick time (home perspective): -4.5 · Closing line: -4.5 — favourite (by closing line): GB
- Live pick: away (GB), P(home cover) = 0.500
- Result: home_covered=not yet played, correct=n/a

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| coverage/defence other | away_def_explosive_pass_allowed_rate_blend | away | 0.068 | 12.5 | -0.158 |
| defence run | away_def_explosive_rush_allowed_rate_blend | away | 0.078 | 6.2 | +0.147 |
| QB | away_qb_epa_under_pressure_blend | away | -0.739 | 84.4 | -0.136 |
| form | away_rolling_3wk_epa_trend_blend | away | -0.131 | 34.4 | +0.111 |
| defence pass rush | home_def_qb_hit_rate_blend | home | 0.112 | 6.2 | -0.104 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | -0.158 | +0.021 | -0.138 |
| OL run blocking | -0.008 | -0.064 | -0.073 |
| QB | +0.142 | +0.098 | +0.240 |
| coverage/defence other | +0.093 | +0.114 | +0.208 |
| defence pass rush | +0.153 | -0.013 | +0.139 |
| defence run | +0.061 | -0.140 | -0.079 |
| form | -0.007 | -0.111 | -0.118 |
| record/margin | -0.101 | +0.025 | -0.076 |
| rest | +0.004 | +0.003 | +0.007 |
| run game | -0.006 | -0.021 | -0.026 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 23% of total |contribution|; top 3 carry 52%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - temp (weather family): +0.020 toward the pick
  - roof_dome (weather family): +0.007 toward the pick
  - wind (weather family): +0.006 toward the pick

The model favours GB over NYJ, driven mainly by coverage/defence other and defence run. Top single driver: away_def_explosive_pass_allowed_rate_blend (coverage/defence other), GB at the 12th league percentile, contributing -0.158 log-odds toward the pick.

### IND @ KC (`2026_02_IND_KC`)

- Line at pick time (home perspective): +6.5 · Closing line: +6.5 — favourite (by closing line): KC
- Live pick: home (KC), P(home cover) = 0.560
- Result: home_covered=not yet played, correct=n/a

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| QB | home_qb_epa_under_pressure_blend | home | -0.529 | 96.9 | +0.116 |
| defence pass rush | home_def_qb_hit_rate_blend | home | 0.177 | 87.5 | +0.107 |
| OL pass protection | away_ol_sack_rate_blend | away | 0.052 | 21.9 | -0.099 |
| form | away_rolling_3wk_epa_trend_blend | away | -0.173 | 15.6 | -0.074 |
| form | home_rolling_3wk_epa_trend_blend | home | -0.168 | 18.8 | +0.070 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | -0.065 | -0.093 | -0.158 |
| OL run blocking | +0.028 | +0.028 | +0.056 |
| QB | +0.161 | -0.039 | +0.121 |
| coverage/defence other | +0.005 | -0.003 | +0.001 |
| defence pass rush | +0.136 | +0.052 | +0.188 |
| defence run | -0.014 | +0.009 | -0.006 |
| form | +0.070 | -0.074 | -0.004 |
| record/margin | +0.039 | +0.068 | +0.106 |
| rest | +0.009 | +0.002 | +0.011 |
| run game | -0.016 | -0.013 | -0.030 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 22% of total |contribution|; top 3 carry 52%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - temp (weather family): -0.008 toward the pick
  - roof_dome (weather family): -0.005 toward the pick
  - wind (weather family): -0.004 toward the pick

The model favours KC over IND, driven mainly by QB and defence pass rush. Top single driver: home_qb_epa_under_pressure_blend (QB), KC at the 97th league percentile, contributing +0.116 log-odds toward the pick.

### JAX @ DEN (`2026_02_JAX_DEN`)

- Line at pick time (home perspective): +2.5 · Closing line: +2.5 — favourite (by closing line): DEN
- Live pick: home (DEN), P(home cover) = 0.572
- Result: home_covered=not yet played, correct=n/a

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| form | away_rolling_3wk_epa_trend_blend | away | 0.188 | 87.5 | +0.175 |
| OL pass protection | home_ol_pressure_proxy_rate_blend | home | 0.159 | 6.2 | -0.159 |
| defence run | away_def_explosive_rush_allowed_rate_blend | away | 0.089 | 15.6 | -0.146 |
| defence pass rush | home_def_qb_hit_rate_blend | home | 0.222 | 100.0 | +0.111 |
| defence pass rush | home_def_sack_rate_blend | home | 0.101 | 100.0 | +0.092 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | -0.129 | -0.028 | -0.156 |
| OL run blocking | +0.039 | -0.054 | -0.015 |
| QB | +0.151 | +0.124 | +0.275 |
| coverage/defence other | -0.042 | +0.092 | +0.050 |
| defence pass rush | +0.244 | -0.013 | +0.232 |
| defence run | +0.011 | -0.217 | -0.206 |
| form | +0.049 | +0.175 | +0.224 |
| record/margin | +0.028 | -0.089 | -0.061 |
| rest | +0.006 | -0.002 | +0.004 |
| run game | -0.002 | +0.012 | +0.010 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 16% of total |contribution|; top 3 carry 45%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - temp (weather family): -0.031 toward the pick
  - wind (weather family): -0.005 toward the pick
  - roof_dome (weather family): -0.004 toward the pick

The model favours DEN over JAX, driven mainly by form and OL pass protection. Top single driver: away_rolling_3wk_epa_trend_blend (form), JAX at the 88th league percentile, contributing +0.175 log-odds toward the pick.

### LV @ LAC (`2026_02_LV_LAC`)

- Line at pick time (home perspective): +7.0 · Closing line: +7.0 — favourite (by closing line): LAC
- Live pick: home (LAC), P(home cover) = 0.592
- Result: home_covered=not yet played, correct=n/a

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| form | home_rolling_3wk_epa_trend_blend | home | -0.291 | 3.1 | +0.306 |
| OL pass protection | away_ol_sack_rate_blend | away | 0.100 | 96.9 | +0.127 |
| form | away_rolling_3wk_epa_trend_blend | away | -0.248 | 6.2 | -0.093 |
| defence pass rush | away_def_sack_rate_blend | away | 0.076 | 75.0 | -0.078 |
| coverage/defence other | away_def_explosive_pass_allowed_rate_blend | away | 0.076 | 34.4 | +0.077 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | -0.093 | +0.158 | +0.065 |
| OL run blocking | +0.077 | -0.066 | +0.012 |
| QB | +0.137 | +0.019 | +0.156 |
| coverage/defence other | -0.019 | +0.087 | +0.068 |
| defence pass rush | +0.064 | -0.064 | -0.000 |
| defence run | -0.055 | -0.125 | -0.180 |
| form | +0.306 | -0.093 | +0.213 |
| record/margin | +0.059 | -0.009 | +0.050 |
| rest | +0.007 | +0.002 | +0.009 |
| run game | -0.019 | +0.030 | +0.011 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 22% of total |contribution|; top 3 carry 51%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - roof_dome (weather family): +0.050 toward the pick
  - temp (weather family): -0.013 toward the pick
  - wind (weather family): -0.003 toward the pick

The model favours LAC over LV, driven mainly by form and OL pass protection. Top single driver: home_rolling_3wk_epa_trend_blend (form), LAC at the 3rd league percentile, contributing +0.306 log-odds toward the pick.

### MIA @ SF (`2026_02_MIA_SF`)

- Line at pick time (home perspective): +13.5 · Closing line: +13.5 — favourite (by closing line): SF
- Live pick: home (SF), P(home cover) = 0.585
- Result: home_covered=not yet played, correct=n/a

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| OL pass protection | away_ol_sack_rate_blend | away | 0.083 | 75.0 | +0.150 |
| defence pass rush | home_def_qb_hit_rate_blend | home | 0.112 | 9.4 | +0.101 |
| defence pass rush | home_def_pressure_proxy_rate_blend | home | 0.143 | 3.1 | +0.100 |
| OL pass protection | home_ol_pressure_proxy_rate_blend | home | 0.169 | 12.5 | +0.097 |
| form | away_rolling_3wk_epa_trend_blend | away | -0.157 | 21.9 | -0.096 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | +0.187 | +0.214 | +0.401 |
| OL run blocking | -0.023 | +0.015 | -0.008 |
| QB | -0.028 | +0.018 | -0.010 |
| coverage/defence other | +0.017 | -0.026 | -0.010 |
| defence pass rush | +0.169 | -0.119 | +0.050 |
| defence run | +0.038 | +0.040 | +0.078 |
| form | -0.033 | -0.096 | -0.130 |
| record/margin | +0.089 | +0.006 | +0.095 |
| rest | -0.021 | +0.006 | -0.015 |
| run game | -0.023 | -0.005 | -0.028 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 26% of total |contribution|; top 3 carry 59%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - temp (weather family): -0.018 toward the pick
  - wind (weather family): -0.010 toward the pick
  - roof_dome (weather family): -0.006 toward the pick

The model favours SF over MIA, driven mainly by OL pass protection and defence pass rush. Top single driver: away_ol_sack_rate_blend (OL pass protection), MIA at the 75th league percentile, contributing +0.150 log-odds toward the pick.

### MIN @ CHI (`2026_02_MIN_CHI`)

- Line at pick time (home perspective): +5.5 · Closing line: +5.5 — favourite (by closing line): CHI
- Live pick: home (CHI), P(home cover) = 0.752
- Result: home_covered=not yet played, correct=n/a

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| coverage/defence other | away_def_epa_per_play_blend | away | -0.108 | 6.2 | +0.237 |
| QB | away_qb_cpoe_blend | away | -3.130 | 9.4 | +0.181 |
| defence pass rush | away_def_sack_rate_blend | away | 0.097 | 96.9 | +0.172 |
| OL pass protection | away_ol_sack_rate_blend | away | 0.111 | 100.0 | +0.162 |
| defence pass rush | away_def_pressure_proxy_rate_blend | away | 0.311 | 96.9 | +0.120 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | -0.013 | +0.350 | +0.338 |
| OL run blocking | +0.102 | -0.032 | +0.070 |
| QB | +0.088 | +0.149 | +0.237 |
| coverage/defence other | -0.020 | +0.318 | +0.298 |
| defence pass rush | +0.005 | +0.333 | +0.339 |
| defence run | -0.009 | -0.110 | -0.119 |
| form | -0.018 | -0.047 | -0.065 |
| record/margin | +0.074 | +0.019 | +0.093 |
| rest | +0.006 | +0.004 | +0.010 |
| run game | +0.003 | -0.001 | +0.002 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 22% of total |contribution|; top 3 carry 59%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - wind (weather family): -0.017 toward the pick
  - temp (weather family): -0.013 toward the pick
  - roof_dome (weather family): -0.007 toward the pick

The model favours CHI over MIN, driven mainly by coverage/defence other and QB. Top single driver: away_def_epa_per_play_blend (coverage/defence other), MIN at the 6th league percentile, contributing +0.237 log-odds toward the pick.

### NO @ BAL (`2026_02_NO_BAL`)

- Line at pick time (home perspective): +8.5 · Closing line: +8.5 — favourite (by closing line): BAL
- Live pick: home (BAL), P(home cover) = 0.548
- Result: home_covered=not yet played, correct=n/a

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| OL pass protection | away_ol_sack_rate_blend | away | 0.078 | 68.8 | +0.124 |
| OL run blocking | home_ol_rush_epa_per_att_blend | home | 0.123 | 100.0 | +0.069 |
| coverage/defence other | away_def_epa_per_play_blend | away | -0.052 | 25.0 | -0.058 |
| defence run | away_def_rush_epa_allowed_per_att_blend | away | -0.071 | 9.4 | -0.056 |
| QB | away_qb_epa_under_pressure_blend | away | -1.035 | 28.1 | -0.055 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | -0.084 | +0.148 | +0.064 |
| OL run blocking | +0.077 | +0.031 | +0.109 |
| QB | +0.018 | -0.012 | +0.007 |
| coverage/defence other | +0.015 | -0.054 | -0.039 |
| defence pass rush | -0.032 | -0.018 | -0.051 |
| defence run | +0.009 | -0.008 | +0.001 |
| form | +0.045 | +0.004 | +0.049 |
| record/margin | +0.075 | +0.017 | +0.092 |
| rest | +0.007 | +0.006 | +0.013 |
| run game | -0.028 | +0.046 | +0.019 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 19% of total |contribution|; top 3 carry 48%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - temp (weather family): -0.010 toward the pick
  - wind (weather family): -0.007 toward the pick
  - roof_dome (weather family): -0.004 toward the pick

The model favours BAL over NO, driven mainly by OL pass protection and OL run blocking. Top single driver: away_ol_sack_rate_blend (OL pass protection), NO at the 69th league percentile, contributing +0.124 log-odds toward the pick.

### NYG @ LA (`2026_02_NYG_LA`)

- Line at pick time (home perspective): +7.0 · Closing line: +7.0 — favourite (by closing line): LA
- Live pick: home (LA), P(home cover) = 0.586
- Result: home_covered=not yet played, correct=n/a

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| form | away_rolling_3wk_epa_trend_blend | away | 0.243 | 93.8 | +0.191 |
| OL pass protection | away_ol_sack_rate_blend | away | 0.082 | 71.9 | +0.103 |
| coverage/defence other | away_def_explosive_pass_allowed_rate_blend | away | 0.074 | 25.0 | +0.093 |
| QB | away_qb_epa_under_pressure_blend | away | -0.686 | 93.8 | +0.074 |
| OL pass protection | home_ol_pressure_proxy_rate_blend | home | 0.173 | 15.6 | +0.065 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | +0.129 | +0.161 | +0.290 |
| OL run blocking | +0.006 | +0.022 | +0.029 |
| QB | -0.003 | +0.069 | +0.066 |
| coverage/defence other | -0.034 | +0.065 | +0.031 |
| defence pass rush | -0.045 | -0.049 | -0.094 |
| defence run | +0.004 | -0.073 | -0.069 |
| form | -0.054 | +0.191 | +0.138 |
| record/margin | -0.030 | +0.027 | -0.003 |
| rest | -0.007 | +0.002 | -0.005 |
| run game | -0.025 | +0.006 | -0.019 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 21% of total |contribution|; top 3 carry 53%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - roof_dome (weather family): +0.034 toward the pick
  - wind (weather family): -0.008 toward the pick
  - temp (weather family): -0.002 toward the pick

The model favours LA over NYG, driven mainly by form and OL pass protection. Top single driver: away_rolling_3wk_epa_trend_blend (form), NYG at the 94th league percentile, contributing +0.191 log-odds toward the pick.

### PHI @ TEN (`2026_02_PHI_TEN`)

- Line at pick time (home perspective): -7.0 · Closing line: -7.0 — favourite (by closing line): PHI
- Live pick: home (TEN), P(home cover) = 0.503
- Result: home_covered=not yet played, correct=n/a

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| form | home_rolling_3wk_epa_trend_blend | home | -0.216 | 9.4 | +0.233 |
| QB | home_qb_cpoe_blend | home | -3.112 | 12.5 | -0.103 |
| coverage/defence other | away_def_explosive_pass_allowed_rate_blend | away | 0.074 | 21.9 | +0.083 |
| coverage/defence other | away_def_epa_per_play_blend | away | -0.047 | 28.1 | -0.080 |
| QB | away_qb_cpoe_blend | away | 2.839 | 81.2 | -0.077 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | -0.040 | +0.095 | +0.055 |
| OL run blocking | +0.055 | +0.007 | +0.062 |
| QB | -0.071 | -0.153 | -0.224 |
| coverage/defence other | +0.012 | +0.035 | +0.048 |
| defence pass rush | +0.008 | -0.068 | -0.061 |
| defence run | +0.001 | +0.015 | +0.016 |
| form | +0.233 | -0.045 | +0.189 |
| record/margin | +0.017 | -0.034 | -0.016 |
| rest | +0.007 | +0.004 | +0.011 |
| run game | -0.003 | +0.007 | +0.004 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 26% of total |contribution|; top 3 carry 59%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - temp (weather family): -0.021 toward the pick
  - roof_dome (weather family): -0.009 toward the pick
  - wind (weather family): +0.007 toward the pick

The model favours TEN over PHI, driven mainly by form and QB. Top single driver: home_rolling_3wk_epa_trend_blend (form), TEN at the 9th league percentile, contributing +0.233 log-odds toward the pick.

### PIT @ NE (`2026_02_PIT_NE`)

- Line at pick time (home perspective): +5.5 · Closing line: +5.5 — favourite (by closing line): NE
- Live pick: home (NE), P(home cover) = 0.524
- Result: home_covered=not yet played, correct=n/a

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| QB | home_qb_cpoe_blend | home | 10.115 | 100.0 | +0.234 |
| OL pass protection | away_ol_pressure_proxy_rate_blend | away | 0.166 | 9.4 | -0.135 |
| defence pass rush | away_def_sack_rate_blend | away | 0.079 | 84.4 | +0.125 |
| form | away_rolling_3wk_epa_trend_blend | away | -0.150 | 28.1 | -0.090 |
| OL pass protection | away_ol_sack_rate_blend | away | 0.053 | 25.0 | -0.085 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | +0.002 | -0.229 | -0.227 |
| OL run blocking | +0.029 | -0.013 | +0.016 |
| QB | +0.189 | -0.001 | +0.188 |
| coverage/defence other | +0.041 | +0.027 | +0.068 |
| defence pass rush | -0.003 | +0.157 | +0.154 |
| defence run | -0.028 | +0.044 | +0.017 |
| form | +0.009 | -0.090 | -0.081 |
| record/margin | -0.022 | +0.024 | +0.003 |
| rest | -0.012 | +0.009 | -0.004 |
| run game | +0.007 | +0.007 | +0.014 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 29% of total |contribution|; top 3 carry 64%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - temp (weather family): -0.018 toward the pick
  - roof_dome (weather family): -0.007 toward the pick
  - wind (weather family): +0.001 toward the pick

The model favours NE over PIT, driven mainly by QB and OL pass protection. Top single driver: home_qb_cpoe_blend (QB), NE at the 100th league percentile, contributing +0.234 log-odds toward the pick.

### SEA @ ARI (`2026_02_SEA_ARI`)

- Line at pick time (home perspective): -4.5 · Closing line: -4.5 — favourite (by closing line): SEA
- Live pick: home (ARI), P(home cover) = 0.554
- Result: home_covered=not yet played, correct=n/a

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| coverage/defence other | away_def_epa_per_play_blend | away | -0.125 | 3.1 | +0.312 |
| coverage/defence other | away_def_explosive_pass_allowed_rate_blend | away | 0.061 | 3.1 | +0.158 |
| defence run | away_def_rush_epa_allowed_per_att_blend | away | -0.136 | 3.1 | +0.142 |
| record/margin | away_avg_margin_blend | away | 10.320 | 100.0 | -0.104 |
| defence pass rush | away_def_sack_rate_blend | away | 0.074 | 65.6 | -0.096 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | -0.130 | +0.061 | -0.070 |
| OL run blocking | +0.040 | -0.024 | +0.016 |
| QB | +0.115 | -0.140 | -0.025 |
| coverage/defence other | +0.081 | +0.511 | +0.592 |
| defence pass rush | -0.047 | -0.060 | -0.107 |
| defence run | -0.025 | +0.073 | +0.048 |
| form | -0.037 | +0.021 | -0.016 |
| record/margin | -0.111 | -0.073 | -0.185 |
| rest | +0.005 | -0.020 | -0.015 |
| run game | +0.079 | -0.019 | +0.061 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 27% of total |contribution|; top 3 carry 55%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - temp (weather family): -0.017 toward the pick
  - wind (weather family): -0.010 toward the pick
  - roof_dome (weather family): -0.008 toward the pick

The model favours ARI over SEA, driven mainly by coverage/defence other and defence run. Top single driver: away_def_epa_per_play_blend (coverage/defence other), SEA at the 3rd league percentile, contributing +0.312 log-odds toward the pick.

### WAS @ DAL (`2026_02_WAS_DAL`)

- Line at pick time (home perspective): +3.5 · Closing line: +3.5 — favourite (by closing line): DAL
- Live pick: home (DAL), P(home cover) = 0.520
- Result: home_covered=not yet played, correct=n/a

**Top 5 drivers (toward the live pick):**

| Family | Feature | Side | Raw value | League pctile | Contribution |
|---|---|---|---|---|---|
| run game | home_rush_explosive_rate_blend | home | 0.099 | 18.8 | +0.120 |
| QB | home_qb_epa_under_pressure_blend | home | -0.518 | 100.0 | +0.093 |
| coverage/defence other | away_def_explosive_pass_allowed_rate_blend | away | 0.093 | 81.2 | -0.086 |
| coverage/defence other | home_def_epa_per_play_blend | home | 0.149 | 100.0 | +0.081 |
| OL pass protection | home_ol_pressure_proxy_rate_blend | home | 0.184 | 21.9 | +0.072 |

**Family matchup (home-cover-oriented, not pick-direction):**

| Family | Home | Away | Net |
|---|---|---|---|
| OL pass protection | +0.145 | +0.070 | +0.215 |
| OL run blocking | +0.031 | +0.035 | +0.066 |
| QB | +0.059 | -0.042 | +0.017 |
| coverage/defence other | +0.147 | -0.175 | -0.029 |
| defence pass rush | -0.022 | -0.067 | -0.089 |
| defence run | +0.004 | -0.021 | -0.017 |
| form | -0.032 | +0.009 | -0.022 |
| record/margin | -0.053 | -0.002 | -0.055 |
| rest | +0.010 | +0.001 | +0.011 |
| run game | +0.120 | -0.051 | +0.069 |
| venue/context | +0.000 | +0.000 | +0.000 |

- Top 1 family carries 23% of total |contribution|; top 3 carry 53%.
- Strongest interaction pair: Not stored: this run computes per-feature contributions only, no feature-interaction pairs.
- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):
  - temp (weather family): -0.017 toward the pick
  - roof_dome (weather family): -0.006 toward the pick
  - wind (weather family): -0.003 toward the pick

The model favours DAL over WAS, driven mainly by run game and QB. Top single driver: home_rush_explosive_rate_blend (run game), DAL at the 19th league percentile, contributing +0.120 log-odds toward the pick.

## 2. Patterns across the games

**Mean |contribution| by family, and how often it pushed toward the picked side:**

| Family | Mean |contribution| | Toward pick (all games) | Toward pick (excl. side-mismatches) |
|---|---|---|---|
| OL pass protection | 0.1718 | 56% (n=16) | 56% (n=16) |
| defence pass rush | 0.1344 | 50% (n=16) | 50% (n=16) |
| QB | 0.1325 | 62% (n=16) | 62% (n=16) |
| coverage/defence other | 0.1109 | 69% (n=16) | 69% (n=16) |
| form | 0.0981 | 56% (n=16) | 56% (n=16) |
| defence run | 0.0717 | 50% (n=16) | 50% (n=16) |
| record/margin | 0.0614 | 56% (n=16) | 56% (n=16) |
| OL run blocking | 0.0462 | 75% (n=16) | 75% (n=16) |
| run game | 0.0300 | 75% (n=16) | 75% (n=16) |
| weather | 0.0270 | 38% (n=16) | 38% (n=16) |
| rest | 0.0098 | 62% (n=16) | 62% (n=16) |
| venue/context | 0.0061 | 56% (n=16) | 56% (n=16) |

**Groups by pick-direction contribution vector (hierarchical, cosine distance, average linkage):**

- Group 1 — dominant: QB, form — games: 2026_02_GB_NYJ, 2026_02_NO_BAL, 2026_02_PHI_TEN
- Group 2 — dominant: OL pass protection, defence pass rush — games: 2026_02_CLE_TB, 2026_02_MIA_SF, 2026_02_MIN_CHI, 2026_02_NYG_LA, 2026_02_WAS_DAL
- Group 3 — dominant: coverage/defence other, record/margin — games: 2026_02_CIN_HOU, 2026_02_SEA_ARI
- Group 4 — dominant: QB, OL pass protection — games: 2026_02_CAR_ATL, 2026_02_IND_KC, 2026_02_JAX_DEN, 2026_02_LV_LAC, 2026_02_PIT_NE
- Group 5 — dominant: defence pass rush, QB — games: 2026_02_DET_BUF

**Recurring top-driver shapes (family + side of the #1 driver):**

- QB (home) — 4 game(s): 2026_02_CAR_ATL (away), 2026_02_DET_BUF (away), 2026_02_IND_KC (home), 2026_02_PIT_NE (home)
- coverage/defence other (away) — 4 game(s): 2026_02_CIN_HOU (away), 2026_02_GB_NYJ (away), 2026_02_MIN_CHI (home), 2026_02_SEA_ARI (home)
- OL pass protection (away) — 2 game(s): 2026_02_MIA_SF (home), 2026_02_NO_BAL (home)
- form (away) — 2 game(s): 2026_02_JAX_DEN (home), 2026_02_NYG_LA (home)
- form (home) — 2 game(s): 2026_02_LV_LAC (home), 2026_02_PHI_TEN (home)
- QB (away) — 1 game(s): 2026_02_CLE_TB (home)
- run game (home) — 1 game(s): 2026_02_WAS_DAL (home)

## 3. Against the market

**Model P(home cover) vs. closing spread, per game (sorted by disagreement with the market):**

| Game | Line at pick time | Closing line | Favourite (closing) | Pick | P(home cover) | |P-0.5| |
|---|---|---|---|---|---|---|
| 2026_02_MIN_CHI | +5.5 | +5.5 | CHI | home | 0.752 | 0.252 |
| 2026_02_CIN_HOU | +3.0 | +3.0 | HOU | away | 0.398 | 0.102 |
| 2026_02_LV_LAC | +7.0 | +7.0 | LAC | home | 0.592 | 0.092 |
| 2026_02_NYG_LA | +7.0 | +7.0 | LA | home | 0.586 | 0.086 |
| 2026_02_MIA_SF | +13.5 | +13.5 | SF | home | 0.585 | 0.085 |
| 2026_02_JAX_DEN | +2.5 | +2.5 | DEN | home | 0.572 | 0.072 |
| 2026_02_CAR_ATL | -1.5 | -1.5 | CAR | away | 0.432 | 0.068 |
| 2026_02_IND_KC | +6.5 | +6.5 | KC | home | 0.560 | 0.060 |
| 2026_02_SEA_ARI | -4.5 | -4.5 | SEA | home | 0.554 | 0.054 |
| 2026_02_NO_BAL | +8.5 | +8.5 | BAL | home | 0.548 | 0.048 |
| 2026_02_CLE_TB | +8.5 | +8.5 | TB | home | 0.538 | 0.038 |
| 2026_02_PIT_NE | +5.5 | +5.5 | NE | home | 0.524 | 0.024 |
| 2026_02_WAS_DAL | +3.5 | +3.5 | DAL | home | 0.520 | 0.020 |
| 2026_02_DET_BUF | +4.5 | +4.5 | BUF | away | 0.489 | 0.011 |
| 2026_02_PHI_TEN | -7.0 | -7.0 | PHI | home | 0.503 | 0.003 |
| 2026_02_GB_NYJ | -4.5 | -4.5 | GB | away | 0.500 | 0.000 |

Families driving the largest market disagreements:
- 2026_02_MIN_CHI (|P-0.5|=0.252): top family OL pass protection (22% of total |contribution|)
- 2026_02_CIN_HOU (|P-0.5|=0.102): top family OL pass protection (19% of total |contribution|)
- 2026_02_LV_LAC (|P-0.5|=0.092): top family form (22% of total |contribution|)

**Underdog picks: 4 of 16.**

Families pushing toward the pick specifically on underdog picks:

| Family | Toward pick (all underdog picks) | Toward pick (excl. mismatches) |
|---|---|---|
| coverage/defence other | 100% (n=4) | 100% (n=4) |
| QB | 25% (n=4) | 25% (n=4) |
| defence pass rush | 25% (n=4) | 25% (n=4) |
| form | 75% (n=4) | 75% (n=4) |
| record/margin | 25% (n=4) | 25% (n=4) |
| run game | 75% (n=4) | 75% (n=4) |
| OL run blocking | 75% (n=4) | 75% (n=4) |
| defence run | 75% (n=4) | 75% (n=4) |
| OL pass protection | 25% (n=4) | 25% (n=4) |
| weather | 50% (n=4) | 50% (n=4) |
| rest | 25% (n=4) | 25% (n=4) |
| venue/context | 25% (n=4) | 25% (n=4) |

**Around key numbers:** 3 game(s) within 0.5 of a 3-point spread (2026_02_CIN_HOU, 2026_02_JAX_DEN, 2026_02_WAS_DAL); 4 game(s) within 0.5 of a 7-point spread (2026_02_IND_KC, 2026_02_LV_LAC, 2026_02_NYG_LA, 2026_02_PHI_TEN).

Line movement: 16 of 16 games have exactly ONE snapshot in `line_snapshots` — a one-time manual catch-up capture (see HANDOFF-2026-09-18-spread-sign-and-snapshots.md), not a real change-log. "First-seen" and "closing" are the same single observation here; no actual line movement can be shown yet.

Moneyline population by season — 2015: 267/267, 2016: 267/267, 2017: 266/267, 2018: 267/267, 2019: 267/267, 2020: 269/269, 2021: 285/285, 2022: 284/284, 2023: 285/285, 2024: 285/285, 2025: 285/285, 2026: 32/272. 2026 week 2 is fully populated for this slate; de-vigged market probability shown below.

| Game | Home devigged win prob (moneyline) | Model P(home cover) |
|---|---|---|
| 2026_02_CAR_ATL | 0.468 | 0.432 |
| 2026_02_NO_BAL | 0.751 | 0.548 |
| 2026_02_DET_BUF | 0.645 | 0.489 |
| 2026_02_CLE_TB | 0.751 | 0.538 |
| 2026_02_GB_NYJ | 0.355 | 0.500 |
| 2026_02_SEA_ARI | 0.336 | 0.554 |
| 2026_02_IND_KC | 0.726 | 0.560 |
| 2026_02_LV_LAC | 0.722 | 0.592 |
| 2026_02_PHI_TEN | 0.278 | 0.503 |
| 2026_02_WAS_DAL | 0.664 | 0.520 |
| 2026_02_CIN_HOU | 0.572 | 0.398 |
| 2026_02_NYG_LA | 0.748 | 0.586 |
| 2026_02_MIA_SF | 0.868 | 0.585 |
| 2026_02_PIT_NE | 0.669 | 0.524 |
| 2026_02_MIN_CHI | 0.675 | 0.752 |
| 2026_02_JAX_DEN | 0.551 | 0.572 |
Note: moneyline win probability and P(home cover) measure different things (straight-up win vs. ATS cover) — shown side by side, not equated.

**Favourite check (closing spread vs. de-vigged moneyline): 100% agree — no disagreements.**

**Per-family correlation with the closing spread (home-cover-oriented, not pick-direction):**

| Family | n games | corr with closing spread |
|---|---|---|
| record/margin | 16 | 0.701 |
| OL pass protection | 16 | 0.446 |
| coverage/defence other | 16 | -0.385 |
| defence pass rush | 16 | 0.240 |
| weather | 16 | 0.182 |
| OL run blocking | 16 | 0.180 |
| form | 16 | -0.166 |
| venue/context | 16 | 0.155 |
| QB | 16 | 0.098 |
| run game | 16 | -0.093 |
| defence run | 16 | -0.024 |
| rest | 16 | -0.002 |

## 4. Hand-off list — testable on 2015-2025

1. Picks where OL run blocking is the top driver and it pushed toward the pick (true in 75% of the 16 non-mismatched games) — test ATS performance on 2015-2025 for games where this family is the #1 driver.
2. Picks where run game is the top driver and it pushed toward the pick (true in 75% of the 16 non-mismatched games) — test ATS performance on 2015-2025 for games where this family is the #1 driver.
3. record/margin correlates most with the closing spread (r=0.70) and is largely repeating the market — test whether excluding it from the feature set changes backtest log loss.
4. rest correlates least with the closing spread (r=-0.00) — test whether picks driven by this family beat the market ATS on 2015-2025, independent of the spread.
5. Picks where the model backs the underdog and coverage/defence other is the top driver — test ATS performance on 2015-2025 for underdog picks split by this family's direction.
6. Games whose #1 driver is QB on the home side (4 of this week's games) — test whether this shape recurs and beats the market ATS on 2015-2025.
7. Games within half a point of the 3 or 7 key numbers — test whether the model's calibration (P(cover) vs. actual cover rate) differs near these numbers on 2015-2025.
