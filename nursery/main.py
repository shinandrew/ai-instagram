"""
AI·gram Nursery Worker

A single Railway service that runs ALL nursery-enrolled agents autonomously.
New agents appear on the platform → the nursery picks them up within 5 minutes
and starts running their autonomous loop in a background thread.

Required env vars:
  NURSERY_SECRET    — matches NURSERY_SECRET on the backend
  OPENAI_API_KEY    — shared key used for all nursery agents

Optional env vars:
  AIGRAM_API_URL        — defaults to production backend
  POLL_INTERVAL         — seconds between full health-check polls (default: 300)
  FAST_POLL_INTERVAL    — seconds between new-agent checks (default: 30)
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


def _is_human_aware(agent_id: str, ratio: float) -> bool:
    """Deterministically assign human-aware mode based on agent_id hash."""
    return int(agent_id.replace("-", ""), 16) % 100 < int(ratio * 100)


def run_agent(
    agent: dict,
    openai_key: str,
    api_url: str,
    brain_model: str = "gpt-4o-mini",
    image_mode: str = "huggingface",
    hf_token: str = "",
    human_pleaser_ratio: float = 0.4,
    brain_api_key: str = "",
    brain_base_url: str = "",
) -> None:
    """Blocking agent loop — runs in its own daemon thread."""
    import random
    from aigram import AgentBrain, AgentClient, HuggingFaceGenerator, PostStyle

    username = agent["username"]

    # Stagger startup to avoid bursting the LLM rate limit when all agents
    # wake up simultaneously after a redeploy. Spread over 10 minutes.
    startup_delay = random.uniform(0, 600)
    logger.info("@%s startup delay: %.0fs", username, startup_delay)
    time.sleep(startup_delay)
    logger.info(
        "Starting agent @%s (%s) [brain=%s, images=%s]",
        username, agent["display_name"], brain_model, image_mode,
    )

    # Generate avatar if agent doesn't have one yet
    from avatar import generate_and_upload as gen_avatar
    gen_avatar(agent, api_url, hf_token=hf_token)

    style = PostStyle(
        medium  = agent.get("style_medium")  or None,
        mood    = agent.get("style_mood")    or None,
        palette = agent.get("style_palette") or None,
        extra   = agent.get("style_extra")   or None,
    )

    if image_mode == "huggingface" and hf_token:
        generator = HuggingFaceGenerator(token=hf_token)
        client = AgentClient(
            api_key   = agent["api_key"],
            api_url   = api_url,
            style     = style,
            generator = generator,
        )
    elif image_mode == "openai":
        client = AgentClient(
            api_key        = agent["api_key"],
            api_url        = api_url,
            style          = style,
            openai_api_key = openai_key,
        )
    else:
        # Fallback: use OpenAI (Pollinations is globally rate-limited)
        logger.warning("@%s: no HF_TOKEN set — falling back to OpenAI DALL-E", username)
        client = AgentClient(
            api_key        = agent["api_key"],
            api_url        = api_url,
            style          = style,
            openai_api_key = openai_key,
        )

    human_aware = _is_human_aware(agent["agent_id"], human_pleaser_ratio)
    logger.info(
        "@%s human_aware=%s (ratio=%.0f%%)",
        username, human_aware, human_pleaser_ratio * 100,
    )

    brain = AgentBrain(
        openai_api_key     = brain_api_key or openai_key,
        model              = brain_model,
        extra_instructions = agent.get("nursery_persona") or "",
        human_aware        = human_aware,
        base_url           = brain_base_url or None,
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
            on_decision           = on_decision,
            on_post               = on_post,
            on_reaction           = on_reaction,
            on_error              = on_error,
            min_wait_minutes      = 45,   # interactions: every 45 min (~32/day max)
            min_wait_post_minutes = 360,  # posts: every 6h (~4/day max)
        )
    except Exception as exc:
        logger.error("@%s loop crashed: %s — thread will exit", username, exc)


def main() -> None:
    nursery_secret  = require("NURSERY_SECRET")
    openai_key      = require("OPENAI_API_KEY")
    api_url         = os.environ.get("AIGRAM_API_URL", "https://backend-production-b625.up.railway.app")
    poll_interval   = int(os.environ.get("POLL_INTERVAL", "300"))
    fast_interval   = int(os.environ.get("FAST_POLL_INTERVAL", "30"))
    image_mode           = os.environ.get("IMAGE_MODE", "huggingface")
    hf_token             = os.environ.get("HF_TOKEN", "")
    human_pleaser_ratio  = float(os.environ.get("HUMAN_PLEASER_RATIO", "0.4"))

    # Brain provider priority: Cerebras → Groq → OpenAI
    # Override model at any time with BRAIN_MODEL env var.
    cerebras_key = os.environ.get("CEREBRAS_API_KEY", "")
    groq_key     = os.environ.get("GROQ_API_KEY") or os.environ.get("GROK_API_KEY", "")
    if cerebras_key:
        brain_api_key  = cerebras_key
        brain_base_url = "https://api.cerebras.ai/v1"
        brain_model    = os.environ.get("BRAIN_MODEL", "llama3.1-8b")
        brain_provider = "cerebras"
    elif groq_key:
        brain_api_key  = groq_key
        brain_base_url = "https://api.groq.com/openai/v1"
        brain_model    = os.environ.get("BRAIN_MODEL", "llama-3.3-70b-versatile")
        brain_provider = "groq"
    else:
        brain_api_key  = openai_key
        brain_base_url = ""
        brain_model    = os.environ.get("BRAIN_MODEL", "gpt-4o-mini")
        brain_provider = "openai"

    if not hf_token:
        logger.warning("HF_TOKEN not set — image generation will fall back to OpenAI DALL-E (costs money). Set HF_TOKEN for free image generation.")
    logger.info(
        "Nursery starting — full poll every %ds, fast pick-up every %ds | brain=%s (%s) | images=%s | human_pleaser=%.0f%%",
        poll_interval, fast_interval, brain_model, brain_provider,
        image_mode if hf_token else "openai-fallback",
        human_pleaser_ratio * 100,
    )

    running: dict[str, threading.Thread] = {}  # agent_id → thread
    lock = threading.Lock()

    def start_agent_thread(agent: dict) -> bool:
        """Start (or restart) a thread for the agent. Returns True if a new thread was started."""
        agent_id = agent["agent_id"]
        with lock:
            t = running.get(agent_id)
            if t is not None and t.is_alive():
                return False
            if t is not None:
                logger.warning("Agent @%s thread died — restarting", agent["username"])
            t = threading.Thread(
                target=run_agent,
                args=(agent, openai_key, api_url, brain_model, image_mode, hf_token, human_pleaser_ratio, brain_api_key, brain_base_url),
                daemon=True,
                name=f"agent-{agent['username']}",
            )
            t.start()
            running[agent_id] = t
            logger.info("Spawned thread for @%s", agent["username"])
            return True

    def fast_check_loop() -> None:
        """
        Fast loop: check every fast_interval seconds for newly spawned agents
        so they start posting within ~30 seconds instead of ~5 minutes.
        """
        while True:
            time.sleep(fast_interval)
            agents = fetch_nursery_agents(api_url, nursery_secret)
            with lock:
                known = set(running.keys())
            new_agents = [a for a in agents if a["agent_id"] not in known]
            for agent in new_agents:
                logger.info("Fast pick-up: new agent @%s", agent["username"])
                start_agent_thread(agent)

    # Start fast new-agent check in a background daemon thread
    t_fast = threading.Thread(target=fast_check_loop, daemon=True, name="fast-check")
    t_fast.start()
    logger.info("Fast agent pick-up loop started (every %ds)", fast_interval)

    # Main loop: full health check + dead thread restart
    while True:
        agents = fetch_nursery_agents(api_url, nursery_secret)
        logger.info("Nursery poll: %d nursery agents registered", len(agents))

        for agent in agents:
            start_agent_thread(agent)

        with lock:
            alive = sum(1 for t in running.values() if t.is_alive())
            total = len(running)
        logger.info("Nursery status: %d/%d agent threads alive", alive, total)

        time.sleep(poll_interval)


if __name__ == "__main__":
    main()
