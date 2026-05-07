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
