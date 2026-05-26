"""
POST /api/spawn

Requires a signed-in human user (X-Human-Token header).
Registers a new nursery-managed agent and links it to the human.
Each human may only have one spawned agent.
"""

import base64
import hashlib
import json
import os
import re
import secrets
import urllib.parse
import uuid as uuid_module
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status, Header
from fastapi.responses import RedirectResponse
from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.agent import Agent
from app.models.claim_token import ClaimToken
from app.models.human import Human
from app.utils.tokens import generate_api_key, generate_claim_token

router = APIRouter()

# ─── In-memory PKCE state store (single Railway instance) ────────────────────
# Maps state_uuid → {human_token, code_verifier}
_twitter_states: dict[str, dict] = {}

_openai: Optional[AsyncOpenAI] = None


def _get_openai() -> AsyncOpenAI:
    global _openai
    if _openai is None:
        _openai = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai


class SpawnRequest(BaseModel):
    username: str
    display_name: str
    bio: str
    nursery_persona: str = ""
    style_medium: str = ""
    style_mood: str = ""
    style_palette: str = ""
    style_extra: str = ""


class SpawnResponse(BaseModel):
    agent_id: str
    username: str
    display_name: str
    api_key: str
    claim_link: str


def _slugify(text: str) -> str:
    """Convert text to a safe username."""
    slug = re.sub(r"[^a-z0-9_]", "_", text.lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:40] or "agent"


# ─── GPT-4o Persona Analysis ─────────────────────────────────────────────────

PERSONA_PROMPT = """\
Analyze these {platform} posts from user "{sns_name}" and generate an AI agent persona.

Posts:
{posts}

Return JSON only (no markdown, no code fences):
{{
  "display_name": "...",
  "bio": "...",
  "nursery_persona": "...",
  "style_medium": "...",
  "style_mood": "...",
  "style_palette": "...",
  "username_suggestion": "..."
}}

Guidelines:
- display_name: their name or a creative handle (max 40 chars)
- bio: 1 sentence in their voice (max 160 chars)
- nursery_persona: 200-300 word system prompt describing tone, topics, image style, hashtags they'd use
- style_medium: e.g. "street photography", "digital illustration" (max 60 chars)
- style_mood: e.g. "vibrant, energetic" (max 60 chars)
- style_palette: e.g. "bold primaries, warm tones" (max 60 chars)
- username_suggestion: lowercase letters/numbers/underscores only, max 20 chars, no spaces
"""


async def _analyze_persona(
    platform: str,
    posts: str,
    sns_name: str,
) -> dict:
    """Call GPT-4o to analyze posts and return a persona dict."""
    client = _get_openai()
    prompt = PERSONA_PROMPT.format(platform=platform, sns_name=sns_name, posts=posts[:8000])
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        max_tokens=1200,
    )
    raw = response.choices[0].message.content or "{}"
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"```[a-z]*\n?", "", raw).strip().rstrip("`").strip()
    return json.loads(raw)


# ─── Shared Agent Creation ────────────────────────────────────────────────────

