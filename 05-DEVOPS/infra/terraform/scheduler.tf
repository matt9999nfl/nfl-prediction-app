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

    oauth_token {
      service_account_email = google_service_account.pipeline.email
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

    oauth_token {
      service_account_email = google_service_account.pipeline.email
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

    oauth_token {
      service_account_email = google_service_account.pipeline.email
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

    oauth_token {
      service_account_email = google_service_account.pipeline.email
    }
  }

  depends_on = [google_cloud_run_v2_job.pipeline_gameday]
}

# Injury / Depth-Chart Snapshot Capture — Daily (08:00 UTC)
#
# WRITTEN, NOT APPLIED OR DEPLOYED (PROMPT-CAPTURE-INJURY-SNAPSHOTS.md,
# design point 2). nflverse's injuries feed refreshes once daily; 08:00 UTC
# is one hour after that refresh, so every day's capture sees that day's
# data rather than racing it (checked 2026-09-19 against a live fetch).
#
# What daily buys over the pipeline's existing weekly cadence (Mon/Tue/Fri):
# it captures the Wednesday/Thursday/Friday DNP-Limited-Full practice-status
# progression that a single weekly snapshot cannot -- that progression does
# not exist anywhere in the archive (PLAN-BUCKET1-DATA-COVERAGE.md) and
# never will unless it is captured as it happens.
# What it does NOT buy: anything intra-day. A same-day correction to a
# report after 08:00 UTC is invisible until the next day's capture; this is
# a once-a-day clock, not a continuous one. A capture on a day with no new
# report (weekends, most of Monday/Tuesday) costs one wasted invocation --
# the change-detection in capture_injury_snapshots.py inserts zero rows and
# that is the expected, correct outcome, not a failure.
resource "google_cloud_scheduler_job" "injury_capture_daily" {
  name             = "nfl-injury-capture-daily"
  description      = "Daily nflverse injury report + depth chart snapshot capture"
  schedule         = "0 8 * * *" # every day, 08:00 UTC
  time_zone        = "UTC"
  region           = var.region
  attempt_deadline = "320s"

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/nfl-injury-capture:run"

    headers = {
      "Content-Type" = "application/json"
    }

    oauth_token {
      service_account_email = google_service_account.injury_capture.email
    }
  }

  depends_on = [google_cloud_run_v2_job.injury_capture]
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

    oauth_token {
      service_account_email = google_service_account.runner.email
    }
  }

  depends_on = [google_cloud_run_v2_job.production_refresh]
}
