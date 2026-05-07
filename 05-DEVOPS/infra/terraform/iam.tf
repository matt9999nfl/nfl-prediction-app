# ── Service Accounts ──────────────────────────────────────────────────────────

resource "google_service_account" "api" {
  account_id   = "nfl-api-sa"
  display_name = "NFL Prediction App — Backend API"
  description  = "Service account for Cloud Run API service"
}

resource "google_service_account" "runner" {
  account_id   = "nfl-runner-sa"
  display_name = "NFL Prediction App — Experiment Runner"
  description  = "Service account for Cloud Run Job experiment runner"
}

resource "google_service_account" "pipeline" {
  account_id   = "nfl-pipeline-sa"
  display_name = "NFL Prediction App — Data Pipeline"
  description  = "Service account for Cloud Run Job data pipeline"
}

resource "google_service_account" "terraform_ci" {
  account_id   = "terraform-ci"
  display_name = "Terraform CI"
  description  = "Service account used by GitHub Actions to apply Terraform"
}

# ── API Service Account IAM Roles ──────────────────────────────────────────────

# BigQuery roles
resource "google_bigquery_dataset_iam_member" "api_reader_platform" {
  dataset_id = "platform"
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.api.email}"
}

resource "google_bigquery_dataset_iam_member" "api_reader_experiments" {
  dataset_id = "experiments"
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.api.email}"
}

resource "google_bigquery_dataset_iam_member" "api_reader_curated" {
  dataset_id = "curated"
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.api.email}"
}

resource "google_bigquery_dataset_iam_member" "api_editor_platform" {
  dataset_id = "platform"
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.api.email}"
}

resource "google_bigquery_dataset_iam_member" "api_editor_experiments_runs" {
  dataset_id = "experiments"
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "api_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# Cloud Storage
resource "google_storage_bucket_iam_member" "api_uploads" {
  bucket = "nfl-model-471509-uploads"
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.api.email}"
}

# Cloud Run Job invoker (experiment runner)
resource "google_cloud_run_v2_job_iam_member" "api_invoke_runner" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.experiment_runner.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.api.email}"
}

# Secret Manager access
resource "google_secret_manager_secret_iam_member" "api_anthropic_key" {
  secret_id = "ANTHROPIC_API_KEY"
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

resource "google_secret_manager_secret_iam_member" "api_owner_key" {
  secret_id = "OWNER_API_KEY"
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

# ── Runner Service Account IAM Roles ───────────────────────────────────────────

resource "google_bigquery_dataset_iam_member" "runner_reader_curated" {
  dataset_id = "curated"
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.runner.email}"
}

resource "google_bigquery_dataset_iam_member" "runner_editor_experiments" {
  dataset_id = "experiments"
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.runner.email}"
}

resource "google_bigquery_dataset_iam_member" "runner_editor_platform" {
  dataset_id = "platform"
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.runner.email}"
}

resource "google_project_iam_member" "runner_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.runner.email}"
}

# Cloud Run Job invoker for production refresh to trigger runs
resource "google_project_iam_member" "runner_invoke_jobs" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.runner.email}"
}

# ── Pipeline Service Account IAM Roles ─────────────────────────────────────────

resource "google_bigquery_dataset_iam_member" "pipeline_editor_raw" {
  dataset_id = "raw_nflfastr"
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_bigquery_dataset_iam_member" "pipeline_editor_curated" {
  dataset_id = "curated"
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_project_iam_member" "pipeline_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

# ── Terraform CI Service Account IAM Roles ─────────────────────────────────────

resource "google_project_iam_member" "terraform_ci_editor" {
  project = var.project_id
  role    = "roles/editor"
  member  = "serviceAccount:${google_service_account.terraform_ci.email}"
}

resource "google_project_iam_member" "terraform_ci_security_admin" {
  project = var.project_id
  role    = "roles/iam.securityAdmin"
  member  = "serviceAccount:${google_service_account.terraform_ci.email}"
}
