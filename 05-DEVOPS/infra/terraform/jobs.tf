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

  depends_on = [google_service_account.pipeline]
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

  depends_on = [google_service_account.runner]
}
