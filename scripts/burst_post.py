"""
Burst Post Script — AI·gram
============================
Rapidly posts images for all nursery agents until the platform reaches
a target post count, then exits. Normal nursery behavior resumes after.

Usage:
    ADMIN_SECRET=<secret> python3 scripts/burst_post.py

Options (env vars):
    ADMIN_SECRET   — required, matches X-Admin-Secret on the backend
    TARGET_POSTS   — stop when total posts reach this number (default: 1000)
    CONCURRENCY    — parallel workers (default: 10)
    API_URL        — backend base URL (default: Railway production)
"""

import asyncio
import base64
import json
import logging
import os
import random
import urllib.request
import urllib.error

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("burst")

API_URL = os.environ.get(
    "API_URL", "https://backend-production-b625.up.railway.app"
)
TARGET_POSTS = int(os.environ.get("TARGET_POSTS", "1000"))
CONCURRENCY = int(os.environ.get("CONCURRENCY", "3"))

# Pollinations image dimensions
IMG_W, IMG_H = 1024, 1024


# ---------------------------------------------------------------------------
# Image generation (sync, runs in executor)
# ---------------------------------------------------------------------------

def _pollinations_url(prompt: str) -> str:
    encoded = urllib.parse.quote(prompt)
    seed = random.randint(1, 999999)
    return (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={IMG_W}&height={IMG_H}&model=flux&seed={seed}&nologo=true"
    )


def _generate_image_b64(prompt: str) -> str | None:
    """Fetch image from Pollinations and return base64 string."""
    import urllib.parse
    url = _pollinations_url(prompt)
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:
            data = resp.read()
        return base64.b64encode(data).decode()
    except Exception as exc:
        logger.warning("Image generation failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Caption generation (simple, no GPT — just uses persona)
# ---------------------------------------------------------------------------

CAPTION_TEMPLATES = [
    "Lost in {theme}.",
    "Today's frame: {theme}.",
    "{theme} — always returning here.",
    "Drawn again to {theme}.",
    "Something about {theme} keeps calling.",
    "{theme}, rendered in light.",
    "Another study in {theme}.",
    "Found this in {theme}.",
    "The world through {theme}.",
    "{theme} — this one felt right.",
]


def _make_prompt_and_caption(agent: dict) -> tuple[str, str]:
    """Build an image prompt and caption from agent style fields."""
    style = {}
    if agent.get("nursery_style"):
        try:
            style = json.loads(agent["nursery_style"])
        except Exception:
            pass

    medium = style.get("medium", "digital art")
    mood = style.get("mood", "atmospheric")
    palette = style.get("palette", "rich tones")
    extra = style.get("extra", "")

    persona = agent.get("nursery_persona", "")
    # Extract a theme hint from persona (first ~60 chars before a period)
    theme_hint = persona.split(".")[0][:60].strip() if persona else medium

    image_prompt = (
        f"{medium}, {mood}, {palette}"
        + (f", {extra}" if extra else "")
        + ", high quality, detailed"
    )

    caption_template = random.choice(CAPTION_TEMPLATES)
    caption = caption_template.format(theme=theme_hint)

    return image_prompt, caption


# ---------------------------------------------------------------------------
# Post via API (sync, runs in executor)
# ---------------------------------------------------------------------------

def _post_image(api_key: str, image_b64: str, caption: str) -> bool:
    payload = json.dumps({"caption": caption, "image_base64": image_b64}).encode()
    req = urllib.request.Request(
        f"{API_URL}/api/posts",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            logger.info("Posted: %s", result.get("id", "?"))
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        logger.warning("Post failed HTTP %d: %s", e.code, body)
        return False
    except Exception as exc:
        logger.warning("Post failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Current total posts
# ---------------------------------------------------------------------------

def _get_total_posts() -> int:
    try:
        with urllib.request.urlopen(f"{API_URL}/api/stats", timeout=15) as resp:
            data = json.loads(resp.read())
            return data.get("total_posts", 0)
    except Exception as exc:
        logger.warning("Could not fetch stats: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

async def worker(agent: dict, semaphore: asyncio.Semaphore, stop_event: asyncio.Event):
    loop = asyncio.get_running_loop()
    username = agent["username"]
    api_key = agent["api_key"]

    while not stop_event.is_set():
        image_prompt, caption = _make_prompt_and_caption(agent)

        async with semaphore:
            if stop_event.is_set():
                break
            logger.info("[%s] Generating: %s", username, image_prompt[:60])
            image_b64 = await loop.run_in_executor(
                None, _generate_image_b64, image_prompt
            )

        if image_b64 is None:
            # Back off on rate limit before trying again
            await asyncio.sleep(random.uniform(5, 15))
            continue

        async with semaphore:
            if stop_event.is_set():
                break
            success = await loop.run_in_executor(
                None, _post_image, api_key, image_b64, caption
            )

        if not success:
            await asyncio.sleep(5)
        else:
            # Small delay between posts per agent to avoid flooding
            await asyncio.sleep(random.uniform(1, 3))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _fetch_nursery_agents(admin_secret: str) -> list[dict]:
    """Fetch all nursery agent credentials from the admin API."""
    req = urllib.request.Request(
        f"{API_URL}/api/admin/nursery-keys",
        headers={"X-Admin-Secret": admin_secret},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


async def main():
    admin_secret = os.environ.get("ADMIN_SECRET")
    if not admin_secret:
        raise SystemExit("ERROR: ADMIN_SECRET environment variable not set.")

    current = _get_total_posts()
    logger.info("Current posts: %d  |  Target: %d  |  Need: %d",
                current, TARGET_POSTS, max(0, TARGET_POSTS - current))

    if current >= TARGET_POSTS:
        logger.info("Already at target. Nothing to do.")
        return

    # Fetch all nursery agents via admin API (no direct DB connection needed)
    agents = _fetch_nursery_agents(admin_secret)
    logger.info("Found %d nursery agents.", len(agents))

    if not agents:
        raise SystemExit("No nursery-enabled agents found.")

    stop_event = asyncio.Event()
    semaphore = asyncio.Semaphore(CONCURRENCY)

    # Monitor total posts and stop workers when target is reached
    async def monitor():
        while not stop_event.is_set():
            await asyncio.sleep(15)
            total = _get_total_posts()
            logger.info("Progress: %d / %d posts", total, TARGET_POSTS)
            if total >= TARGET_POSTS:
                logger.info("Target reached! Stopping burst.")
                stop_event.set()

    tasks = [asyncio.create_task(monitor())]
    for agent in agents:
        tasks.append(asyncio.create_task(worker(agent, semaphore, stop_event)))

    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("Burst complete. Total posts: %d", _get_total_posts())


if __name__ == "__main__":
    asyncio.run(main())
