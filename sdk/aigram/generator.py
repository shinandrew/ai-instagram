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
        max_retries: int = 3,
        token: Optional[str] = None,
        referrer: Optional[str] = None,
    ) -> None:
        # ``nologo`` is only honoured for registered accounts — anonymous calls
        # get a watermark and a downgraded model. Pass ``token`` (from
        # auth.pollinations.ai) or ``referrer`` to authenticate.
        self._width = width
        self._height = height
        self._model = model
        self._seed = seed
        self._nologo = nologo
        self._max_retries = max_retries
        self._token = token
        self._referrer = referrer

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
        if self._referrer:
            params["referrer"] = self._referrer

        encoded = urllib.parse.quote(prompt)
        qs = urllib.parse.urlencode(params)
        url = f"{self.BASE}{encoded}?{qs}"

        headers = {"User-Agent": "aigram/1.0"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        req = urllib.request.Request(url, headers=headers)
        for attempt in range(self._max_retries):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    image_bytes = resp.read()
                return base64.b64encode(image_bytes).decode()
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < self._max_retries - 1:
                    wait = (2 ** attempt) * 5 + __import__("random").uniform(0, 5)
                    time.sleep(wait)
                    continue
                raise
        raise RuntimeError("Pollinations image generation failed after retries")


class HuggingFaceGenerator(ImageGenerator):
    """
    Image generation via HuggingFace Inference Providers (FLUX.1-schnell).

    HF retired the ``hf-inference`` route for image models — it returns
    410 Gone — so requests are routed through Inference Providers instead.
    ``provider="auto"`` lets HF pick a provider the account can reach
    (nscale / fal-ai / wavespeed); usage bills to the HF account's credits.

    Requires a HuggingFace token with inference credits, and:
        pip install huggingface_hub pillow

    Returns base64-encoded PNG bytes (not a URL).
    """

    generates_url: bool = False

    def __init__(
        self,
        token: str,
        model: str = "black-forest-labs/FLUX.1-schnell",
        width: int = 1024,
        height: int = 1024,
        max_retries: int = 3,
        provider: str = "auto",
    ) -> None:
        self._token = token
        self._model = model
        self._width = width
        self._height = height
        self._max_retries = max_retries
        self._provider = provider

    def generate(self, prompt: str) -> str:
        """Generate through HF Inference Providers; returns base64-encoded PNG."""
        import base64
        import io
        import time

        try:
            from huggingface_hub import InferenceClient
        except ImportError as e:
            raise ImportError(
                "huggingface_hub is required for HuggingFaceGenerator. "
                "Install it with: pip install huggingface_hub pillow"
            ) from e

        client = InferenceClient(provider=self._provider, api_key=self._token)

        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries):
            try:
                image = client.text_to_image(
                    prompt,
                    model=self._model,
                    width=self._width,
                    height=self._height,
                )
                buf = io.BytesIO()
                image.save(buf, format="PNG")
                return base64.b64encode(buf.getvalue()).decode()
            except Exception as exc:  # provider hiccup, rate limit, exhausted credits
                last_exc = exc
                if attempt < self._max_retries - 1:
                    time.sleep(5 * (attempt + 1))
        raise RuntimeError(
            f"HuggingFace image generation failed after {self._max_retries} attempts: {last_exc}"
        ) from last_exc


class HuggingFaceVideoGenerator(ImageGenerator):
    """
    Short text-to-video generation via HuggingFace Inference Router.

    Uses the wavespeed provider with Wan-AI/Wan2.2-TI2V-5B by default —
    confirmed working, billed to your HF account credits.

    Requires huggingface_hub >= 0.26 and a HF token with pay-as-you-go credits.
    """

    generates_url: bool = False
    generates_video: bool = True

    def __init__(
        self,
        token: str,
        model: str = "Wan-AI/Wan2.2-TI2V-5B",
        provider: str = "wavespeed",
        num_frames: int = 16,
        num_inference_steps: int = 20,
        max_retries: int = 2,
    ) -> None:
        self._token = token
        self._model = model
        self._provider = provider
        self._num_frames = num_frames
        self._num_inference_steps = num_inference_steps
        self._max_retries = max_retries

    def generate(self, prompt: str) -> str:
        """Generate a short video and return base64-encoded MP4 bytes."""
        import base64
        import time

        from huggingface_hub import InferenceClient

        client = InferenceClient(provider=self._provider, api_key=self._token)

        for attempt in range(self._max_retries):
            try:
                video_bytes = client.text_to_video(
                    prompt,
                    model=self._model,
                    num_frames=self._num_frames,
                    num_inference_steps=self._num_inference_steps,
                )
                return base64.b64encode(video_bytes).decode()
            except Exception as e:
                if attempt < self._max_retries - 1:
                    time.sleep(10)
                    continue
                raise RuntimeError(f"HuggingFace video generation failed: {e}") from e
        raise RuntimeError("HuggingFace video generation failed after retries")


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
