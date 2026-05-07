# Running the Phase 1 Backtest

## Prerequisites

1. **GCP auth** — must be set up on the machine running the script.
   Either `GOOGLE_APPLICATION_CREDENTIALS` pointing to a service account key,
   or an active `gcloud auth application-default login` session.

2. **Python 3.10+** with dependencies installed:
   ```bash
   cd 02-MODELING
   pip install -r requirements.txt
   ```

3. **BigQuery tables** — `curated.games` and `curated.plays` must be present
   in project `nfl-model-471509`.  Verify with the DATA-PIPELINE validation
   report before running.

## Running

```bash
cd 02-MODELING
python backtests/run_phase1_backtest.py
```

Expected runtime: ~5–15 minutes (dominated by the BigQuery data loads and
6-fold XGBoost training).

## Outputs

All outputs land in `backtests/reports/` with the experiment ID as a prefix:

| File | Contents |
|------|----------|
| `{id}_report.md`              | Full backtest report (submit to PROJECT-LEAD) |
| `{id}_predictions.csv`        | All per-game predictions across all 6 folds |
| `{id}_by_season.csv`          | Per-season ATS summary |
| `{id}_feature_importance.json`| Avg feature importance across folds |

BigQuery:
- `experiments.backtest_runs` — one row for this run
- `experiments.backtest_predictions` — one row per game

`experiments/EXPERIMENTS.md` is also updated with a brief summary.

## After the run

1. Review `backtests/reports/{id}_report.md`
2. Review `experiments/OL_COMPOSITE_PROPOSAL.md` (generated automatically)
3. **Submit the composite proposal to PROJECT-LEAD** and wait for written approval
4. Do NOT modify `ol_mismatch_flag` or run any subset analysis before approval

## Reproducibility

Given the same `experiment_id`, re-running produces identical results:
- XGBoost random_state=42 is fixed
- StandardScaler is deterministic
- Feature computation is purely deterministic from BigQuery data

## Troubleshooting

**`BigQuery connection failed`** — run `gcloud auth application-default login`
or confirm your service account key path.

**`Unexpected play count`** — the curated.plays table may not be fully loaded.
Re-run the DATA-PIPELINE before retrying.

**`NaN hit rate`** — indicates all test games for a fold were pushes (impossible
with real NFL data; check the home_covered derivation in curated.games).
