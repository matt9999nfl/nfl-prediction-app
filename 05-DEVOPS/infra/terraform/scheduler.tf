# ── Cloud Scheduler Jobs ──────────────────────────────────────────────────────

# Data Pipeline — Full run (Tuesday 6am ET = 11:00 UTC)
resource "google_cloud_scheduler_job" "pipeline_full_weekly" {
  name             = "nfl-pipeline-full-weekly"
  description      = "Weekly full nflfastR data ingest"
  schedule         = "0 11 * * 2"  # Tuesday 11:00 UTC
  time_zone        = "UTC"
  region           = var.region
  attempt_deadline = "320s"

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/nfl-pipeline-full:run"

    headers = {
      "Content-Type" = "application/json"
    }

    oidc_token {
      service_account_email = google_service_account.pipeline.email
      audience              = "https://${var.region}-run.googleapis.com/"
    }
  }

  depends_on = [google_cloud_run_v2_job.pipeline_full]
}

# Data Pipeline — Gameday refresh (Monday 12am ET = 5:00 UTC)
resource "google_cloud_scheduler_job" "pipeline_gameday_sunday" {
  name             = "nfl-pipeline-gameday-sunday"
  description      = "Post-Sunday-games nflfastR refresh"
  schedule         = "0 5 * * 1"  # Monday 5:00 UTC
  time_zone        = "UTC"
  region           = var.region
  attempt_deadline = "320s"

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/nfl-pipeline-gameday:run"

    headers = {
      "Content-Type" = "application/json"
    }

    oidc_token {
      service_account_email = google_service_account.pipeline.email
      audience              = "https://${var.region}-run.googleapis.com/"
    }
  }

  depends_on = [google_cloud_run_v2_job.pipeline_gameday]
}

# Data Pipeline — Gameday refresh (Tuesday 2am ET = 7:00 UTC)
resource "google_cloud_scheduler_job" "pipeline_gameday_monday" {
  name             = "nfl-pipeline-gameday-monday"
  description      = "Post-Monday-Night-Football nflfastR refresh"
  schedule         = "0 7 * * 2"  # Tuesday 7:00 UTC
  time_zone        = "UTC"
  region           = var.region
  attempt_deadline = "320s"

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/nfl-pipeline-gameday:run"

    headers = {
      "Content-Type" = "application/json"
    }

    oidc_token {
      service_account_email = google_service_account.pipeline.email
      audience              = "https://${var.region}-run.googleapis.com/"
    }
  }

  depends_on = [google_cloud_run_v2_job.pipeline_gameday]
}

# Data Pipeline — Gameday refresh (Friday 12am ET ≈ 5:00 UTC Thursday)
resource "google_cloud_scheduler_job" "pipeline_gameday_thursday" {
  name             = "nfl-pipeline-gameday-thursday"
  description      = "Post-Thursday-Night-Football nflfastR refresh"
  schedule         = "0 5 * * 5"  # Thursday 5:00 UTC (actually Friday morning UTC for Thu night games)
  time_zone        = "UTC"
  region           = var.region
  attempt_deadline = "320s"

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/nfl-pipeline-gameday:run"

    headers = {
      "Content-Type" = "application/json"
    }

    oidc_token {
      service_account_email = google_service_account.pipeline.email
      audience              = "https://${var.region}-run.googleapis.com/"
    }
  }

  depends_on = [google_cloud_run_v2_job.pipeline_gameday]
}

# Production Refresh — Weekly (Tuesday 9am ET = 14:00 UTC)
resource "google_cloud_scheduler_job" "production_refresh_weekly" {
  name             = "nfl-production-refresh-weekly"
  description      = "Weekly refresh of gate-passed experiments for current-week predictions"
  schedule         = "0 14 * * 2"  # Tuesday 14:00 UTC
  time_zone        = "UTC"
  region           = var.region
  attempt_deadline = "320s"

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/nfl-production-refresh:run"

    headers = {
      "Content-Type" = "application/json"
    }

    oidc_token {
      service_account_email = google_service_account.runner.email
      audience              = "https://${var.region}-run.googleapis.com/"
    }
  }

  depends_on = [google_cloud_run_v2_job.production_refresh]
}
