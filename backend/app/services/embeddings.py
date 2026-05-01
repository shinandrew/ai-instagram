"""
Embedding pipeline for semantic search.

Image embeddings: CLIP (openai/clip-vit-base-patch32) via HuggingFace Inference API.
  - embed_image_bytes(): 512-dim, embedded in-memory at post creation time.

Text embeddings: OpenAI text-embedding-3-small via OpenAI API.
  - embed_text(): 1536-dim, used for search queries and caption backfill.

The two vector spaces are different dimensions and not directly comparable.
cosine_similarity() returns 0.0 on dimension mismatch, so they coexist safely
in the same DB column. Text search uses OpenAI-embedded captions; visual search
(future) will use CLIP image embeddings.
"""

import json
import logging
import math
import urllib.request

logger = logging.getLogger(__name__)

CLIP_MODEL = "openai/clip-vit-base-patch32"
_HF_BASE = "https://api-inference.huggingface.co"

OPENAI_EMBED_MODEL = "text-embedding-3-small"
_OPENAI_BASE = "https://api.openai.com/v1"


def embed_image_bytes(image_bytes: bytes, hf_token: str) -> list[float] | None:
    """
    Embed raw image bytes with CLIP — no URL fetching.
    Use this when the bytes are already in memory (e.g. right after upload).
    Returns a 512-dim float list, or None on failure.
    """
    if not image_bytes or not hf_token:
        return None

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
        if isinstance(result, list) and result and isinstance(result[0], list):
            return result[0]
        if isinstance(result, list) and result and isinstance(result[0], (int, float)):
            return result
        logger.warning("Unexpected CLIP image response: %s", str(result)[:120])
        return None
    except Exception as exc:
        logger.warning("CLIP image embedding failed: %s", exc)
        return None


def embed_image(image_url: str, hf_token: str) -> list[float] | None:
    """
    Fetch the image from its URL and embed it with CLIP.
    Prefer embed_image_bytes() when you already have the bytes in memory.
    """
    if not image_url or not hf_token:
        return None
    try:
        with urllib.request.urlopen(image_url, timeout=20) as r:
            image_bytes = r.read()
    except Exception as exc:
        logger.warning("Failed to fetch image %s: %s", image_url[:80], exc)
        return None
    return embed_image_bytes(image_bytes, hf_token)


def embed_text(text: str, openai_api_key: str) -> list[float] | None:
    """
    Embed text via OpenAI text-embedding-3-small.
    Returns a 1536-dim float list, or None on failure.
    Used for search queries and caption backfill.
    """
    if not text or not openai_api_key:
        return None

    body = json.dumps({"input": text, "model": OPENAI_EMBED_MODEL}).encode()
    req = urllib.request.Request(
        f"{_OPENAI_BASE}/embeddings",
        data=body,
        headers={
            "Authorization": f"Bearer {openai_api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        return result["data"][0]["embedding"]
    except Exception as exc:
        logger.warning("OpenAI text embedding failed: %s", exc)
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    denom = norm_a * norm_b
    return dot / denom if denom > 0 else 0.0
