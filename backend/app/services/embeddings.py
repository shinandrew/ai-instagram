"""
CLIP embedding pipeline for semantic image search.

Images are embedded directly via CLIP (openai/clip-vit-base-patch32) using the
HuggingFace Inference API. Search queries are embedded via the same CLIP text
encoder so image and text vectors live in the same 512-dim space.

No OpenAI usage — runs entirely on the free HF Inference API (HF_TOKEN required).
"""

import json
import logging
import math
import urllib.request

logger = logging.getLogger(__name__)

CLIP_MODEL = "openai/clip-vit-base-patch32"
EMBEDDING_DIM = 512
_HF_BASE = "https://api-inference.huggingface.co"


def embed_image(image_url: str, hf_token: str) -> list[float] | None:
    """
    Fetch the image from its URL and embed it with CLIP.
    Sends raw image bytes to HF as application/octet-stream.
    Returns a 512-dim float list, or None on failure.
    """
    if not image_url or not hf_token:
        return None

    # Fetch image bytes
    try:
        with urllib.request.urlopen(image_url, timeout=20) as r:
            image_bytes = r.read()
    except Exception as exc:
        logger.warning("Failed to fetch image %s: %s", image_url[:80], exc)
        return None

    # Send to CLIP
    url = f"{_HF_BASE}/models/{CLIP_MODEL}"
    req = urllib.request.Request(
        url,
        data=image_bytes,
        headers={
            "Authorization": f"Bearer {hf_token}",
            "Content-Type": "application/octet-stream",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        # Response: [[...512 floats...]] or [...512 floats...]
        if isinstance(result, list) and result and isinstance(result[0], list):
            return result[0]
        if isinstance(result, list) and result and isinstance(result[0], (int, float)):
            return result
        logger.warning("Unexpected CLIP image response: %s", str(result)[:120])
        return None
    except Exception as exc:
        logger.warning("CLIP image embedding failed for %s: %s", image_url[:80], exc)
        return None


def embed_text(text: str, hf_token: str) -> list[float] | None:
    """
    Embed a text query via the CLIP text encoder.
    Returns a 512-dim float list in the same space as embed_image().
    """
    if not text or not hf_token:
        return None

    url = f"{_HF_BASE}/pipeline/feature-extraction/{CLIP_MODEL}"
    body = json.dumps({"inputs": text, "options": {"wait_for_model": True}}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {hf_token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        if isinstance(result, list) and result and isinstance(result[0], list):
            return result[0]
        if isinstance(result, list) and result and isinstance(result[0], (int, float)):
            return result
        logger.warning("Unexpected CLIP text response: %s", str(result)[:120])
        return None
    except Exception as exc:
        logger.warning("CLIP text embedding failed: %s", exc)
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    denom = norm_a * norm_b
    return dot / denom if denom > 0 else 0.0
