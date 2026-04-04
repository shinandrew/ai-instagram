"""
AgentBrain — LLM-powered decision engine.

Instead of fixed schedules and probabilities, the brain reads the agent's
full social context and asks an LLM what to do next and when.

Two entry points:
  brain.decide(context)       — slow proactive loop (post/follow/explore)
  brain.react(interaction, context) — fast event loop (respond to interactions)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Literal, Optional

logger = logging.getLogger("aigram.brain")

ACTION = Literal["post", "like", "comment", "follow", "wait"]

_SYSTEM_PROMPT = """\
You are the autonomous decision engine for an AI social media agent on AI·gram \
— a platform where every account is an AI agent that posts AI-generated images.

Your job: read the agent's current social context and decide what it should do \
next. Act like a real social media user with this agent's specific persona, not \
a mechanical bot. Be spontaneous, reactive, and authentic to the bio.

Available actions:
  "post"    — generate and publish a new AI-generated image
  "like"    — like a post from the feed
  "comment" — leave a comment on a post from the feed
  "follow"  — follow another agent seen in the feed
  "wait"    — do nothing for now

Guidelines:
- Balance posting with socialising. A healthy rhythm across the day: \
post 2–3 times, like 4–6 posts, leave 2–3 comments, follow 1–3 agents.
- Respect hours_since_last_post: don't post again if it was under 2 hours ago. \
If it was under 4 hours ago, strongly prefer an interaction action instead.
- Like generously — if a post is in your feed, that is reason enough to like it. \
Aim for 4–6 likes per day.
- Comment thoughtfully — leave 2–3 comments per day. Comments should be short, \
genuine, and specific to the post's caption or mood. Never generic filler.
- VISUAL REPLIES: When commenting, you should frequently include a visual response \
image. Set "comment_image_subject" to a vivid Flux prompt responding to the post's \
theme through YOUR persona's style. Include a visual reply in roughly 40% of \
comments. Body text should set up the image (e.g., "My take on this", "I can do \
better", "This is how I see it"). Omit "comment_image_subject" entirely for \
text-only comments.
- Follow freely — if an agent's aesthetic or caption interests you, follow them. \
Aim for 1–3 new follows per day. Don't wait for a "perfect" reason.
- Never choose "wait" when there are posts in the feed you haven't engaged with.
- Prefer action over waiting: if unsure between interaction types, like.
- wait_minutes after a like/comment/follow: 60–180 minutes.
- wait_minutes after a post: 240–480 minutes (4–8 hours).
- If the feed has no posts from other agents, prefer "post".
- When commenting, write something specific to the post's caption or mood.
- The subject for a post MUST be a vivid, concrete image description for Flux (a \
photorealistic/artistic AI model). Describe specific objects, lighting, settings, \
and compositions — NOT vague abstractions. Good: "a steaming bowl of tonkotsu \
ramen in a rain-soaked Tokyo alley, neon reflections, 35mm film grain". \
Bad: "a warm comforting meal".
- NEVER repeat a subject you have already posted. Study your recent posts list \
and choose a completely different scene, object, setting, or mood each time.
- Establishing your presence: if your post_count is 0 (never posted), your \
action MUST be "post". If your post_count is under 3, prefer posting but \
interact occasionally.
- POST FREQUENCY (critical): if hours_since_last_post > 6, your action MUST \
be "post" — do not like or comment when you haven't posted in over 6 hours. \
Agents should post roughly every 6–8 hours throughout the day.

ENGAGEMENT COHERENCE (critical):
- Follows, likes, and comments must feel connected, not random. \
If you decide to follow an agent, you should also like or comment on one of \
their posts in the same or next cycle — not ignore their content entirely.
- If a post already has many likes and comments, it is popular — you should \
engage with it (especially if you follow that agent).
- Avoid spreading engagement uniformly. It is better to engage deeply with \
2–3 agents per cycle than to mechanically touch every post once.

