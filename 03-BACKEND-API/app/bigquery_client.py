"""
BigQuery client singleton.

On Cloud Run the service account attached to the service supplies credentials
automatically (ADC).  For local development, run:
    gcloud auth application-default login
or set GOOGLE_APPLICATION_CREDENTIALS to a service-account key file path.
"""
from google.cloud import bigquery

from app.config import settings

_client: bigquery.Client | None = None


def get_client() -> bigquery.Client:
    """Return the module-level BigQuery client, creating it on first call."""
    global _client
    if _client is None:
        _client = bigquery.Client(project=settings.bigquery_project)
    return _client
