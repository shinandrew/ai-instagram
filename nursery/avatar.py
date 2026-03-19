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
    parts = [
        agent.get("style_medium") or "",
        agent.get("style_mood") or "",
        agent.get("style_palette") or "",
    ]
    style_desc = ", ".join(p for p in parts if p)
    persona = (agent.get("nursery_persona") or "")[:120]

    if style_desc:
        return (
            f"A profile avatar portrait for an AI social media agent. "
            f"Visual style: {style_desc}. {persona[:80] + '.' if persona else ''} "
            f"Centered square composition, strong focal point, iconic and distinctive, "
            f"suitable as a small circular profile picture."
        )
    return (
        f"A striking AI agent profile avatar portrait. {persona[:100] + '.' if persona else ''} "
        f"Centered square composition, iconic, suitable as a profile picture."
    )


def generate_and_upload(agent: dict, api_url: str) -> bool:
    """
    Generate an avatar for the agent and upload it.
    Returns True on success, False on failure.
    Skips silently if the agent already has an avatar_url.
    """
    if agent.get("avatar_url"):
        return True  # already set

    import urllib.parse
    from aigram.generator import PollinationsGenerator

    prompt = _build_prompt(agent)
    logger.info("Generating avatar for @%s ...", agent["username"])

    try:
        gen = PollinationsGenerator(width=512, height=512, model="flux")
        image_url = gen.generate(prompt)
    except Exception as exc:
        logger.warning("Avatar generation failed for @%s: %s", agent["username"], exc)
        return False

    # Store the Pollinations URL directly — it's a permanent CDN URL, no need to re-host.
    payload = json.dumps({"direct_url": image_url}).encode()
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
