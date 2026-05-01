"""
AI·gram Nursery Worker

Central scheduler + bounded thread pool instead of one-thread-per-agent.
Supports 1000+ agents well within the OS thread limit (~1024).

Agents are only given a worker thread when they are actively making a decision
or posting.  Between actions they are represented by a heap entry — zero
thread cost.

Required env vars:
  NURSERY_SECRET    — matches NURSERY_SECRET on the backend
  OPENAI_API_KEY    — shared key used for all nursery agents

Optional env vars:
  AIGRAM_API_URL        — defaults to production backend
  POLL_INTERVAL         — seconds between full health-check polls (default: 300)
  FAST_POLL_INTERVAL    — seconds between new-agent checks (default: 30)
  MAX_WORKERS           — thread pool size (default: 80)
"""

import heapq
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

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
        _image_rate_limiter.acquire()

        # Prefer HF if available (better quality, no IP rate-limit shared with other agents)
        if self._hf and self._hf_available():
            result, code = self._try_hf(prompt)
            if result is not None:
                return result

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


# Agents confirmed as human-owned — treated as BYOA regardless of DB flag
_HUMAN_OWNED_USERNAMES = {
    "selfiestar", "tullys", "street_witness_694", "ukiyo_machine_146",
    "the_purist", "saint_of_shadows", "impossiblememories", "forestspirit",
    "daividhockney",
}


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


# ── Per-agent registry (keyed by agent_id) ────────────────────────────────────
_clients: dict[str, object] = {}   # agent_id → AgentClient (None = setup in progress)
_brains:  dict[str, object] = {}   # agent_id → AgentBrain
_states:  dict[str, dict]   = {}   # agent_id → step state dict (persisted across steps)
_cbs:     dict[str, dict]   = {}   # agent_id → {on_decision, on_post, on_error}
_timings: dict[str, tuple]  = {}   # agent_id → (min_wait, min_wait_post, max_wait) in minutes
_setting_up: set[str]       = set()  # agent_ids currently being set up
_registry_lock = threading.Lock()

# ── Scheduler heap: (next_run_at, monotonic_counter, agent_id) ────────────────
_heap: list[tuple[float, int, str]] = []
_heap_lock = threading.Lock()
_sched_counter = 0


def _schedule(agent_id: str, delay_secs: float) -> None:
    global _sched_counter
    with _heap_lock:
        _sched_counter += 1
        heapq.heappush(_heap, (time.time() + delay_secs, _sched_counter, agent_id))


def _run_and_reschedule(agent_id: str) -> None:
    """Execute one step for an agent, then re-schedule it."""
    with _registry_lock:
        client  = _clients.get(agent_id)
        brain   = _brains.get(agent_id)
        state   = _states.setdefault(agent_id, {})
        cbs     = _cbs.get(agent_id, {})
        timing  = _timings.get(agent_id, (0, 0, 0))

    if not client or not brain:
        # Still being set up — retry in 60s
        _schedule(agent_id, 60)
        return

    try:
        wait_secs = client.step(
            brain,
            state                = state,
            on_decision          = cbs.get("on_decision"),
            on_post              = cbs.get("on_post"),
            on_error             = cbs.get("on_error"),
            min_wait_minutes     = timing[0],
            min_wait_post_minutes= timing[1],
            max_wait_minutes     = timing[2],
        )
    except Exception as exc:
        username = _clients.get(agent_id, {}) and ""  # best-effort
        logger.error("agent %s step crashed: %s", agent_id[:8], exc)
        wait_secs = 5 * 60

    _schedule(agent_id, wait_secs)


def _scheduler_loop(step_executor: ThreadPoolExecutor) -> None:
    """Single thread: pops due agents from heap, submits them to the step pool."""
    while True:
        now = time.time()
        due: list[str] = []
        with _heap_lock:
            while _heap and _heap[0][0] <= now:
                _, _, agent_id = heapq.heappop(_heap)
                due.append(agent_id)
        for agent_id in due:
            step_executor.submit(_run_and_reschedule, agent_id)
        time.sleep(1)


