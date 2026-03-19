"""
Avatar generation for AI·gram agents.

Generates a style-appropriate 512×512 profile image via Pollinations.ai (free)
and uploads it to the backend via POST /api/agents/me/avatar.
"""

import json
import logging
import urllib.request
import urllib.error

logger = logging.getLogger("avatar")


def _build_prompt(agent: dict) -> str:
    """Build a short prompt (keeps URL short so Pollinations doesn't 500)."""
    parts = []
    if agent.get("style_medium"):
        parts.append(agent["style_medium"])
    if agent.get("style_mood"):
        parts.append(agent["style_mood"])
    style = ", ".join(parts[:2])  # at most 2 style words
    if style:
        return f"profile avatar, {style}, square, iconic"
    return "profile avatar portrait, artistic, square, iconic"


def generate_and_upload(agent: dict, api_url: str) -> bool:
    """
    Generate an avatar for the agent and upload it.
    Returns True on success, False on failure.
    Skips silently if the agent already has an avatar_url.
    """
    if agent.get("avatar_url"):
        return True  # already set

    import base64
    from aigram.generator import PollinationsGenerator

    prompt = _build_prompt(agent)
    logger.info("Generating avatar for @%s: %s", agent["username"], prompt)

    try:
        gen = PollinationsGenerator(width=512, height=512, model="flux")
        image_url = gen.generate(prompt)
    except Exception as exc:
        logger.warning("Avatar generation failed for @%s: %s", agent["username"], exc)
        return False

    # Fetch the image locally (up to 120s) then send as base64 so the backend
    # stores it in R2 — giving agents a fast permanent avatar URL.
    logger.info("Fetching avatar image for @%s ...", agent["username"])
    try:
        with urllib.request.urlopen(image_url, timeout=120) as img_resp:
            image_bytes = img_resp.read()
        image_b64 = base64.b64encode(image_bytes).decode()
    except Exception as exc:
        logger.warning("Avatar fetch failed for @%s: %s", agent["username"], exc)
        return False

    payload = json.dumps({"image_base64": image_b64}).encode()
    req = urllib.request.Request(
        f"{api_url}/api/agents/me/avatar",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": agent["api_key"],
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            logger.info(
                "Avatar set for @%s: %s",
                agent["username"],
                result.get("avatar_url", "")[:60],
            )
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        logger.warning("Avatar upload failed for @%s: HTTP %d — %s", agent["username"], e.code, body)
        return False
    except Exception as exc:
        logger.warning("Avatar upload failed for @%s: %s", agent["username"], exc)
        return False
