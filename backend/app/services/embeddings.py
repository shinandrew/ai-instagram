"""
Embedding pipeline for semantic image search.

All embeddings use OpenAI text-embedding-3-small (1536-dim) so every vector
lives in the same space and cosine similarity is directly comparable.

Index-time flow for new posts:
  1. GPT-4o-mini vision describes the image visually (subjects, colors, mood, style)
  2. That description is embedded with text-embedding-3-small
  3. Fallback: caption text embedding if vision fails

Backfill flow for existing posts:
  1. Same vision → embed pipeline, passing the R2 URL directly to OpenAI
     (OpenAI servers can fetch public R2 URLs even though our backend cannot)
  2. Fallback: caption text embedding

Search-time flow:
  1. Query text is embedded with text-embedding-3-small
  2. Cosine similarity against stored vectors
"""

import base64
import json
import logging
import math
import time
import urllib.request

logger = logging.getLogger(__name__)

OPENAI_EMBED_MODEL = "text-embedding-3-small"
OPENAI_VISION_MODEL = "gpt-4o-mini"
_OPENAI_BASE = "https://api.openai.com/v1"

_VISION_PROMPT = (
    "Describe the visual content of this image concisely in 2-3 sentences. "
    "Include: main subjects, colors, mood, artistic style, and setting."
)


def _openai_post(url: str, body: dict, openai_api_key: str, timeout: int = 30) -> dict | None:
    """POST to OpenAI API with 3-attempt retry on transient errors."""
    encoded = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=encoded,
        headers={
            "Authorization": f"Bearer {openai_api_key}",
            "Content-Type": "application/json",
        },
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except Exception as exc:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            logger.warning("OpenAI API call to %s failed: %s", url, exc)
            return None


def describe_image_bytes(image_bytes: bytes, openai_api_key: str) -> str | None:
    """
    Use GPT-4o-mini vision to produce a rich visual description from raw bytes.
    The description is later embedded with embed_text() for semantic search.
    """
    if not image_bytes or not openai_api_key:
        return None

    b64 = base64.b64encode(image_bytes).decode()
    result = _openai_post(
        f"{_OPENAI_BASE}/chat/completions",
        {
            "model": OPENAI_VISION_MODEL,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/webp;base64,{b64}"}},
                    {"type": "text", "text": _VISION_PROMPT},
                ],
            }],
            "max_tokens": 150,
        },
        openai_api_key,
        timeout=45,
    )
    if result:
        return result["choices"][0]["message"]["content"]
    return None


def describe_image_url(image_url: str, openai_api_key: str) -> str | None:
    """
    Use GPT-4o-mini vision to produce a rich visual description from a URL.
    OpenAI's servers fetch the URL directly — works even if our backend can't.
    """
    if not image_url or not openai_api_key:
        return None

    result = _openai_post(
        f"{_OPENAI_BASE}/chat/completions",
        {
            "model": OPENAI_VISION_MODEL,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": _VISION_PROMPT},
                ],
            }],
            "max_tokens": 150,
        },
        openai_api_key,
        timeout=45,
    )
    if result:
        return result["choices"][0]["message"]["content"]
    return None


def embed_text(text: str, openai_api_key: str) -> list[float] | None:
    """
    Embed text via OpenAI text-embedding-3-small.
    Returns a 1536-dim float list, or None on failure.
    """
    if not text or not openai_api_key:
        return None

    result = _openai_post(
        f"{_OPENAI_BASE}/embeddings",
        {"input": text, "model": OPENAI_EMBED_MODEL},
        openai_api_key,
    )
    if result:
        return result["data"][0]["embedding"]
    return None


def embed_image_bytes(image_bytes: bytes, hf_token: str) -> list[float] | None:
    """Legacy CLIP embedding via HuggingFace — kept for reference but HF API is broken."""
    return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    denom = norm_a * norm_b
    return dot / denom if denom > 0 else 0.0
