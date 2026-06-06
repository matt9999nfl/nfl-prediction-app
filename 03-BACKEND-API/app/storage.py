"""
Google Cloud Storage client.

Bucket: nfl-model-471509-uploads  (created on first upload if absent).
Access: uniform bucket-level access (no per-object ACLs), per spec.

All uploads are stored at:
  gs://nfl-model-471509-uploads/{dataset_id}/raw.{ext}
"""
import logging

from google.cloud import storage

from app.config import settings

logger = logging.getLogger(__name__)

BUCKET_NAME = "nfl-model-471509-uploads"

_storage_client: storage.Client | None = None


def get_storage_client() -> storage.Client:
    """Return the module-level GCS client, creating it on first call."""
    global _storage_client
    if _storage_client is None:
        _storage_client = storage.Client(project=settings.bigquery_project)
    return _storage_client


def _get_or_create_bucket(client: storage.Client) -> storage.Bucket:
    """
    Return a handle to the upload bucket.

    Uses client.bucket() (no API call) rather than client.get_bucket() so that
    the service account only needs storage.objectAdmin — not storage.buckets.get.
    The bucket is pre-created by DEVOPS; if it is genuinely absent the first
    upload_from_string call will raise a 404, which propagates to the caller.
    """
    return client.bucket(BUCKET_NAME)


def upload_file(
    client: storage.Client,
    dataset_id: str,
    content: bytes,
    ext: str,
) -> str:
    """
    Upload raw file bytes to GCS.

    Args:
        client:     GCS client.
        dataset_id: UUID of the dataset (used as the folder name).
        content:    Raw file bytes.
        ext:        File extension without dot, e.g. "csv", "xlsx", "json".

    Returns:
        GCS URI of the uploaded blob: gs://bucket/dataset_id/raw.ext
    """
    bucket = _get_or_create_bucket(client)
    blob_name = f"{dataset_id}/raw.{ext}"
    blob = bucket.blob(blob_name)
    blob.upload_from_string(content)
    uri = f"gs://{BUCKET_NAME}/{blob_name}"
    logger.info("Uploaded dataset %s to %s", dataset_id, uri)
    return uri
