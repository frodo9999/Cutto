import os
import uuid
import asyncio
from google.cloud import storage

storage_client = storage.Client()
GCS_BUCKET = os.getenv("GCS_BUCKET_NAME", "cutto-videos")


def ensure_bucket_exists():
    try:
        storage_client.get_bucket(GCS_BUCKET)
    except Exception:
        bucket = storage_client.create_bucket(GCS_BUCKET, location="us-central1")
        print(f"Created bucket: {bucket.name}")


def _upload_sync(file_bytes: bytes, blob_name: str, content_type: str):
    """Synchronous upload - run in thread pool."""
    bucket = storage_client.bucket(GCS_BUCKET)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(file_bytes, content_type=content_type, timeout=300)


async def upload_file(file_bytes: bytes, filename: str, content_type: str):
    """Upload a file to GCS asynchronously using thread pool."""
    job_id = str(uuid.uuid4())
    blob_name = f"uploads/{job_id}/{filename}"

    # Run sync upload in thread pool to avoid blocking
    await asyncio.to_thread(_upload_sync, file_bytes, blob_name, content_type)

    return f"gs://{GCS_BUCKET}/{blob_name}", job_id