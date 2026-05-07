# ── BACKEND-API Cloud Run Service ──────────────────────────────────────────────

resource "google_cloud_run_service" "api" {
  name            = "nfl-backend-api"
  location        = var.region
  project         = var.project_id

  template {
    spec {
      service_account_name = google_service_account.api.email

      containers {
        # Image is updated by CI pipeline, not Terraform
        # Initial image can be anything; CI will push the real one
        image = "gcr.io/${var.project_id}/nfl-backend-api:latest"

        ports {
          container_port = 8080
        }

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

        env {
          name = "ANTHROPIC_API_KEY"
          value_from {
            secret_key_ref {
              name = google_secret_manager_secret.anthropic_api_key.secret_id
              key  = "latest"
            }
          }
        }

        env {
          name = "OWNER_API_KEY"
          value_from {
            secret_key_ref {
              name = google_secret_manager_secret.owner_api_key.secret_id
              key  = "latest"
            }
          }
        }
      }

      timeout_seconds       = 60
      container_concurrency = 80
    }

    metadata {
      annotations = {
        "autoscaling.knative.dev/min-scale" = "0"
        "autoscaling.knative.dev/max-scale" = "3"
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }

  depends_on = [google_secret_manager_secret.anthropic_api_key, google_secret_manager_secret.owner_api_key]
}

# Public ingress policy
resource "google_cloud_run_service_iam_member" "api_public" {
  service  = google_cloud_run_service.api.name
  location = google_cloud_run_service.api.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
