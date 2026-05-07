# Phase 1 Pipeline — Run Instructions

Open a terminal (cmd or PowerShell), `cd` into this folder, then run these
commands **in order**. Each one prints a summary when it finishes.
PBP ingest is the slow step (~15–25 min for all 10+ seasons).

```
cd C:\Users\Matth\Desktop\nfl-prediction-app\01-DATA-PIPELINE
```

## Step 0 — One-time GCP auth (Application Default Credentials)

This is required once so the Python BigQuery client can authenticate.

```
gcloud auth application-default login
```

A browser window will open. Sign in with matt.lilley4@gmail.com and approve.

## Step 1 — Ingest raw schedules (fast, ~2 min)

```
C:\Users\Matth\AppData\Local\Programs\Python\Python311\python.exe scripts\ingest_schedules.py
```

## Step 2 — Audit closing lines (STOP and read output before continuing)

```
C:\Users\Matth\AppData\Local\Programs\Python\Python311\python.exe scripts\audit_closing_lines.py
```

Read the output carefully. It will print null rates by season and a RESULT line.
If OPTION 1 PASSES, continue to Step 3. If it fails, report back to PROJECT-LEAD
before proceeding.

## Step 3 — Ingest raw PBP (slow, ~15–25 min for all seasons)

```
C:\Users\Matth\AppData\Local\Programs\Python\Python311\python.exe scripts\ingest_pbp.py
```

To do a single season first as a smoke test:
```
C:\Users\Matth\AppData\Local\Programs\Python\Python311\python.exe scripts\ingest_pbp.py --season 2024
```

## Step 4 — Ingest raw rosters (~3 min)

```
C:\Users\Matth\AppData\Local\Programs\Python\Python311\python.exe scripts\ingest_rosters.py
```

## Step 5 — Build curated.games (~1 min)

```
C:\Users\Matth\AppData\Local\Programs\Python\Python311\python.exe scripts\build_curated_games.py
```

## Step 6 — Build curated.plays (~5–10 min)

```
C:\Users\Matth\AppData\Local\Programs\Python\Python311\python.exe scripts\build_curated_plays.py
```

## Step 7 — Run validation and generate report

```
C:\Users\Matth\AppData\Local\Programs\Python\Python311\python.exe scripts\validate_and_report.py
```

This produces `VALIDATION_REPORT.md` in this folder and prints PASS/FAIL for
every spec check. All checks must pass before handing off to MODELING.

---

## Troubleshooting

**MemoryError on import** — close other applications to free RAM, then retry.

**DefaultCredentialsError** — run Step 0 (gcloud auth application-default login).

**403 Permission denied on BigQuery** — run:
```
gcloud config set project nfl-model-471509
```

**Single-season retry** — every script accepts `--season YYYY` to re-run just
one year without touching the others.