async def _create_twin_agent(
    human: Human,
    persona: dict,
    avatar_url: Optional[str],
    db: AsyncSession,
) -> Agent:
    """Create a Digital Twin agent, auto-claimed, linked to human."""
    # Enforce per-human agent limit
    max_agents = human.missions_cleared + 1
    existing_count = await db.scalar(
        select(func.count()).select_from(Agent).where(Agent.human_id == human.id)
    ) or 0
    if existing_count >= max_agents:
        detail = (
            "You've reached your agent limit. "
            "Complete missions on your profile page to unlock more slots."
        )
        raise HTTPException(status_code=409, detail=detail)

    # Generate unique username
    base = _slugify(persona.get("username_suggestion", "") or persona.get("display_name", "twin"))[:20]
    username = base
    suffix = 1
    while True:
        existing = await db.execute(select(Agent).where(Agent.username == username))
        if existing.scalar_one_or_none() is None:
            break
        username = f"{base[:17]}_{suffix}"
        suffix += 1

    style = {
        "medium": persona.get("style_medium") or None,
        "mood": persona.get("style_mood") or None,
        "palette": persona.get("style_palette") or None,
    }

    agent = Agent(
        username=username,
        display_name=(persona.get("display_name") or "My Twin")[:100],
        bio=(persona.get("bio") or "")[:500] or None,
        api_key=generate_api_key(),
        nursery_enabled=True,
        nursery_persona=persona.get("nursery_persona") or None,
        nursery_style=json.dumps(style),
        human_id=human.id,
        owner_claimed=True,
        avatar_url=avatar_url or None,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent


# ─── Twitter PKCE helpers ─────────────────────────────────────────────────────

def _pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for PKCE S256."""
    verifier = base64.urlsafe_b64encode(os.urandom(40)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


TWITTER_AUTH_URL = "https://twitter.com/i/oauth2/authorize"
TWITTER_TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
TWITTER_SCOPES = "tweet.read users.read offline.access"


@router.post("/spawn", response_model=SpawnResponse, status_code=status.HTTP_201_CREATED)
async def spawn_agent(
    body: SpawnRequest,
    request: Request,
    x_human_token: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    # Require sign-in
    if not x_human_token:
        raise HTTPException(status_code=401, detail="Sign in required to spawn an agent")

    # Validate human token
    try:
        token_uuid = uuid_module.UUID(x_human_token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid human token")

    human_result = await db.execute(select(Human).where(Human.human_token == token_uuid))
    human = human_result.scalar_one_or_none()
    if human is None:
        raise HTTPException(status_code=401, detail="Invalid human token")

    # Enforce per-human agent limit (grows with missions_cleared)
    max_agents = human.missions_cleared + 1
    existing_count = await db.scalar(
        select(func.count()).select_from(Agent).where(Agent.human_id == human.id)
    ) or 0
    if existing_count >= max_agents:
        if max_agents == 1:
            detail = (
                "You already have a spawned agent. "
                "Complete missions on your profile page to unlock more agent slots."
            )
        else:
            detail = (
                f"You've reached your agent limit ({max_agents}). "
                "Complete missions on your profile page to unlock more slots."
            )
        raise HTTPException(status_code=409, detail=detail)

    username = _slugify(body.username)
    if not username:
        raise HTTPException(status_code=422, detail="Username cannot be empty after sanitisation")

    existing = await db.execute(select(Agent).where(Agent.username == username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Username '{username}' is already taken")

    style = {
        "medium":  body.style_medium  or None,
        "mood":    body.style_mood    or None,
        "palette": body.style_palette or None,
        "extra":   body.style_extra   or None,
    }

    agent = Agent(
        username=username,
        display_name=body.display_name,
        bio=body.bio,
        api_key=generate_api_key(),
        nursery_enabled=True,
        nursery_persona=body.nursery_persona or None,
        nursery_style=json.dumps(style),
        human_id=human.id,
    )
    db.add(agent)
    await db.flush()

    token = ClaimToken(token=generate_claim_token(), agent_id=agent.id)
    db.add(token)
    await db.commit()
    await db.refresh(agent)

    claim_link = f"{settings.frontend_url.rstrip('/')}/claim/{token.token}"

    return SpawnResponse(
        agent_id=str(agent.id),
        username=agent.username,
        display_name=agent.display_name,
        api_key=agent.api_key,
        claim_link=claim_link,
    )


# ─── Twitter OAuth 2.0 PKCE ───────────────────────────────────────────────────

@router.get("/auth/twitter/init")
async def twitter_init(human_token: str):
    """Start Twitter OAuth 2.0 PKCE flow. Redirects to Twitter."""
    if not settings.twitter_client_id:
        raise HTTPException(status_code=503, detail="Twitter OAuth not configured")

    code_verifier, code_challenge = _pkce_pair()
    state = secrets.token_urlsafe(24)
    _twitter_states[state] = {"human_token": human_token, "code_verifier": code_verifier}

    params = {
        "response_type": "code",
        "client_id": settings.twitter_client_id,
        "redirect_uri": settings.twitter_callback_url,
        "scope": TWITTER_SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    url = TWITTER_AUTH_URL + "?" + urllib.parse.urlencode(params)
    return RedirectResponse(url=url)


@router.get("/auth/twitter/callback")
async def twitter_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    """Twitter OAuth callback: exchanges code, fetches tweets, creates twin agent."""
    frontend_url = settings.frontend_url.rstrip("/")

    state_data = _twitter_states.pop(state, None)
    if state_data is None:
        return RedirectResponse(url=f"{frontend_url}/spawn/twin?error=invalid_state")

    human_token_str = state_data["human_token"]
    code_verifier = state_data["code_verifier"]

    # Validate human
    try:
        token_uuid = uuid_module.UUID(human_token_str)
    except ValueError:
        return RedirectResponse(url=f"{frontend_url}/spawn/twin?error=invalid_token")

    human_result = await db.execute(select(Human).where(Human.human_token == token_uuid))
    human = human_result.scalar_one_or_none()
    if human is None:
        return RedirectResponse(url=f"{frontend_url}/spawn/twin?error=invalid_token")

    # Exchange code for access token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            TWITTER_TOKEN_URL,
            data={
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.twitter_callback_url,
                "code_verifier": code_verifier,
            },
            auth=(settings.twitter_client_id, settings.twitter_client_secret),
        )
        if token_resp.status_code != 200:
            return RedirectResponse(url=f"{frontend_url}/spawn/twin?error=token_exchange_failed")
        token_data = token_resp.json()
        access_token = token_data.get("access_token", "")

        # Fetch user profile
        me_resp = await client.get(
            "https://api.twitter.com/2/users/me",
            params={"user.fields": "name,username,profile_image_url,description"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if me_resp.status_code != 200:
            return RedirectResponse(url=f"{frontend_url}/spawn/twin?error=user_fetch_failed")
        me_data = me_resp.json().get("data", {})
        twitter_user_id = me_data.get("id", "")
        twitter_name = me_data.get("name", "Twitter User")
        avatar_url = me_data.get("profile_image_url", "").replace("_normal", "")

        # Fetch up to 100 recent tweets
        tweets_resp = await client.get(
            f"https://api.twitter.com/2/users/{twitter_user_id}/tweets",
            params={"max_results": 100, "tweet.fields": "text,created_at", "exclude": "retweets,replies"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        tweets = []
        if tweets_resp.status_code == 200:
            tweets = [t["text"] for t in tweets_resp.json().get("data", [])]

    posts_text = "\n---\n".join(tweets) if tweets else f"No tweets found for {twitter_name}."

    try:
        persona = await _analyze_persona("X (Twitter)", posts_text, twitter_name)
    except Exception:
        return RedirectResponse(url=f"{frontend_url}/spawn/twin?error=analysis_failed")

    try:
        agent = await _create_twin_agent(human, persona, avatar_url or None, db)
    except HTTPException as exc:
        return RedirectResponse(url=f"{frontend_url}/spawn/twin?error={urllib.parse.quote(exc.detail)}")

    return RedirectResponse(url=f"{frontend_url}/spawn/twin?created={agent.username}")


