# ── Notification Channel ──────────────────────────────────────────────────────

resource "google_monitoring_notification_channel" "email" {
  display_name = "Email — ${var.alert_email}"
  type         = "email"
  labels = {
    email_address = var.alert_email
  }
  enabled = true
}

# ── Alert: Cloud Run 5xx Rate ──────────────────────────────────────────────────

resource "google_monitoring_alert_policy" "api_5xx" {
  display_name = "Cloud Run API — 5xx Error Rate > 5%"
  combiner     = "OR"
  enabled      = true

  conditions {
    display_name = "5xx rate > 5% over 5 minutes"

    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"nfl-backend-api\" AND metric.type=\"run.googleapis.com/request_count\" AND metric.labels.response_code_class=\"5xx\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.05
      
      aggregations {
        alignment_period  = "60s"
        per_series_aligner = "ALIGN_RATE"
      }

      # INC-002 (2026-09-08): without an explicit trigger, the API defaults it to
      # zero and the console reports "0% of time series cross threshold" -- the
      # policy is enabled, looks correct, and can never fire. This omission is
      # why no alert email was ever received.
      trigger {
        count = 1
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]
  documentation {
    content   = "Alert triggered when nfl-backend-api has > 5% 5xx responses over 5 minutes. See runbook: 05-DEVOPS/runbooks/api-down.md"
    mime_type = "text/markdown"
  }
}

# ── Alert: Cloud Run Job Failure ───────────────────────────────────────────────

resource "google_monitoring_alert_policy" "job_failure" {
  display_name = "Cloud Run Job — Execution Failed"
  combiner     = "OR"
  enabled      = true

  conditions {
    display_name = "Job execution failed"

    condition_threshold {
      filter          = "resource.type=\"cloud_run_job\" AND metric.type=\"run.googleapis.com/job/completed_execution_count\" AND metric.labels.result=\"failed\""
      # INC-002: was "60s". A failed execution is a single counted event, not a
      # sustained state -- requiring the condition to hold for a full minute can
      # miss it entirely. Fire on the first occurrence.
      duration        = "0s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0

      aggregations {
        alignment_period  = "60s"
        # INC-002: was ALIGN_RATE. A rate over a sparse counter that increments
        # once per failure can align to a value that never clears the threshold.
        # ALIGN_DELTA counts the failures in the window, which is the question
        # being asked: did a job fail?
        per_series_aligner = "ALIGN_DELTA"
      }

      # INC-002: the omission that made this policy silent. See the 5xx policy above.
      trigger {
        count = 1
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]
  documentation {
    content   = "Alert triggered when a scheduled Cloud Run Job fails. See runbook: 05-DEVOPS/runbooks/pipeline-failure.md"
    mime_type = "text/markdown"
  }
}

# ── Budget Alert ───────────────────────────────────────────────────────────────
# NOTE: Billing budgets are created at the billing account level, not the project level.
# The billing_account ID must be obtained from:
#   gcloud billing accounts list
# Then added to variables.tf as var.billing_account_id and passed to this resource.
#
# For now, this resource is commented out. Uncomment and configure after bootstrap.
#
# resource "google_billing_budget" "nfl_monthly" {
#   billing_account = var.billing_account_id
#   display_name    = "nfl-prediction-app-monthly"
#   budget_filter {
#     projects = ["projects/${var.project_id}"]
#   }
#
#   amount {
#     specified_amount {
#       currency_code = "USD"
#       units         = "50"
#     }
#   }
#
#   threshold_rules {
#     threshold_percent = 50.0
#   }
#
#   threshold_rules {
#     threshold_percent = 80.0
#   }
#
#   threshold_rules {
#     threshold_percent = 100.0
#   }
#
#   notification_config {
#     notification_channels = [google_monitoring_notification_channel.email.id]
#     pubsub_topic          = google_pubsub_topic.billing_alerts.id
#   }
# }
#
# resource "google_pubsub_topic" "billing_alerts" {
#   name = "nfl-billing-alerts"
# }
