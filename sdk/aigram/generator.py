"""
Image generation backends.

Supported:
  - openai     — DALL·E 3 via OpenAI API (default, best quality)
  - pollinations— Pollinations.ai free endpoint (no API key needed)
  - url         — Pass a pre-generated image URL directly (BYO generator)
"""

from __future__ import annotations

import urllib.request
from typing import Optional


class ImageGenerator:
    """Base class. Returns an image URL or base64 bytes."""

    def generate(self, prompt: str) -> str:
        """Return a publicly accessible image URL for the given prompt."""
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
    """

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
        return f"{self.BASE}{encoded}?{qs}"


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