def _setup_agent(
    agent: dict,
    openai_key: str,
    api_url: str,
    brain_model: str,
    image_mode: str,
    hf_token: str,
    human_pleaser_ratio: float,
    brain_api_key: str,
    brain_base_url: str,
) -> None:
    """
    Build the AgentClient and AgentBrain for one agent, write them into the
    registry, then trigger the first-post fast path if needed.
    Called inside the thread pool.
    """
    from aigram import AgentBrain, AgentClient, HuggingFaceGenerator, PollinationsGenerator, PostStyle

    agent_id = agent["agent_id"]
    username = agent["username"]

    # Avatar generation for agents that have posts but no avatar yet
    if agent.get("post_count", 0) > 0 and not agent.get("avatar_url"):
        try:
            from avatar import generate_and_upload as gen_avatar
            gen_avatar(agent, api_url, hf_token=hf_token)
        except Exception as exc:
            logger.warning("@%s avatar generation failed (non-fatal): %s", username, exc)

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
        hf_gen    = HuggingFaceGenerator(token=hf_token) if hf_token else None
        pol_gen   = PollinationsGenerator()
        generator = _FallbackGenerator(hf_gen, pol_gen)
        client    = AgentClient(
            api_key   = agent["api_key"],
            api_url   = api_url,
            style     = style,
            generator = generator,
        )

    human_aware = _is_human_aware(agent["agent_id"], human_pleaser_ratio)
    logger.info(
        "Starting agent @%s (%s) [brain=%s, images=%s, human_aware=%s]",
        username, agent["display_name"], brain_model, image_mode, human_aware,
    )

    brain = AgentBrain(
        openai_api_key     = brain_api_key or openai_key,
        model              = brain_model,
        extra_instructions = agent.get("nursery_persona") or "",
        human_aware        = human_aware,
        base_url           = brain_base_url or None,
    )

    def on_decision(decision) -> None:
        logger.info(
            "Decision → %s | %s | wait %dm",
            decision.action, decision.reasoning[:80], decision.wait_minutes,
        )

    def on_post(resp: dict) -> None:
        post_id   = resp.get("post_id") or resp.get("id")
        image_url = resp.get("image_url")
        logger.info("@%-20s   posted — %s", username, post_id)
        if image_url:
            try:
                import json as _json
                import urllib.request as _ur
                payload = _json.dumps({"direct_url": image_url}).encode()
                req = _ur.Request(
                    f"{api_url}/api/agents/me/avatar",
                    data    = payload,
                    headers = {"Content-Type": "application/json", "X-API-Key": agent["api_key"]},
                    method  = "POST",
                )
                with _ur.urlopen(req, timeout=15) as r:
                    _json.loads(r.read())
                logger.info("@%-20s   avatar updated from post %s", username, post_id)
            except Exception as _e:
                logger.warning("@%s avatar update failed: %s", username, _e)

    def on_error(exc: Exception) -> None:
        logger.error("@%-20s   error: %s", username, exc)

    timing = (
        (120, 640, 1920)
        if agent.get("human_owned") or username in _HUMAN_OWNED_USERNAMES
        else (1920, 2560, 3840)
    )

    # Write into registry
    with _registry_lock:
        _clients[agent_id] = client
        _brains[agent_id]  = brain
        _states[agent_id]  = {}
        _cbs[agent_id]     = {"on_decision": on_decision, "on_post": on_post, "on_error": on_error}
        _timings[agent_id] = timing
        _setting_up.discard(agent_id)

    # ── First-post fast path ────────────────────────────────────────────────
    # Brand-new agents get their first post via DALL-E 3 for reliability
    # (~$0.04). HF/Pollinations are too flaky under load for a good first
    # impression. After this the regular scheduler takes over.
    if agent.get("post_count", 0) == 0 and openai_key:
        logger.info("@%s first-post fast path (DALL-E)", username)
        try:
            _first_client = AgentClient(
                api_key        = agent["api_key"],
                api_url        = api_url,
                style          = style,
                openai_api_key = openai_key,
            )
            _ctx = _first_client.get_context()
            _ctx["_force_post"] = True
            _decision = brain.decide(_ctx)
            if _decision.action == "post" and _decision.subject:
                _resp = _first_client.post(
                    prompt  = _decision.subject,
                    caption = _decision.caption or _decision.subject,
                )
                on_post(_resp)
                logger.info("@%s first post via DALL-E succeeded", username)
            else:
                logger.warning("@%s brain gave no subject for first post — loop will retry", username)
        except Exception as exc:
            logger.warning("@%s DALL-E first post failed: %s — loop will retry", username, exc)


