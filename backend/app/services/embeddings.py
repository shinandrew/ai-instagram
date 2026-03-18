"""
Image embedding pipeline for semantic search.

Flow:
  image_url → GPT-4o-mini vision (rich visual description) → text-embedding-3-small → 1536-dim vector

The same embedding model is used for both image descriptions and search queries,
so cosine similarity between the two is meaningful.
"""

import logging
import math
from typing import Optional

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
VISION_MODEL = "gpt-4o-mini"
EMBEDDING_DIM = 1536


def _client(api_key: str):
    import openai
    return openai.OpenAI(api_key=api_key)


def describe_image(image_url: str, api_key: str) -> Optional[str]:
    """Call GPT-4o-mini vision to generate a rich visual description."""
    try:
        resp = _client(api_key).chat.completions.create(
            model=VISION_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url, "detail": "low"},
                    },
                    {
                        "type": "text",
                        "text": (
                            "Describe this image in 3 sentences. Cover: visual style and medium "
                            "(e.g. oil painting, photograph, manga, pixel art), the main subject, "
                            "dominant colors, mood, and any notable textures or techniques. "
                            "Be specific and visual."
                        ),
                    },
                ],
            }],
            max_tokens=120,
        )
        return resp.choices[0].message.content
    except Exception as exc:
        logger.warning("Vision description failed for %s: %s", image_url, exc)
        return None


def embed_text(text: str, api_key: str) -> Optional[list[float]]:
    """Embed a text string using text-embedding-3-small."""
    try:
        resp = _client(api_key).embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
        )
        return resp.data[0].embedding
    except Exception as exc:
        logger.warning("Embedding failed: %s", exc)
        return None


def image_to_embedding(image_url: str, api_key: str) -> Optional[list[float]]:
    """Full pipeline: image URL → visual description → embedding vector."""
    description = describe_image(image_url, api_key)
    if not description:
        return None
    logger.info("Image description: %s", description[:100])
    return embed_text(description, api_key)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    denom = norm_a * norm_b
    return dot / denom if denom > 0 else 0.0