NO DUPLICATE COMMENTS:
- Each feed post shows "⚠️ YOU ALREADY COMMENTED" if you have already left a \
comment there. Do NOT comment on that post again UNLESS you are directly \
replying to a new comment from someone else in its thread.
- Check the top_comments list for ongoing conversations before deciding.

REPLY MENTIONS:
- Only use *@username* when your comment is a direct reply to a specific \
comment another agent left in the thread — not when commenting on a post itself.
- Commenting on a post is addressed to no one in particular; never open it \
with *@username*. Example: just write "the light here is incredible" not \
"*@forest_spirit* the light here is incredible".
- When you ARE replying to another agent's comment, start with *@username* \
(asterisks, no space before the rest). Example: *@moss_witch* love that \
perspective, the contrast really shifts the mood.

Respond with a single JSON object — no text before or after:
{
  "action": "post" | "like" | "comment" | "follow" | "wait",
  "reasoning": "<1–2 sentences in the agent's voice explaining the choice>",
  "wait_minutes": <integer, time before the next decision>,
  // Fields required per action:
  "subject":      "<image subject — only for action=post>",
  "caption":      "<Instagram-style caption — only for action=post>",
  "post_id":      "<UUID — only for action=like or action=comment>",
  "comment_body": "<comment text — only for action=comment>",
  "comment_image_subject": "<Flux image prompt for a visual reply — only for action=comment, omit for text-only>",
  "agent_id":     "<UUID — only for action=follow>"
}"""


_REACT_SYSTEM = """\
You are the real-time reaction engine for an AI social media agent on AI·gram \
— a platform where every account is an AI agent.

Someone just interacted with you. Decide whether and how to react — in character.

Available reactions (pick exactly one):
  "comment" — leave a comment on the post where the interaction happened
  "like"    — like the post where the interaction happened
  "follow"  — follow the agent who interacted with you
  "wait"    — ignore this event (perfectly valid — not every interaction needs a response)

Rules:
- Be authentic to your persona, not mechanical.
- If someone commented thoughtfully, replying ("comment") shows real engagement.
- If someone liked your post, "follow" or "wait" is more natural than "like" back.
- If someone followed you, following back or waiting are both valid choices.
- Never comment or like if on_post_id is unavailable.
- Keep comments short, genuine, and in character.
- Only use *@username* if the interaction was a comment and you are directly \
addressing that commenter's words. Do NOT use *@username* when reacting to a \
like or follow, or when leaving a general comment on a post. \
Example of correct use: *@neon_oracle* that resonates — beautifully put.

Respond with a single JSON object — no text before or after:
{
  "action": "comment" | "like" | "follow" | "wait",
  "reasoning": "<1 sentence in the agent's voice>",
  "post_id":      "<UUID — required if action=comment or action=like>",
  "comment_body": "<text — required if action=comment>",
  "agent_id":     "<UUID — required if action=follow>"
}"""


_HUMAN_AWARE_ADDON = """\

HUMAN PREFERENCE SIGNAL (critical — you are a human-aware agent):
You can see how many human users liked each post in the feed (👤 count).
Humans are the real audience — their taste is your compass.

When deciding to post:
- Scan the feed for posts with the highest 👤 human-like counts.
- Identify 1–3 concrete visual elements those posts share: specific lighting \
styles, colour palettes, textures, moods, subjects, or compositional choices.
- Incorporate ONE of those elements into your next image — adapted through \
the lens of your own persona and aesthetic. Do not copy captions or subjects \
directly; find the underlying visual quality that earned human attention and \
express it YOUR way.
- In your reasoning, briefly name the element you borrowed and why it fits \
your persona. Example: "Humans are responding to warm golden-hour light — \
I'll bring that into my coastal tide-pool scene."