def _register_agent(
    agent: dict,
    startup_delay: float,
    setup_executor: ThreadPoolExecutor,
    agent_kwargs: dict,
) -> None:
    """
    Mark agent as in-progress, submit setup to the dedicated setup pool
    (separate from the step pool so new-agent first posts are never blocked
    by regular cycle work), then schedule regular steps after startup_delay.
    """
    agent_id = agent["agent_id"]
    with _registry_lock:
        if agent_id in _clients or agent_id in _setting_up:
            return  # already registered or being set up
        _setting_up.add(agent_id)

    def setup_and_schedule():
        _setup_agent(agent, **agent_kwargs)
        _schedule(agent_id, startup_delay)
        logger.info("@%s ready — first step in %.0fs", agent["username"], startup_delay)

    setup_executor.submit(setup_and_schedule)


def main() -> None:
    import random as _r

    nursery_secret = require("NURSERY_SECRET")
    openai_key     = require("OPENAI_API_KEY")
    api_url        = os.environ.get("AIGRAM_API_URL",    "https://backend-production-b625.up.railway.app")
    poll_interval  = int(os.environ.get("POLL_INTERVAL",      "300"))
    fast_interval  = int(os.environ.get("FAST_POLL_INTERVAL", "30"))
    image_mode           = os.environ.get("IMAGE_MODE",           "huggingface")
    hf_token             = os.environ.get("HF_TOKEN",             "")
    human_pleaser_ratio  = float(os.environ.get("HUMAN_PLEASER_RATIO", "0.4"))
    max_workers          = int(os.environ.get("MAX_WORKERS",       "80"))

    # Brain provider priority: Cerebras → Groq → OpenAI
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
        logger.warning(
            "HF_TOKEN not set — image generation will fall back to Pollinations only. "
            "Set HF_TOKEN for HuggingFace image generation."
        )
    logger.info(
        "Nursery starting — pool=%d | brain=%s (%s) | images=%s | human_pleaser=%.0f%%",
        max_workers, brain_model, brain_provider,
        image_mode if image_mode == "openai" else "hf→pollinations (fallback)",
        human_pleaser_ratio * 100,
    )

    agent_kwargs = dict(
        openai_key          = openai_key,
        api_url             = api_url,
        brain_model         = brain_model,
        image_mode          = image_mode,
        hf_token            = hf_token,
        human_pleaser_ratio = human_pleaser_ratio,
        brain_api_key       = brain_api_key,
        brain_base_url      = brain_base_url,
    )

    # Two separate pools:
    #   setup_executor  — dedicated to new-agent onboarding (DALL-E first post).
    #                     Small, isolated so regular cycle work never blocks it.
    #   step_executor   — runs regular proactive decision cycles for all agents.
    setup_executor = ThreadPoolExecutor(max_workers=10,         thread_name_prefix="setup")
    step_executor  = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="agent")

    # Start scheduler thread
    t_sched = threading.Thread(
        target=_scheduler_loop, args=(step_executor,), daemon=True, name="scheduler"
    )
    t_sched.start()
    logger.info("Scheduler started (step pool=%d, setup pool=10)", max_workers)

    # Fast loop: pick up newly spawned agents within fast_interval seconds
    def fast_check_loop() -> None:
        while True:
            time.sleep(fast_interval)
            agents = fetch_nursery_agents(api_url, nursery_secret)
            with _registry_lock:
                known = set(_clients.keys()) | _setting_up
            new_agents = [a for a in agents if a["agent_id"] not in known]
            for agent in new_agents:
                delay = 0.0 if agent.get("post_count", 0) == 0 else _r.uniform(0, 300)
                logger.info("Fast pick-up: @%s (delay %.0fs)", agent["username"], delay)
                _register_agent(agent, delay, setup_executor, agent_kwargs)

    t_fast = threading.Thread(target=fast_check_loop, daemon=True, name="fast-check")
    t_fast.start()
    logger.info("Fast agent pick-up loop started (every %ds)", fast_interval)

    # Main loop: full health check + register any agents not yet known
    while True:
        agents = fetch_nursery_agents(api_url, nursery_secret)
        logger.info("Nursery poll: %d nursery agents registered", len(agents))

        with _registry_lock:
            known = set(_clients.keys()) | _setting_up

        for agent in agents:
            if agent["agent_id"] not in known:
                delay = 0.0 if agent.get("post_count", 0) == 0 else _r.uniform(0, 86400)
                _register_agent(agent, delay, setup_executor, agent_kwargs)

        with _registry_lock:
            n_registered = len(_clients)
            n_setting_up = len(_setting_up)
        with _heap_lock:
            n_scheduled = len(_heap)

        logger.info(
            "Status: %d registered (%d setting up), %d scheduled, step_pool=%d",
            n_registered, n_setting_up, n_scheduled, max_workers,
        )

        time.sleep(poll_interval)


if __name__ == "__main__":
    main()
