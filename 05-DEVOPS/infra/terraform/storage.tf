# ── Cloud Storage: Uploads Bucket ─────────────────────────────────────────────

resource "google_storage_bucket" "uploads" {
  name          = "nfl-model-471509-uploads"
  location      = var.region
  storage_class = "STANDARD"
  project       = var.project_id

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 3
    }
    action {
      type = "Delete"
    }
  }
}

# ── Cloud Storage: Frontend Bucket ────────────────────────────────────────────

resource "google_storage_bucket" "frontend" {
  name          = "nfl-frontend-${var.project_id}"
  location      = var.region
  storage_class = "STANDARD"
  project       = var.project_id

  website {
    main_page_suffix = "index.html"
    not_found_page   = "index.html"  # Critical for client-side routing
  }

  versioning {
    enabled = false
  }

  cors {
    origin          = ["*"]
    method          = ["GET", "HEAD"]
    response_header = ["Content-Type", "Cache-Control"]
    max_age_seconds = 3600
  }
}

# Public read access for frontend bucket
resource "google_storage_bucket_iam_member" "frontend_public" {
  bucket = google_storage_bucket.frontend.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# ── Cloud CDN Backend Bucket ───────────────────────────────────────────────────

resource "google_compute_backend_bucket" "frontend" {
  name            = "nfl-frontend-backend"
  description     = "Frontend static site backend for Cloud CDN"
  bucket_name     = google_storage_bucket.frontend.name
  project         = var.project_id
  enable_cdn      = true

  cdn_policy {
    cache_mode        = "CACHE_ALL_STATIC"
    default_ttl       = 3600
    max_ttl           = 86400
    client_ttl        = 3600
    negative_caching  = false
    serve_while_stale = 86400
  }
}

# ── Cloud Load Balancer (HTTPS + CDN) ──────────────────────────────────────────

resource "google_compute_url_map" "frontend" {
  name            = "nfl-frontend-load-balancer"
  description     = "Load balancer for frontend CDN"
  default_service = google_compute_backend_bucket.frontend.id
  project         = var.project_id
}

# HTTP proxy — no domain yet. Once a domain is purchased:
#   1. Add google_compute_managed_ssl_certificate with that domain
#   2. Switch to google_compute_target_https_proxy + port 443
resource "google_compute_target_http_proxy" "frontend" {
  name    = "nfl-frontend-http-proxy"
  url_map = google_compute_url_map.frontend.id
  project = var.project_id
}

resource "google_compute_global_forwarding_rule" "frontend" {
  name                  = "nfl-frontend-forwarding-rule"
  load_balancing_scheme = "EXTERNAL"
  project               = var.project_id
  ip_protocol           = "TCP"
  port_range            = "80"
  target                = google_compute_target_http_proxy.frontend.id
}
