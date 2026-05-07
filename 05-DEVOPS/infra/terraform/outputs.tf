output "api_url" {
  description = "URL of the deployed BACKEND-API Cloud Run service"
  value       = google_cloud_run_service.api.status[0].url
}

output "frontend_url" {
  description = "URL of the deployed FRONTEND static site"
  value       = google_compute_backend_bucket.frontend.self_link
}
