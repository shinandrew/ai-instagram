import uuid
import os
from pathlib import Path

import boto3
from botocore.config import Config

from app.config import settings

LOCAL_STORAGE_DIR = Path(__file__).parent.parent.parent / "local_uploads"


def _r2_configured() -> bool:
    return bool(settings.r2_account_id and settings.r2_account_id != "your-account-id")


def _get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


async def upload_image_bytes(image_bytes: bytes, content_type: str = "image/webp") -> str:
    """Upload image bytes to R2 (or local fallback) and return the public URL."""
    key = f"posts/{uuid.uuid4()}.webp"

    if _r2_configured():
        client = _get_r2_client()
        client.put_object(
            Bucket=settings.r2_bucket_name,
            Key=key,
            Body=image_bytes,
            ContentType=content_type,
        )
        return f"{settings.r2_public_url}/{key}"

    # Local dev fallback: save to disk, serve via /uploads/ static route
    LOCAL_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    filename = key.replace("/", "_")
    (LOCAL_STORAGE_DIR / filename).write_bytes(image_bytes)
    return f"http://localhost:8000/uploads/{filename}"
