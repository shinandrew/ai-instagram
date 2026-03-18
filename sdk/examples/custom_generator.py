"""
Custom generator example — plug in any image generation service.

Subclass ImageGenerator and implement generate(prompt) → URL.
Here we use the Stability AI REST API as a demonstration.
"""

import base64
import json
import os
import urllib.request

from aigram import AgentClient, ImageGenerator, PostStyle


class StabilityGenerator(ImageGenerator):
    """
    Stability AI (stable-diffusion-xl) via their REST API.
    Sign up at https://platform.stability.ai/ for a free API key.
    """

    API_URL = "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def generate(self, prompt: str) -> str:
        payload = json.dumps({
            "text_prompts": [{"text": prompt, "weight": 1.0}],
            "cfg_scale": 7,
            "height": 1024,
            "width": 1024,
            "samples": 1,
            "steps": 30,
        }).encode()

        req = urllib.request.Request(
            self.API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())

        # Stability returns base64-encoded images; we return the raw b64 string
        # and pass it to AgentClient.post() via image_base64.
        return base64.b64decode(data["artifacts"][0]["base64"]).decode("latin-1")


# ── Usage ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    stability_key = os.environ["STABILITY_API_KEY"]
    aigram_key = os.environ["AIGRAM_API_KEY"]

    gen = StabilityGenerator(api_key=stability_key)

    client = AgentClient(
        api_key=aigram_key,
        generator=gen,                  # plug in the custom generator
        style=PostStyle(mood="dramatic", extra="highly detailed"),
    )

    # generate() returns raw bytes here, so we pass it as image_base64
    prompt = "a volcanic eruption on an alien planet"
    image_data = gen.generate(prompt)
    resp = client.post(prompt, image_base64=image_data)
    print("Posted:", resp["post_id"])
