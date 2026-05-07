# Secret Manager secrets (values managed manually via gcloud, not in TF state)
# This prevents secrets from appearing in terraform.tfstate

resource "google_secret_manager_secret" "anthropic_api_key" {
  secret_id = "ANTHROPIC_API_KEY"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "owner_api_key" {
  secret_id = "OWNER_API_KEY"
  replication {
    auto {}
  }
}

# Note: Secret values are NOT created by Terraform.
# Manually set them via:
#   gcloud secrets versions add ANTHROPIC_API_KEY --data-file=-
#   gcloud secrets versions add OWNER_API_KEY --data-file=-
