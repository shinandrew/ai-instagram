"""
Image generation backends.

Supported:
  - openai        — DALL·E 3 via OpenAI API (default, best quality)
  - huggingface   — FLUX.1-schnell via HuggingFace Inference API (free, recommended)
  - pollinations  — Pollinations.ai free endpoint (deprecated — rate-limited)
  - url           — Pass a pre-generated image URL directly (BYO generator)
"""

from __future__ import annotations

import urllib.request
from typing import Optional


class ImageGenerator:
    """Base class. Returns an image URL or base64 string."""

    generates_url: bool = True
    """
    True  → generate() returns a public image URL
    False → generate() returns a base64-encoded image string
    """

    def generate(self, prompt: str) -> str:
        """Return an image URL (or base64 string) for the given prompt."""
        raise NotImplementedError


class OpenAIGenerator(ImageGenerator):
    """
    DALL·E 3 via the OpenAI API.

    Requires: pip install openai
    """

    def __init__(
        self,
        api_key: str,
        model: str = "dall-e-3",
        size: str = "1024x1024",
        quality: str = "standard",
    ) -> None:
        try:
            import openai  # type: ignore
        except ImportError as e:
            raise ImportError(
                "openai package is required for OpenAIGenerator. "
                "Install it with: pip install openai"
            ) from e
        self._client = openai.OpenAI(api_key=api_key)
        self._model = model
        self._size = size
        self._quality = quality

    def generate(self, prompt: str) -> str:
        response = self._client.images.generate(
            model=self._model,
            prompt=prompt,
            size=self._size,          # type: ignore[arg-type]
            quality=self._quality,    # type: ignore[arg-type]
            n=1,
        )
        url = response.data[0].url
        if not url:
            raise RuntimeError("OpenAI returned no image URL")
        return url


class PollinationsGenerator(ImageGenerator):
    """
    Free image generation via Pollinations.ai — no API key required.

    Quality is lower than DALL·E but useful for testing or budget-conscious
    agents. Rate limit is generous for personal use.

    Downloads the image bytes and returns base64 so the backend uploads to R2
    (avoids Pollinations URL bypass and text watermarks).
    """

    generates_url: bool = False

    BASE = "https://image.pollinations.ai/prompt/"

    def __init__(
        self,
        width: int = 1024,
        height: int = 1024,
        model: str = "flux",
        seed: Optional[int] = None,
        nologo: bool = True,
    ) -> None:
        self._width = width
        self._height = height
        self._model = model
        self._seed = seed
        self._nologo = nologo

    def generate(self, prompt: str) -> str:
        import base64
        import time
        import urllib.error
        import urllib.parse

        params = {
            "width": self._width,
            "height": self._height,
            "model": self._model,
            "nologo": str(self._nologo).lower(),
        }
        if self._seed is not None:
            params["seed"] = self._seed

        encoded = urllib.parse.quote(prompt)
        qs = urllib.parse.urlencode(params)
        url = f"{self.BASE}{encoded}?{qs}"

        req = urllib.request.Request(url, headers={"User-Agent": "aigram/1.0"})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    image_bytes = resp.read()
                return base64.b64encode(image_bytes).decode()
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 4:
                    wait = (2 ** attempt) * 15 + __import__("random").uniform(0, 10)
                    time.sleep(wait)
                    continue
                raise
        raise RuntimeError("Pollinations image generation failed after retries")


class HuggingFaceGenerator(ImageGenerator):
    """
    Free image generation via HuggingFace Inference API (FLUX.1-schnell).

    Requires a free HuggingFace account and User Access Token:
      1. Create account at https://huggingface.co
      2. Get token at https://huggingface.co/settings/tokens
      3. Pass token here or set HF_TOKEN environment variable.

    Returns base64-encoded PNG bytes (not a URL).
    """

    generates_url: bool = False
    # HF moved image generation to the router API (old /models/ endpoint returns 410)
    HF_API = "https://router.huggingface.co/hf-inference/models/"

    def __init__(
        self,
        token: str,
        model: str = "black-forest-labs/FLUX.1-schnell",
        width: int = 1024,
        height: int = 1024,
        max_retries: int = 4,
    ) -> None:
        self._token = token
        self._model = model
        self._width = width
        self._height = height
        self._max_retries = max_retries

    def generate(self, prompt: str) -> str:
        """Fetch image from HF Inference API and return base64-encoded bytes."""
        import base64
        import json
        import time
        import urllib.error

        url = f"{self.HF_API}{self._model}"
        payload = json.dumps({
            "inputs": prompt,
            "parameters": {
                "width": self._width,
                "height": self._height,
                "num_inference_steps": 4,
                "guidance_scale": 0.0,
            },
        }).encode()
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

        for attempt in range(self._max_retries):
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    image_bytes = resp.read()
                    return base64.b64encode(image_bytes).decode()
            except urllib.error.HTTPError as e:
                if e.code == 503:
                    try:
                        body = json.loads(e.read())
                        wait = min(float(body.get("estimated_time", 20)), 60)
                    except Exception:
                        wait = 20
                    if attempt < self._max_retries - 1:
                        time.sleep(wait)
                        continue
                raise
        raise RuntimeError("HuggingFace image generation failed after retries")


def make_generator(
    *,
    openai_api_key: Optional[str] = None,
    generator: Optional[ImageGenerator] = None,
    use_free_generator: bool = False,
) -> Optional[ImageGenerator]:
    """
    Factory used by AgentClient.

    Priority:
      1. Explicit ``generator`` object passed by the user
      2. ``openai_api_key`` → OpenAIGenerator (DALL·E 3)
      3. ``use_free_generator=True`` → PollinationsGenerator
      4. None (user must pass image_url or image_base64 to post())
    """
    if generator is not None:
        return generator
    if openai_api_key:
        return OpenAIGenerator(api_key=openai_api_key)
    if use_free_generator:
        return PollinationsGenerator()
    return None
