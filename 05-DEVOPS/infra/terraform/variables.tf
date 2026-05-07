variable "project_id" {
  description = "GCP Project ID"
  type        = string
  default     = "nfl-model-471509"
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "alert_email" {
  description = "Email for alert notifications"
  type        = string
  default     = "matt.lilley4@gmail.com"
}
