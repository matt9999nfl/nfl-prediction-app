"""
Google Cloud Storage client.

Bucket: nfl-model-471509-uploads  (created on first upload if absent).
Access: uniform bucket-level access (no per-object ACLs), per spec.

All uploads are stored at:
  gs://nfl-model-471509-uploads/{dataset_id}/raw.{ext}
"""
import logging

import google.api_core.exceptions
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
    Return the upload bucket, creating it (with uniform access) if it doesn't exist.
    Logs a warning if creation fails due to insufficient permissions — DEVOPS should
    pre-create the bucket in that case.
    """
    try:
        return client.get_bucket(BUCKET_NAME)
    except google.api_core.exceptions.NotFound:
        logger.info("Bucket %s not found — creating it", BUCKET_NAME)
        try:
            bucket = client.create_bucket(
                BUCKET_NAME,
                location="US",
            )
            bucket.iam_configuration.uniform_bucket_level_access_enabled = True
            bucket.patch()
            logger.info("Created bucket %s with uniform access", BUCKET_NAME)
            return bucket
        except Exception as exc:
            logger.error(
                "Could not create bucket %s: %s. DEVOPS should pre-create it.",
                BUCKET_NAME, exc,
            )
            raise


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
