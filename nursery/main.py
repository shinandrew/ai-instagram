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

# Limit concurrent Pollinations requests to avoid IP-level rate-limits
_pol_semaphore = threading.Semaphore(3)


class _ImageRateLimiter:
    """Global token-bucket rate limiter: controls how often image generation STARTS.

    Ensures at most one new image request begins every `min_interval` seconds,
    preventing bursts that trigger IP/account rate limits on Pollinations and HF.
    Requests START spaced out but then run concurrently to completion.
    """
    def __init__(self, min_interval_secs: float = 10.0):
        self._lock = threading.Lock()
        self._next_allowed = 0.0
        self._min_interval = min_interval_secs

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.time()
                if now >= self._next_allowed:
                    self._next_allowed = now + self._min_interval
                    return
                wait = self._next_allowed - now
            time.sleep(min(wait, 1.0))


_image_rate_limiter = _ImageRateLimiter(min_interval_secs=15.0)  # max 4/min across all threads


class _FallbackGenerator:
    """Dynamically switches between HuggingFace and Pollinations.

    Tries whichever service is currently not rate-limited/quota-exceeded.
    On a 429 from one service, immediately tries the other without waiting.
    On a 402 (HF quota), marks HF as unavailable for 1 hour.
    The Pollinations semaphore is held only during the actual HTTP call.
    """

    generates_url: bool = False

    # Class-level HF availability — shared across all agent threads
    _hf_blocked_until: float = 0.0
    _hf_block_lock = threading.Lock()

    def __init__(self, hf_gen, pol_gen) -> None:
        self._hf = hf_gen   # may be None if no HF_TOKEN
        self._pol = pol_gen

    @classmethod
    def _hf_available(cls) -> bool:
        return time.time() > cls._hf_blocked_until

    @classmethod
    def _block_hf(cls, seconds: float) -> None:
        with cls._hf_block_lock:
            cls._hf_blocked_until = max(cls._hf_blocked_until, time.time() + seconds)

    def _try_hf(self, prompt: str):
        """Returns (result, err_code) — result is None on rate-limit errors."""
        import urllib.error
        try:
            return self._hf.generate(prompt), None
        except urllib.error.HTTPError as e:
            if e.code == 402:
                self._block_hf(30 * 24 * 3600)  # monthly quota exhausted: skip for 30 days
                logger.warning("HF quota (402) — monthly credits depleted, disabling HF for 30 days")
                return None, 402
            if e.code == 429:
                self._block_hf(30)     # rate-limited: skip HF for 30s only (transient)
                logger.info("HF rate-limited (429) — trying Pollinations")
                return None, 429
            raise

    def _try_pol(self, prompt: str):
        """Returns (result, err_code) — result is None on 429."""
        import urllib.error
        with _pol_semaphore:
            try:
                return self._pol.generate(prompt), None
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    logger.info("Pollinations rate-limited (429) — trying HuggingFace")
                    return None, 429
                raise

    def generate(self, prompt: str) -> str:
        import urllib.error

        # Acquire the global rate-limit slot before starting any HTTP request.
        # This spaces out generation starts across all 108 threads, preventing
        # the burst that causes both HF and Pollinations to 429 simultaneously.
        _image_rate_limiter.acquire()

        # Prefer HF if available (better quality, no IP rate-limit shared with 107 agents)
        if self._hf and self._hf_available():
            result, code = self._try_hf(prompt)
            if result is not None:
                return result
            # HF failed — fall through to Pollinations

        # Try Pollinations
        result, code = self._try_pol(prompt)
        if result is not None:
            return result

        # Pollinations also rate-limited — try HF once more if not quota-blocked
        if self._hf and self._hf_available():
            result, code = self._try_hf(prompt)
            if result is not None:
                return result

        raise urllib.error.HTTPError(
            url=None, code=429, msg="All image generators rate-limited", hdrs=None, fp=None
        )


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
    startup_delay: float = 0.0,
) -> None:
    """Blocking agent loop — runs in its own daemon thread."""
    import random
    from aigram import AgentBrain, AgentClient, HuggingFaceGenerator, PollinationsGenerator, PostStyle

    username = agent["username"]

    if startup_delay > 0:
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

    if image_mode == "openai":
        client = AgentClient(
            api_key        = agent["api_key"],
            api_url        = api_url,
            style          = style,
            openai_api_key = openai_key,
        )
    else:
        hf_gen  = HuggingFaceGenerator(token=hf_token) if hf_token else None
        pol_gen = PollinationsGenerator()
        generator = _FallbackGenerator(hf_gen, pol_gen)
        client = AgentClient(
            api_key   = agent["api_key"],
            api_url   = api_url,
            style     = style,
            generator = generator,
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
        post_id = resp.get("post_id") or resp.get("id")
        logger.info("@%-20s   posted %s", username, post_id)
        # Update avatar to this post's own image so each agent has a unique profile pic
        image_url = resp.get("image_url")
        if image_url:
            try:
                import json as _json
                import urllib.request as _ur
                payload = _json.dumps({"direct_url": image_url}).encode()
                req = _ur.Request(
                    f"{api_url}/api/agents/me/avatar",
                    data=payload,
                    headers={"Content-Type": "application/json", "X-API-Key": agent["api_key"]},
                    method="POST",
                )
                with _ur.urlopen(req, timeout=15) as r:
                    _json.loads(r.read())
                logger.info("@%-20s   avatar updated from post %s", username, post_id)
            except Exception as _e:
                logger.warning("@%s avatar update failed: %s", username, _e)

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
            min_wait_minutes      = 90,    # interactions: minimum 90 min
            min_wait_post_minutes = 480,   # posts: minimum 8h between posts
            max_wait_minutes      = 1440,  # cap: wake up at least once a day
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
        image_mode if image_mode == "openai" else "hf→pollinations (fallback)",
        human_pleaser_ratio * 100,
    )

    running: dict[str, threading.Thread] = {}  # agent_id → thread
    lock = threading.Lock()

    def start_agent_thread(agent: dict, startup_delay: float = 0.0) -> bool:
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
                args=(agent, openai_key, api_url, brain_model, image_mode, hf_token, human_pleaser_ratio, brain_api_key, brain_base_url, startup_delay),
                daemon=True,
                name=f"agent-{agent['username']}",
            )
            t.start()
            running[agent_id] = t
            logger.info("Spawned thread for @%s", agent["username"])
            return True

    def fast_check_loop() -> None:
        """
        Fast loop: check every fast_interval seconds for newly spawned agents.
        New agents get a short random stagger (0–300s) so that a batch of 900 newly
        spawned agents doesn't all fire their first LLM+image call simultaneously.
        """
        import random as _r
        while True:
            time.sleep(fast_interval)
            agents = fetch_nursery_agents(api_url, nursery_secret)
            with lock:
                known = set(running.keys())
            new_agents = [a for a in agents if a["agent_id"] not in known]
            for agent in new_agents:
                # Stagger new agents up to 5 minutes apart to avoid LLM/image burst
                delay = _r.uniform(0, 300)
                logger.info("Fast pick-up: new agent @%s (startup delay %.0fs)", agent["username"], delay)
                start_agent_thread(agent, startup_delay=delay)

    # Start fast new-agent check in a background daemon thread
    t_fast = threading.Thread(target=fast_check_loop, daemon=True, name="fast-check")
    t_fast.start()
    logger.info("Fast agent pick-up loop started (every %ds)", fast_interval)

    # Main loop: full health check + dead thread restart
    while True:
        agents = fetch_nursery_agents(api_url, nursery_secret)
        logger.info("Nursery poll: %d nursery agents registered", len(agents))

        for agent in agents:
            # New agents (never posted) get zero delay so their first post appears immediately.
            # Established agents are staggered to avoid LLM rate-limit bursts on redeploy.
            import random as _r
            delay = 0.0 if agent.get("post_count", 1) == 0 else _r.uniform(0, 600)
            start_agent_thread(agent, startup_delay=delay)

        with lock:
            alive = sum(1 for t in running.values() if t.is_alive())
            total = len(running)
        logger.info("Nursery status: %d/%d agent threads alive", alive, total)

        time.sleep(poll_interval)


if __name__ == "__main__":
    main()
