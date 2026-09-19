# ── Dataset Upload Processor Cloud Run Job ─────────────────────────────────────
#
# Triggered by POST /api/v1/datasets/upload after the raw file is written to GCS.
# Reads: gs://nfl-model-471509-uploads/{DATASET_ID}/raw.{FILE_EXT}
# Writes: user_datasets.{dataset_id} (BQ table) + platform.datasets/dataset_columns
#
# Uses the same container image as the backend API (nfl-backend-api:latest) and
# runs scripts/process_dataset_upload.py as the command.  No separate image is
# needed: the API image already has pandas, google-cloud-bigquery, openpyxl, and
# google-cloud-storage installed via pyproject.toml.
#
# max-retries=1: if the job fails once it retries; a second failure sets status
# to 'error' via the script's except block and exits 1 to stop further retries.

resource "google_cloud_run_v2_job" "dataset_processor" {
  name     = "nfl-dataset-processor"
  location = var.region
  project  = var.project_id

  template {
    parallelism = 1
    task_count  = 1

    template {
      timeout         = "900s"   # 15 min — generous for large Excel/JSON files
      max_retries     = 1
      service_account = google_service_account.dataset_processor.email

      containers {
        image   = "gcr.io/${var.project_id}/nfl-backend-api:latest"
        command = ["python"]
        args    = ["scripts/process_dataset_upload.py"]

        resources {
          limits = {
            cpu    = "1"
            memory = "2Gi"   # pandas + openpyxl peak usage for 50 MB files
          }
        }

        env {
          name  = "BIGQUERY_PROJECT"
          value = var.project_id
        }

        # DATASET_ID and FILE_EXT are injected per-execution via containerOverrides
        # in trigger_dataset_processor() — no static values here.
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image]
  }

  depends_on = [google_service_account.dataset_processor]
}

# ── Experiment Runner Cloud Run Job ────────────────────────────────────────────

resource "google_cloud_run_v2_job" "experiment_runner" {
  name     = "nfl-experiment-runner"
  location = var.region
  project  = var.project_id

  template {
    parallelism = 1
    task_count  = 1

    template {
      timeout         = "3600s"
      service_account = google_service_account.runner.email

      containers {
        image = "gcr.io/${var.project_id}/nfl-experiment-runner:latest"

        resources {
          limits = {
            cpu    = "2"
            memory = "4Gi"
          }
        }

        env {
          name  = "BIGQUERY_PROJECT"
          value = var.project_id
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image]
  }

  depends_on = [google_service_account.runner]
}

# ── Data Pipeline — Full Run Cloud Run Job ─────────────────────────────────────

resource "google_cloud_run_v2_job" "pipeline_full" {
  name     = "nfl-pipeline-full"
  location = var.region
  project  = var.project_id

  template {
    parallelism = 1
    task_count  = 1

    template {
      timeout         = "7200s"
      service_account = google_service_account.pipeline.email

      containers {
        image = "gcr.io/${var.project_id}/nfl-data-pipeline:latest"

        resources {
          limits = {
            cpu    = "2"
            memory = "8Gi"
          }
        }

        env {
          name  = "BIGQUERY_PROJECT"
          value = var.project_id
        }

        env {
          name  = "PIPELINE_MODE"
          value = "full"
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image]
  }

  depends_on = [google_service_account.pipeline]
}

# ── Data Pipeline — Gameday Run Cloud Run Job ──────────────────────────────────

resource "google_cloud_run_v2_job" "pipeline_gameday" {
  name     = "nfl-pipeline-gameday"
  location = var.region
  project  = var.project_id

  template {
    parallelism = 1
    task_count  = 1

    template {
      timeout         = "1800s"
      service_account = google_service_account.pipeline.email

      containers {
        image = "gcr.io/${var.project_id}/nfl-data-pipeline:latest"

        resources {
          limits = {
            cpu    = "2"
            memory = "4Gi"
          }
        }

        env {
          name  = "BIGQUERY_PROJECT"
          value = var.project_id
        }

        env {
          name  = "PIPELINE_MODE"
          value = "gameday"
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image]
  }

  depends_on = [google_service_account.pipeline]
}

# ── Injury / Depth-Chart Snapshot Capture Cloud Run Job ─────────────────────────
#
# WRITTEN, NOT APPLIED OR DEPLOYED (PROMPT-CAPTURE-INJURY-SNAPSHOTS.md). A
# separate job from nfl-pipeline-full/gameday on purpose (design point 1):
# the pipeline drops and rebuilds its own landing tables and crash-looped for
# a week on one missing IAM grant (QUESTIONS.md, 2026-09-18); this capture's
# only job is to never miss a day, so it must not share that job's fate --
# its own image, own service account (nfl-injury-capture-sa, iam.tf), own
# schedule (scheduler.tf), and it touches a dataset the pipeline doesn't
# write.
#
# Reuses the nfl-data-pipeline IMAGE (not a new build/image pipeline): it
# already carries the pinned nfl_data_py + google-cloud-bigquery this script
# needs, and reusing it means no new Dockerfile or build step is required.
# This does NOT reintroduce the fate-sharing design point 1 warns against --
# that's about not sharing the pipeline's *runtime* (a hung/crash-looping
# pipeline execution cannot block or fail this capture's own execution),
# which is satisfied by this being an independent Cloud Run Job resource;
# the two jobs happening to run identical container bytes is no different
# from two unrelated processes both being written in Python.
#
# max_retries = 1: a fetch from nflverse can hit a transient network error;
# one retry absorbs that without the B1-2a crash-loop risk, because unlike
# the pipeline, this job's writes are already idempotent (append-only,
# change-detected -- capture_injury_snapshots.py inserts nothing on a re-run
# with unchanged source data) and non-destructive (no drop-and-rebuild step
# for a retry to race against).
resource "google_cloud_run_v2_job" "injury_capture" {
  name     = "nfl-injury-capture"
  location = var.region
  project  = var.project_id

  template {
    parallelism = 1
    task_count  = 1

    template {
      timeout         = "600s" # 10 min -- generous for fetching one season of injuries + depth charts from nflverse and diffing/loading to BigQuery
      max_retries     = 1
      service_account = google_service_account.injury_capture.email

      containers {
        image   = "gcr.io/${var.project_id}/nfl-data-pipeline:latest"
        command = ["python"]
        args    = ["scripts/capture_injury_snapshots.py"]

        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi" # one season of injuries (~6k rows) + depth charts (~35k rows) in pandas
          }
        }

        env {
          name  = "BIGQUERY_PROJECT"
          value = var.project_id
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image]
  }

  depends_on = [google_service_account.injury_capture]
}

# Cloud Scheduler invokes this job's :run endpoint using the job's own SA
# (same pattern as every other scheduler entry in scheduler.tf) -- scoped to
# just this job, not the project-wide roles/run.developer the pipeline SA
# has, since this SA never needs to invoke anything else.
resource "google_cloud_run_v2_job_iam_member" "injury_capture_invoke_self" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.injury_capture.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.injury_capture.email}"
}

# ── Production Refresh Cloud Run Job ────────────────────────────────────────────

resource "google_cloud_run_v2_job" "production_refresh" {
  name     = "nfl-production-refresh"
  location = var.region
  project  = var.project_id

  template {
    parallelism = 1
    task_count  = 1

    template {
      timeout         = "120s"
      service_account = google_service_account.runner.email

      containers {
        image = "gcr.io/${var.project_id}/nfl-experiment-runner:latest"
        args  = ["python", "backtests/run_production_refresh.py"]

        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi"
          }
        }

        env {
          name  = "BIGQUERY_PROJECT"
          value = var.project_id
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image]
  }

  depends_on = [google_service_account.runner]
}