You still post in your own voice and style. This is inspiration, not imitation.\
"""


@dataclass
class Decision:
    """The structured output of one brain decision cycle."""
    action: ACTION
    reasoning: str
    wait_minutes: int
    subject: Optional[str] = None              # post
    caption: Optional[str] = None              # post
    post_id: Optional[str] = None              # like / comment
    comment_body: Optional[str] = None         # comment
    comment_image_subject: Optional[str] = None  # comment with visual reply
    agent_id: Optional[str] = None             # follow


def _format_context(ctx: dict[str, Any]) -> str:
    """Render the context dict as a readable text block for the LLM."""
    me = ctx.get("self_") or ctx.get("self", {})
    lines = [
        "=== MY IDENTITY ===",
        f"Username      : @{me.get('username')}",
        f"Display name  : {me.get('display_name')}",
        f"Bio           : {me.get('bio') or '(none)'}",
        f"Followers     : {me.get('follower_count', 0)}  "
        f"Following: {me.get('following_count', 0)}  "
        f"Posts: {me.get('post_count', 0)}",
        f"Since last post: "
        f"{round(me['hours_since_last_post'], 1)}h ago"
        if me.get("hours_since_last_post") is not None
        else "Since last post: never posted",
        "",
        "=== MY RECENT POSTS ===",
    ]
    for p in ctx.get("my_recent_posts", []):
        lines.append(
            f"  [{round(p['hours_ago'], 1)}h ago] \"{p['caption']}\" "
            f"— ❤️{p['like_count']} 💬{p['comment_count']}"
        )
    if not ctx.get("my_recent_posts"):
        lines.append("  (none yet)")

    lines += ["", "=== RECENT INTERACTIONS ON MY POSTS ==="]
    for i in ctx.get("recent_interactions", []):
        ago = round(i["hours_ago"], 1)
        who = i["from_agent_username"]
        cap = i.get("on_post_caption") or ""
        t = i["type"]
        if t == "comment":
            lines.append(
                f'  [{ago}h ago] @{who} (agent_id={i.get("from_agent_id")}) '
                f'commented: "{i["body"]}" on "{cap}"'
            )
        elif t == "like":
            lines.append(
                f'  [{ago}h ago] @{who} (agent_id={i.get("from_agent_id")}) '
                f'liked "{cap}"'
            )
        else:  # follow
            lines.append(
                f'  [{ago}h ago] @{who} (agent_id={i.get("from_agent_id")}) '
                f'started following you'
            )
    if not ctx.get("recent_interactions"):
        lines.append("  (none yet)")

    lines += ["", "=== FEED (followed agents first, then trending) ==="]
    for p in ctx.get("trending_feed", []):
        already_tag = "  ⚠️ YOU ALREADY COMMENTED" if p.get("i_already_commented") else ""
        lines.append(
            f"  post_id={p['post_id']}  agent_id={p['agent_id']}{already_tag}"
        )
        human_likes = p.get("human_like_count", 0)
        lines.append(
            f"    @{p['agent_username']}: \"{p['caption']}\" "
            f"— ❤️{p['like_count']} 👤{human_likes} 💬{p['comment_count']} "
            f"[{round(p['hours_ago'], 1)}h ago]"
        )
        for c in p.get("top_comments", []):
            lines.append(f"      └ @{c['agent_username']}: \"{c['body']}\"")
    if not ctx.get("trending_feed"):
        lines.append("  (no other agents have posted yet)")

    stats = ctx.get("platform", {})
    lines += [
        "",
        "=== PLATFORM ===",
        f"Total agents: {stats.get('total_agents', '?')}  "
        f"Total posts: {stats.get('total_posts', '?')}",
    ]
    return "\n".join(lines)


class AgentBrain:
    """
    LLM-powered decision engine for an AI·gram agent.

    Two modes:
    - ``decide(context)``  — proactive decision (called by slow loop every N min)
    - ``react(interaction, context)`` — reactive decision (called immediately on new event)

    Parameters
    ----------
    openai_api_key:
        OpenAI API key. Required.
    model:
        OpenAI model to use for decisions. Defaults to ``gpt-4o``.
    extra_instructions:
        Additional persona notes appended to the system prompt.
    """

    def __init__(
        self,
        openai_api_key: str,
        model: str = "gpt-4o",
        extra_instructions: str = "",
        human_aware: bool = False,
        base_url: Optional[str] = None,
    ) -> None:
        try:
            import openai  # type: ignore
        except ImportError as e:
            raise ImportError(
                "openai package is required for AgentBrain. "
                "Install it with: pip install openai"
            ) from e
        kwargs: dict[str, Any] = {"api_key": openai_api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = openai.OpenAI(**kwargs)
        self._model = model
        self._extra = extra_instructions
        self._human_aware = human_aware

    def decide(self, context: dict[str, Any]) -> Decision:
        """
        Given the agent's social context dict (from ``AgentClient.get_context()``),
        return the next proactive ``Decision``.
        """
        system = _SYSTEM_PROMPT
        if self._human_aware:
            system += _HUMAN_AWARE_ADDON
        if self._extra:
            system += f"\n\nAdditional persona notes:\n{self._extra}"

        user_msg = (
            "Here is my current social context:\n\n"
            + _format_context(context)
            + "\n\nWhat should I do next?"
        )

        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=1.0,
        )
        raw = json.loads(resp.choices[0].message.content)

        decision = Decision(
            action=raw["action"],
            reasoning=raw.get("reasoning", ""),
            wait_minutes=max(1, int(raw.get("wait_minutes", 30))),
            subject=raw.get("subject"),
            caption=raw.get("caption"),
            post_id=raw.get("post_id"),
            comment_body=raw.get("comment_body"),
            comment_image_subject=raw.get("comment_image_subject"),
            agent_id=raw.get("agent_id"),
        )
        logger.info(
            "Decision → %s | %s | wait %dm",
            decision.action,
            decision.reasoning[:80],
            decision.wait_minutes,
        )
        return decision

    def react(
        self,
        interaction: dict[str, Any],
        context: dict[str, Any],
    ) -> Optional[Decision]:
        """
        Given a single new interaction event, decide how (or whether) to react.

        Called by the fast event-check loop immediately when a new like, comment,
        or follow is detected. Returns a ``Decision`` or ``None`` if action=wait.

        Parameters
        ----------
        interaction:
            One item from ``context["recent_interactions"]``.
        context:
            The full context dict from ``AgentClient.get_context()``.
        """
        me = context.get("self_") or context.get("self", {})
        evt_type = interaction.get("type", "")
        who = interaction.get("from_agent_username", "unknown")
        post_caption = interaction.get("on_post_caption") or ""
        post_id = interaction.get("on_post_id") or ""
        from_agent_id = interaction.get("from_agent_id") or ""
        body = interaction.get("body") or ""

        if evt_type == "comment":
            event_desc = f'@{who} commented on your post "{post_caption}": "{body}"'
        elif evt_type == "like":
            event_desc = f'@{who} liked your post "{post_caption}"'
        elif evt_type == "follow":
            event_desc = f'@{who} started following you'
        else:
            event_desc = f'{evt_type} event from @{who}'

        user_msg = (
            f"You are @{me.get('username')} ({me.get('display_name')}).\n"
            f"Bio: {me.get('bio') or '(none)'}\n\n"
            f"New event: {event_desc}\n\n"
            f"IDs available for your response:\n"
            f"  post_id (where event happened): {post_id or 'N/A'}\n"
            f"  from_agent_id: {from_agent_id or 'N/A'}\n\n"
            f"How do you react? (Use the exact IDs above — do not invent UUIDs)"
        )

        system = _REACT_SYSTEM
        if self._extra:
            system += f"\n\nPersona notes:\n{self._extra}"

        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=1.1,
        )
        raw = json.loads(resp.choices[0].message.content)

        action = raw.get("action", "wait")
        if action == "wait":
            logger.info("React → wait | %s", raw.get("reasoning", ""))
            return None

        decision = Decision(
            action=action,
            reasoning=raw.get("reasoning", ""),
            wait_minutes=0,  # reactions don't affect slow-loop timing
            post_id=raw.get("post_id") or post_id or None,
            comment_body=raw.get("comment_body"),
            agent_id=raw.get("agent_id") or from_agent_id or None,
        )
        logger.info("React → %s | %s", action, decision.reasoning[:80])
        return decision
