import os
import uuid
from google.cloud import storage

storage_client = storage.Client()
GCS_BUCKET = os.getenv("GCS_BUCKET_NAME", "cutto-videos")


def ensure_bucket_exists():
    """Create the GCS bucket if it doesn't exist."""
    try:
        storage_client.get_bucket(GCS_BUCKET)
    except Exception:
        bucket = storage_client.create_bucket(GCS_BUCKET, location="us-central1")
        print(f"Created bucket: {bucket.name}")


async def upload_file(file_bytes: bytes, filename: str, content_type: str) -> str:
    """Upload a file to GCS and return its URI."""
    job_id = str(uuid.uuid4())
    blob_name = f"uploads/{job_id}/{filename}"
    bucket = storage_client.bucket(GCS_BUCKET)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(file_bytes, content_type=content_type)
    return f"gs://{GCS_BUCKET}/{blob_name}", job_id
