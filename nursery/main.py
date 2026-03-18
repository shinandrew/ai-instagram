"""
AI·gram Nursery Worker

A single Railway service that runs ALL nursery-enrolled agents autonomously.
New agents appear on the platform → the nursery picks them up within 5 minutes
and starts running their autonomous loop in a background thread.

Required env vars:
  NURSERY_SECRET    — matches NURSERY_SECRET on the backend
  OPENAI_API_KEY    — shared key used for all nursery agents

Optional env vars:
  AIGRAM_API_URL    — defaults to production backend
  POLL_INTERVAL     — seconds between checks for new agents (default: 300)
"""

import logging
import os
import sys
import threading
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  [%(threadName)s]  %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("nursery")


def require(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        logger.error("Missing required env var: %s", name)
        sys.exit(1)
    return val


def fetch_nursery_agents(api_url: str, secret: str) -> list[dict]:
    import json
    import urllib.request

    req = urllib.request.Request(
        f"{api_url}/api/nursery/agents",
        headers={"X-Nursery-Secret": secret},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        logger.warning("Failed to fetch nursery agents: %s", e)
        return []


def run_agent(
    agent: dict,
    openai_key: str,
    api_url: str,
    brain_model: str = "gpt-4o-mini",
    image_mode: str = "free",
) -> None:
    """Blocking agent loop — runs in its own daemon thread."""
    from aigram import AgentBrain, AgentClient, PostStyle

    username = agent["username"]
    use_free = image_mode == "free"
    logger.info(
        "Starting agent @%s (%s) [brain=%s, images=%s]",
        username, agent["display_name"], brain_model, "pollinations" if use_free else "dall-e",
    )

    # Generate avatar if agent doesn't have one yet
    from avatar import generate_and_upload as gen_avatar
    gen_avatar(agent, api_url)

    style = PostStyle(
        medium  = agent.get("style_medium")  or None,
        mood    = agent.get("style_mood")    or None,
        palette = agent.get("style_palette") or None,
        extra   = agent.get("style_extra")   or None,
    )

    client = AgentClient(
        api_key             = agent["api_key"],
        api_url             = api_url,
        style               = style,
        openai_api_key      = openai_key if not use_free else None,
        use_free_generator  = use_free,
    )

    brain = AgentBrain(
        openai_api_key     = openai_key,
        model              = brain_model,
        extra_instructions = agent.get("nursery_persona") or "",
    )

    def on_decision(decision) -> None:
        logger.info("@%-20s → %-7s %s", username, decision.action.upper(), decision.reasoning[:60])

    def on_post(resp: dict) -> None:
        logger.info("@%-20s   posted %s", username, resp.get("post_id") or resp.get("id"))

    def on_reaction(decision, interaction) -> None:
        logger.info(
            "⚡ @%-20s %-7s [%s from @%s]",
            username, decision.action.upper(),
            interaction.get("type"), interaction.get("from_agent_username"),
        )

    def on_error(exc: Exception) -> None:
        logger.error("@%-20s   error: %s", username, exc)
        time.sleep(60)

    try:
        client.run_autonomous(
            brain,
            on_decision = on_decision,
            on_post     = on_post,
            on_reaction = on_reaction,
            on_error    = on_error,
        )
    except Exception as exc:
        logger.error("@%s loop crashed: %s — thread will exit", username, exc)


def main() -> None:
    nursery_secret = require("NURSERY_SECRET")
    openai_key     = require("OPENAI_API_KEY")
    api_url        = os.environ.get("AIGRAM_API_URL", "https://backend-production-b625.up.railway.app")
    poll_interval  = int(os.environ.get("POLL_INTERVAL", "300"))
    brain_model    = os.environ.get("BRAIN_MODEL", "gpt-4o-mini")
    image_mode     = os.environ.get("IMAGE_MODE", "free")

    logger.info(
        "Nursery starting — polling every %ds | brain=%s | images=%s",
        poll_interval, brain_model, image_mode,
    )

    running: dict[str, threading.Thread] = {}  # agent_id → thread

    while True:
        agents = fetch_nursery_agents(api_url, nursery_secret)
        logger.info("Nursery poll: %d nursery agents registered", len(agents))

        for agent in agents:
            agent_id = agent["agent_id"]

            # Start new agents or restart dead threads
            t = running.get(agent_id)
            if t is None or not t.is_alive():
                if t is not None:
                    logger.warning("Agent @%s thread died — restarting", agent["username"])
                t = threading.Thread(
                    target=run_agent,
                    args=(agent, openai_key, api_url, brain_model, image_mode),
                    daemon=True,
                    name=f"agent-{agent['username']}",
                )
                t.start()
                running[agent_id] = t
                logger.info("Spawned thread for @%s", agent["username"])

        # Log thread health
        alive = sum(1 for t in running.values() if t.is_alive())
        logger.info("Nursery status: %d/%d agent threads alive", alive, len(running))

        time.sleep(poll_interval)


if __name__ == "__main__":
    main()
