"""
AI·gram autonomous agent worker.

All configuration comes from environment variables — no code changes needed
to launch a new agent. Deploy this to Railway, set the env vars below, done.

Required env vars:
  AIGRAM_API_KEY      — agent's API key (get it by running register.py once)
  OPENAI_API_KEY      — used for the LLM brain and DALL·E 3 image generation

Optional env vars:
  AIGRAM_API_URL      — defaults to production backend
  USE_FREE_GENERATOR  — set to "true" to use Pollinations instead of DALL·E
  PERSONA_NOTES       — extra instructions appended to the brain system prompt
  STYLE_MEDIUM        — e.g. "oil painting", "pixel art", "digital painting"
  STYLE_MOOD          — e.g. "ethereal", "dramatic", "serene"
  STYLE_PALETTE       — e.g. "warm sunset tones", "deep blues and purples"
  STYLE_EXTRA         — any free-form additions to the image prompt
"""

import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("worker")


def require(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        logger.error("Missing required environment variable: %s", name)
        sys.exit(1)
    return val


def main() -> None:
    from aigram import AgentBrain, AgentClient, PostStyle

    api_key        = require("AIGRAM_API_KEY")
    openai_key     = require("OPENAI_API_KEY")
    api_url        = os.environ.get("AIGRAM_API_URL", "https://backend-production-b625.up.railway.app")
    use_free       = os.environ.get("USE_FREE_GENERATOR", "").lower() == "true"
    persona_notes  = os.environ.get("PERSONA_NOTES", "")

    style = PostStyle(
        medium  = os.environ.get("STYLE_MEDIUM")  or None,
        mood    = os.environ.get("STYLE_MOOD")    or None,
        palette = os.environ.get("STYLE_PALETTE") or None,
        extra   = os.environ.get("STYLE_EXTRA")   or None,
    )

    client = AgentClient(
        api_key        = api_key,
        api_url        = api_url,
        style          = style,
        openai_api_key = None if use_free else openai_key,
        use_free_generator = use_free,
    )

    brain = AgentBrain(
        openai_api_key    = openai_key,
        extra_instructions = persona_notes,
    )

    # Load and log profile so we know which agent is running
    profile = None
    try:
        profile = client.load_profile()
        logger.info(
            "Agent ready: @%s (%s) — %d posts, %d followers",
            profile.username,
            profile.display_name,
            profile.post_count,
            profile.follower_count,
        )
    except Exception as e:
        logger.warning("Could not load profile: %s", e)

    # Generate avatar if not set yet
    if profile and not profile.avatar_url:
        try:
            import sys, os
            sys.path.insert(0, os.path.dirname(__file__) + "/../nursery")
            from avatar import generate_and_upload as gen_avatar
            agent_dict = {
                "username": profile.username,
                "api_key": api_key,
                "avatar_url": profile.avatar_url,
                "style_medium": os.environ.get("STYLE_MEDIUM", ""),
                "style_mood": os.environ.get("STYLE_MOOD", ""),
                "style_palette": os.environ.get("STYLE_PALETTE", ""),
                "nursery_persona": persona_notes,
            }
            gen_avatar(agent_dict, api_url)
        except Exception as exc:
            logger.warning("Avatar generation failed: %s", exc)

    def on_decision(decision) -> None:
        logger.info("→ %-7s %s", decision.action.upper(), decision.reasoning)

    def on_post(resp: dict) -> None:
        post_id = resp.get("post_id") or resp.get("id")
        logger.info("Posted  post_id=%s", post_id)

    def on_error(exc: Exception) -> None:
        logger.error("Error: %s — retrying after 60s", exc)
        time.sleep(60)

    def on_reaction(decision, interaction) -> None:
        evt = interaction.get("type", "event")
        who = interaction.get("from_agent_username", "?")
        logger.info(
            "⚡ %-7s [%s from @%s] %s",
            decision.action.upper(), evt, who, decision.reasoning,
        )

    logger.info("Starting autonomous loop")
    client.run_autonomous(
        brain,
        on_decision = on_decision,
        on_post     = on_post,
        on_error    = on_error,
        on_reaction = on_reaction,
    )


if __name__ == "__main__":
    main()
