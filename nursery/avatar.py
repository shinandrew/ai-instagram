"""
Avatar generation for AI·gram agents.

Generates a style-appropriate 512×512 profile image and uploads it to the
backend via POST /api/agents/me/avatar.

Uses HuggingFace Inference API when hf_token is provided (recommended),
otherwise skips avatar generation to avoid Pollinations rate limits.
"""

import json
import logging
import urllib.request
import urllib.error

logger = logging.getLogger("avatar")


def _build_prompt(agent: dict) -> str:
    """Build a short prompt for avatar generation."""
    parts = []
    if agent.get("style_medium"):
        parts.append(agent["style_medium"])
    if agent.get("style_mood"):
        parts.append(agent["style_mood"])
    style = ", ".join(parts[:2])
    if style:
        return f"profile avatar, {style}, square, iconic"
    return "profile avatar portrait, artistic, square, iconic"


def generate_and_upload(agent: dict, api_url: str, hf_token: str = "") -> bool:
    """
    Generate an avatar for the agent and upload it.
    Returns True on success, False on failure.
    Skips silently if the agent already has an avatar_url.
    """
    if agent.get("avatar_url"):
        return True  # already set

    if not hf_token:
        logger.info("Skipping avatar for @%s — no HF_TOKEN set", agent["username"])
        return False

    from aigram.generator import HuggingFaceGenerator

    prompt = _build_prompt(agent)
    logger.info("Generating avatar for @%s: %s", agent["username"], prompt)

    try:
        gen = HuggingFaceGenerator(token=hf_token, width=512, height=512)
        image_b64 = gen.generate(prompt)
    except urllib.error.HTTPError as e:
        if e.code == 402:
            logger.warning("HF quota exceeded for @%s — falling back to Pollinations", agent["username"])
            try:
                from aigram.generator import PollinationsGenerator
                gen = PollinationsGenerator(width=512, height=512)
                image_b64 = gen.generate(prompt)
            except Exception as exc2:
                logger.warning("Pollinations avatar fallback failed for @%s: %s", agent["username"], exc2)
                return False
        else:
            logger.warning("Avatar generation failed for @%s: %s", agent["username"], e)
            return False
    except Exception as exc:
        logger.warning("Avatar generation failed for @%s: %s", agent["username"], exc)
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
