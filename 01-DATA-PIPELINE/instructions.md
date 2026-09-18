# Agent: DATA-PIPELINE

**Rewritten 2026-09-17.** The old version, including the HC-S1 and DP-REVIEW task briefs, is in `archive/instructions-pre-2026-09-17.md`. Read the repo root `CLAUDE.md` first.

## What you own

Getting NFL data into BigQuery, validated: source adapters, raw and curated tables, pipeline jobs, data-quality checks, and the line-snapshot log. Everything downstream reads what you publish.

You don't compute model features (MODELING), serve HTTP (BACKEND-API), or deploy infrastructure (DEVOPS).

## What's here

| Path | What it is |
|---|---|
| `scripts/run_pipeline.py` | The 7-step pipeline: 1 schedules, 2 audit closing lines, 3 pbp, 4 rosters, 5 `curated.games`, 6 `curated.plays`, 7 validate. `--start-at N` resumes |
| `scripts/run_pipeline_job.py` | Cloud Run entrypoint. `PIPELINE_MODE=full` or `gameday` (gameday is `--start-at 1`, so it currently runs all steps) |
| `scripts/snapshot_lines.py` | Appends line changes to `raw_lines.line_snapshots` (live since 2026-09-09). Called inside the pipeline; a failure is loud but not fatal |
| `scripts/verify_label_convention.py` | Label checks C1–C6 over `curated.games`; exits non-zero on failure |
| `scripts/migrate_*.py` | Table migrations (phase 2 platform tables, phase 6 scoping tables) |
| `adapters/` | `base.py` adapter interface, `nflfastr.py` (the data spine) |
| `new_sources_staging/` | 13 staged parquet sources (OL snaps, depth charts, injuries, NGS, PFR pressure, FTN charting and more) plus `load_to_bigquery.py` |
| `DP-REVIEW-2026-09-09.md` | Review of the ingest path; defects DP-R-01 to DP-R-13 |
| `RUN.md` | **Out of date** (old `C:\Users\Matth` paths). Use `run_pipeline.py` directly |

## Tables you publish

`raw_nflfastr.schedules`, `raw_nflfastr.pbp`, `raw_nflfastr.rosters`, `raw_lines.line_snapshots`, `curated.games`, `curated.plays`. Migrations also created `platform.scoping_sessions` and `platform.capability_gaps`.

## How it runs

- Image: `gcr.io/nfl-model-471509/nfl-data-pipeline`, built from this folder's `cloudbuild.yaml`. Jobs `nfl-pipeline-full` and `nfl-pipeline-gameday` run it.
- Schedule (UTC): Mon 05:00 gameday (Sunday games) · Tue 07:00 gameday (MNF) · Tue 11:00 full · Fri 05:00 gameday (TNF).
- Recovery for a missed ingest (Matt runs it): `gcloud run jobs execute nfl-pipeline-full --region us-central1 --wait`

## Rules

1. **Fix the script, then rebuild the data.** A data-only fix is overwritten by the next scheduled run. Document real remediations in `PIPELINE_REMEDIATION_NNN.md`.
2. **Idempotent.** Re-running the same week gives the same curated state.
3. **Sign convention.** In nflverse data, a positive `home_spread_close` means the home team is favoured. C1 in `verify_label_convention.py` proves this from results; don't rely on comments.
4. **Check derived labels, not just row counts.** `home_covered` must sit near 50% in every spread bin. A null-rate check passes on a fully inverted label (INC-001).
5. **Surface absences.** Known gap (DP-R-02): if a season returns no rows, no check is generated and the run still reports "ALL CHECKS PASSED". Until that's fixed, row counts per season are the only way to see a skipped season.
6. **Schema is a contract.** Adding a curated column is a notice to MODELING and BACKEND-API. Renaming or removing one needs PROJECT-LEAD.
7. **Read the live schema before writing** to any table.
8. **Name things by what they measure,** not by vendor.

## Current task

None. Work arrives as `00-PROJECT-LEAD/PROMPT-*.md`. DP-REVIEW (09-09) is finished. Its follow-up defects aren't scheduled yet; they are listed in `00-PROJECT-LEAD/STATE.md`.
