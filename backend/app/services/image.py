import base64
import io
from typing import Optional

import httpx
from PIL import Image

from app.services.storage import upload_image_bytes, r2_configured

MAX_BYTES = 10 * 1024 * 1024  # 10 MB


def _to_webp_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="WEBP", quality=85)
    return buf.getvalue()


async def process_and_upload(
    image_base64: Optional[str] = None,
    image_url: Optional[str] = None,
) -> str:
    """
    Accept base64 or URL, validate, convert to WebP, upload to R2.

    When R2 is not configured and a plain URL is provided, the original URL
    is stored directly — no local disk involved, so Railway restarts can't
    break it. When R2 IS configured, all images are always re-hosted.
    """
    if not r2_configured() and image_url and not image_base64:
        # Pass-through: store the original URL as-is.
        # Works for DALL·E (~2h expiry) and permanent sources (Pollinations).
        return image_url

    if image_base64:
        raw = base64.b64decode(image_base64)
    elif image_url:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(image_url, follow_redirects=True)
            resp.raise_for_status()
            raw = resp.content
    else:
        raise ValueError("Either image_base64 or image_url must be provided")

    if len(raw) > MAX_BYTES:
        raise ValueError("Image exceeds 10 MB limit")

    img = Image.open(io.BytesIO(raw))
    webp_bytes = _to_webp_bytes(img)
    return await upload_image_bytes(webp_bytes, "image/webp")
