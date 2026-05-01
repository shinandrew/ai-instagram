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
  1. Query text is embedded with text-embedding-3-small (5s timeout, no retries)
  2. Cosine similarity against stored vectors (in-memory numpy)
"""

import base64
import logging
import math

logger = logging.getLogger(__name__)

OPENAI_EMBED_MODEL = "text-embedding-3-small"
OPENAI_VISION_MODEL = "gpt-4o-mini"

_VISION_PROMPT = (
    "Describe the visual content of this image concisely in 2-3 sentences. "
    "Include: main subjects, colors, mood, artistic style, and setting."
)

# Module-level OpenAI client — httpx-based, persistent connections, thread-safe.
_client = None
_client_key: str | None = None


def _get_client(api_key: str):
    global _client, _client_key
    if _client is None or _client_key != api_key:
        from openai import OpenAI
        # max_retries=2 for background tasks; search overrides timeout per-call
        _client = OpenAI(api_key=api_key, timeout=30.0, max_retries=2)
        _client_key = api_key
    return _client


def embed_text(
    text: str,
    openai_api_key: str,
    timeout: float = 30.0,
) -> list[float] | None:
    """
    Embed text via OpenAI text-embedding-3-small.
    Returns a 1536-dim float list, or None on failure.
    Pass timeout=5.0 for search path so failures are fast.
    """
    if not text or not openai_api_key:
        return None
    try:
        client = _get_client(openai_api_key)
        resp = client.embeddings.create(
            input=text,
            model=OPENAI_EMBED_MODEL,
            timeout=timeout,
        )
        return resp.data[0].embedding
    except Exception as exc:
        logger.warning("embed_text failed: %s", exc)
        return None


def describe_image_bytes(image_bytes: bytes, openai_api_key: str) -> str | None:
    """
    Use GPT-4o-mini vision to produce a rich visual description from raw bytes.
    The description is later embedded with embed_text() for semantic search.
    """
    if not image_bytes or not openai_api_key:
        return None
    try:
        import base64 as _b64
        b64 = _b64.b64encode(image_bytes).decode()
        client = _get_client(openai_api_key)
        resp = client.chat.completions.create(
            model=OPENAI_VISION_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/webp;base64,{b64}"}},
                    {"type": "text", "text": _VISION_PROMPT},
                ],
            }],
            max_tokens=150,
            timeout=45.0,
        )
        return resp.choices[0].message.content
    except Exception as exc:
        logger.warning("describe_image_bytes failed: %s", exc)
        return None


def describe_image_url(image_url: str, openai_api_key: str) -> str | None:
    """
    Use GPT-4o-mini vision to produce a rich visual description from a URL.
    OpenAI's servers fetch the URL directly — works even if our backend can't.
    """
    if not image_url or not openai_api_key:
        return None
    try:
        client = _get_client(openai_api_key)
        resp = client.chat.completions.create(
            model=OPENAI_VISION_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": _VISION_PROMPT},
                ],
            }],
            max_tokens=150,
            timeout=45.0,
        )
        return resp.choices[0].message.content
    except Exception as exc:
        logger.warning("describe_image_url failed: %s", exc)
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
