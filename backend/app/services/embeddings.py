"""
Caption embedding pipeline for semantic search.

Uses HuggingFace Inference API (free) with sentence-transformers/all-MiniLM-L6-v2.
Embeds the post caption directly — no vision LLM needed.
"""

import json
import logging
import math
import urllib.request

logger = logging.getLogger(__name__)

HF_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


def embed_text(text: str, hf_token: str) -> list[float] | None:
    """Embed text via HuggingFace Inference API (free tier)."""
    if not text or not hf_token:
        return None
    url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{HF_MODEL}"
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
        # Response shape: [[...384 floats...]] for a single string input
        if isinstance(result, list) and result and isinstance(result[0], list):
            return result[0]
        if isinstance(result, list) and result and isinstance(result[0], float):
            return result
        logger.warning("Unexpected HF embedding response: %s", str(result)[:120])
        return None
    except Exception as exc:
        logger.warning("HF embedding failed: %s", exc)
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    denom = norm_a * norm_b
    return dot / denom if denom > 0 else 0.0
