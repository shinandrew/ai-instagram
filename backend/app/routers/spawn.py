"""
POST /api/spawn

Requires a signed-in human user (X-Human-Token header).
Registers a new nursery-managed agent and links it to the human.
Each human may only have one spawned agent.
"""

import base64
import io
import json
import re
import uuid as uuid_module
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status, Header
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
    language: str = "en"


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


# ─── Language helpers ─────────────────────────────────────────────────────────

_LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese (Simplified)",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
}

def _language_instruction(language: str) -> str:
    name = _LANGUAGE_NAMES.get(language, "English")
    return (
        f"\nIMPORTANT: Write the bio and nursery_persona fields in {name}. "
        "All other fields (display_name, style_medium, style_mood, style_palette, "
        "username_suggestion) must remain in English."
    )


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
    language: str = "en",
) -> dict:
    """Call GPT-4o to analyze posts and return a persona dict."""
    client = _get_openai()
    prompt = PERSONA_PROMPT.format(platform=platform, sns_name=sns_name, posts=posts[:8000]) + _language_instruction(language)
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
    language: str = "en",
) -> Agent:
    """Create a Digital Twin agent, auto-claimed, linked to human."""
    # Enforce per-human agent limit
    max_agents = human.missions_cleared + 3
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
        language=language or "en",
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent



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
    max_agents = human.missions_cleared + 3
    existing_count = await db.scalar(
        select(func.count()).select_from(Agent).where(Agent.human_id == human.id)
    ) or 0
    if existing_count >= max_agents:
        if max_agents == 3:
            detail = (
                "You've used all 3 of your starting agent slots. "
                "Complete missions on your profile page to unlock more."
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
        language=body.language or "en",
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


# ─── Twitter Bearer Token — fetch by username ────────────────────────────────

class TwitterTwinRequest(BaseModel):
    twitter_username: str   # e.g. "elonmusk" or "@elonmusk"
    language: str = "en"


class TwinSpawnResponse(BaseModel):
    agent_id: str
    username: str
    display_name: str
    avatar_url: str | None
    bio: str | None = None
    nursery_persona: str | None = None
    style_medium: str | None = None
    style_mood: str | None = None
    style_palette: str | None = None


async def _fetch_twitter_profile(handle: str) -> tuple[str, str, list[str]]:
    """Fetch an X user's name, avatar and recent original tweets.

    Returns (display_name, avatar_url, tweets). Raises HTTPException on API errors.
    """
    bearer = f"Bearer {settings.twitter_bearer_token}"

    async with httpx.AsyncClient() as client:
        # Look up user by username
        user_resp = await client.get(
            f"https://api.twitter.com/2/users/by/username/{handle}",
            params={"user.fields": "name,profile_image_url,description"},
            headers={"Authorization": bearer},
        )
        if user_resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"X user @{handle} not found")
        if user_resp.status_code == 401:
            raise HTTPException(status_code=502, detail="Twitter API: invalid Bearer Token")
        if user_resp.status_code == 403:
            err_body = user_resp.json()
            raise HTTPException(status_code=502, detail=f"Twitter API access denied (403): {err_body}")
        if user_resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Twitter API error {user_resp.status_code}: {user_resp.text[:300]}")

        user_json = user_resp.json()
        user_data = user_json.get("data", {})
        if not user_data:
            raise HTTPException(status_code=502, detail=f"Unexpected Twitter response: {user_json}")
        twitter_user_id = user_data.get("id", "")
        twitter_name = user_data.get("name", handle)
        avatar_url = user_data.get("profile_image_url", "").replace("_normal", "_400x400")

        # Fetch up to 100 recent original tweets
        tweets_resp = await client.get(
            f"https://api.twitter.com/2/users/{twitter_user_id}/tweets",
            params={
                "max_results": 100,
                "tweet.fields": "text,created_at",
                "exclude": "retweets,replies",
            },
            headers={"Authorization": bearer},
        )
        tweets = []
        if tweets_resp.status_code == 200:
            tweets = [t["text"] for t in tweets_resp.json().get("data", [])]
        elif tweets_resp.status_code == 403:
            raise HTTPException(status_code=502, detail=f"Twitter API: tweet read access denied (403) — your plan may not include timeline access. Response: {tweets_resp.text[:300]}")
        elif tweets_resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Twitter API error fetching tweets ({tweets_resp.status_code}): {tweets_resp.text[:300]}")

    if not tweets:
        raise HTTPException(status_code=422, detail=f"No public tweets found for @{handle}. The account may be private or have no posts.")

    return twitter_name, avatar_url, tweets


@router.post("/spawn/from-twitter", response_model=TwinSpawnResponse, status_code=status.HTTP_201_CREATED)
async def spawn_from_twitter(
    body: TwitterTwinRequest,
    x_human_token: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Create a Digital Twin by fetching public tweets via Bearer Token."""
    if not x_human_token:
        raise HTTPException(status_code=401, detail="Sign in required")
    if not settings.twitter_bearer_token:
        raise HTTPException(status_code=503, detail="Twitter API not configured")

    try:
        token_uuid = uuid_module.UUID(x_human_token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid human token")

    human_result = await db.execute(select(Human).where(Human.human_token == token_uuid))
    human = human_result.scalar_one_or_none()
    if human is None:
        raise HTTPException(status_code=401, detail="Invalid human token")

    handle = body.twitter_username.lstrip("@").strip()
    if not handle:
        raise HTTPException(status_code=422, detail="twitter_username cannot be empty")

    twitter_name, avatar_url, tweets = await _fetch_twitter_profile(handle)

    posts_text = "\n---\n".join(tweets)
    persona = await _analyze_persona("X (Twitter)", posts_text, twitter_name, language=body.language)
    agent = await _create_twin_agent(human, persona, avatar_url or None, db, language=body.language)

    return TwinSpawnResponse(
        agent_id=str(agent.id),
        username=agent.username,
        display_name=agent.display_name,
        avatar_url=agent.avatar_url,
        bio=persona.get("bio") or None,
        nursery_persona=persona.get("nursery_persona") or None,
        style_medium=persona.get("style_medium") or None,
        style_mood=persona.get("style_mood") or None,
        style_palette=persona.get("style_palette") or None,
    )


# ─── Document / Image Upload ──────────────────────────────────────────────────

_MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
_ALLOWED_DOC_EXTENSIONS = {".txt", ".md", ".pdf"}
_ALLOWED_IMG_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_PDF_MAGIC = b"%PDF-"
_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG"

_PERSONA_JSON_SCHEMA = """\
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
- display_name: creative handle inspired by their identity/style (max 40 chars)
- bio: 1 sentence capturing their essence (max 160 chars)
- nursery_persona: 200-300 word system prompt. Translate their expertise/aesthetic \
into a visual art style for an AI Instagram agent — e.g. marine biologist → \
underwater photography, data scientist → data visualization art, painter → \
oil landscape. Include topics they'd caption about and hashtags they'd use.
- style_medium: the artistic medium (max 60 chars)
- style_mood: mood/feeling adjectives (max 60 chars)
- style_palette: color palette description (max 60 chars)
- username_suggestion: lowercase letters/numbers/underscores only, max 20 chars"""

DOCUMENT_PERSONA_PROMPT = """\
Analyze this document (a CV, essay, personal statement, or similar personal text) \
and generate a creative AI social media agent persona that reflects the author's \
background, expertise, and personality.

Document:
{{text}}

{schema}
""".format(schema=_PERSONA_JSON_SCHEMA)

IMAGE_PERSONA_PROMPT = """\
Look at this image — it may be a portrait, a piece of artwork, a design portfolio, \
or any other visual content — and generate a creative AI social media agent persona \
inspired by what you see.

{schema}
""".format(schema=_PERSONA_JSON_SCHEMA)

COMBINED_PERSONA_PROMPT = """\
Analyze both the image and the document text below. Together they represent a person's \
visual aesthetic and background. Generate a creative AI social media agent persona \
that combines insights from both.

Document:
{{text}}

{schema}
""".format(schema=_PERSONA_JSON_SCHEMA)


def _extract_text(filename: str, data: bytes) -> str:
    """Extract plain text from uploaded file bytes."""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext in (".txt", ".md"):
        return data.decode("utf-8", errors="replace")

    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Could not read PDF: {exc}")

    raise HTTPException(status_code=415, detail="Unsupported file type")


@router.post("/spawn/from-document", response_model=TwinSpawnResponse, status_code=status.HTTP_201_CREATED)
async def spawn_from_document(
    x_human_token: str | None = Header(None),
    document: Optional[UploadFile] = File(default=None),
    image: Optional[UploadFile] = File(default=None),
    language: str = Form(default="en"),
    db: AsyncSession = Depends(get_db),
):
    """Create an agent persona from an uploaded document and/or image."""
    if not x_human_token:
        raise HTTPException(status_code=401, detail="Sign in required")
    if not document and not image:
        raise HTTPException(status_code=422, detail="Please upload at least one file.")

    try:
        token_uuid = uuid_module.UUID(x_human_token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid human token")

    human_result = await db.execute(select(Human).where(Human.human_token == token_uuid))
    human = human_result.scalar_one_or_none()
    if human is None:
        raise HTTPException(status_code=401, detail="Invalid human token")

    # ── Process document ──────────────────────────────────────────────────────
    text: str | None = None
    if document:
        fname = (document.filename or "upload").strip()
        ext = ("." + fname.rsplit(".", 1)[-1].lower()) if "." in fname else ""
        if ext not in _ALLOWED_DOC_EXTENSIONS:
            raise HTTPException(status_code=415, detail=f"Unsupported document type '{ext}'. Please upload .txt, .md, or .pdf.")
        data = await document.read(_MAX_UPLOAD_BYTES + 1)
        if len(data) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Document too large. Maximum size is 5 MB.")
        if ext == ".pdf" and not data.startswith(_PDF_MAGIC):
            raise HTTPException(status_code=415, detail="File does not appear to be a valid PDF.")
        if ext in (".txt", ".md") and b"\x00" in data:
            raise HTTPException(status_code=415, detail="Document contains binary content. Please upload a plain text file.")
        text = _extract_text(fname, data).strip()
        if len(text) < 50:
            raise HTTPException(status_code=422, detail="Document appears to be empty or could not be read.")
        text = text[:8000]

    # ── Process image ─────────────────────────────────────────────────────────
    img_b64: str | None = None
    img_mime = "image/jpeg"
    if image:
        img_fname = (image.filename or "image").strip()
        img_ext = ("." + img_fname.rsplit(".", 1)[-1].lower()) if "." in img_fname else ""
        if img_ext not in _ALLOWED_IMG_EXTENSIONS:
            raise HTTPException(status_code=415, detail=f"Unsupported image type '{img_ext}'. Please upload .jpg, .png, or .webp.")
        img_data = await image.read(_MAX_UPLOAD_BYTES + 1)
        if len(img_data) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Image too large. Maximum size is 5 MB.")
        if img_ext in (".jpg", ".jpeg") and not img_data.startswith(_JPEG_MAGIC):
            raise HTTPException(status_code=415, detail="File does not appear to be a valid JPEG.")
        if img_ext == ".png" and not img_data.startswith(_PNG_MAGIC):
            raise HTTPException(status_code=415, detail="File does not appear to be a valid PNG.")
        if img_ext == ".webp" and not (img_data[:4] == b"RIFF" and img_data[8:12] == b"WEBP"):
            raise HTTPException(status_code=415, detail="File does not appear to be a valid WebP.")
        img_b64 = base64.b64encode(img_data).decode()
        if img_ext == ".png":
            img_mime = "image/png"
        elif img_ext == ".webp":
            img_mime = "image/webp"

    # ── Build GPT-4o message ──────────────────────────────────────────────────
    client = _get_openai()
    img_part = {"type": "image_url", "image_url": {"url": f"data:{img_mime};base64,{img_b64}"}}

    lang_note = _language_instruction(language)
    if img_b64 and text:
        prompt_text = COMBINED_PERSONA_PROMPT.format(text=text) + lang_note
        msg_content: str | list = [img_part, {"type": "text", "text": prompt_text}]
    elif img_b64:
        msg_content = [img_part, {"type": "text", "text": IMAGE_PERSONA_PROMPT + lang_note}]
    else:
        msg_content = DOCUMENT_PERSONA_PROMPT.format(text=text) + lang_note

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": msg_content}],
            temperature=0.8,
            max_tokens=1200,
        )
        raw = (response.choices[0].message.content or "{}").strip()
        if raw.startswith("```"):
            raw = re.sub(r"```[a-z]*\n?", "", raw).strip().rstrip("`").strip()
        persona = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"Persona analysis failed: {exc}")

    agent = await _create_twin_agent(human, persona, None, db, language=language)

    return TwinSpawnResponse(
        agent_id=str(agent.id),
        username=agent.username,
        display_name=agent.display_name,
        avatar_url=agent.avatar_url,
        bio=persona.get("bio") or None,
        nursery_persona=persona.get("nursery_persona") or None,
        style_medium=persona.get("style_medium") or None,
        style_mood=persona.get("style_mood") or None,
        style_palette=persona.get("style_palette") or None,
    )


# ─── Public Twin Preview — the magic moment before sign-up ──────────────────
#
# Flow: visitor enters an X handle on the landing page (no account needed) →
# we analyze the persona and show it live → registration is how you KEEP the
# twin, not how you start. Previews expire after 24h.

import hashlib
import time as _time
from datetime import datetime, timedelta, timezone

from app.models.twin_preview import TwinPreview
from app.models.follow import Follow
from app.models.agent import Agent as _Agent
from app.models.agent_memory import append_memory
from app.models.funnel_event import FunnelEvent
from app.routers.notifications import maybe_notify


def _funnel(db: AsyncSession, event_type: str, request: Request | None = None,
            preview_id=None, handle: str = "", referrer: str = "", detail: str = "") -> None:
    """Queue a funnel event on the session (committed with the caller's commit)."""
    ip_hash = user_agent = None
    if request is not None:
        raw_ip = (request.headers.get("x-forwarded-for")
                  or (request.client.host if request.client else "")).split(",")[0].strip()
        ip_hash = hashlib.sha256(raw_ip.encode()).hexdigest() if raw_ip else None
        user_agent = (request.headers.get("user-agent") or "")[:512] or None
    db.add(FunnelEvent(
        event_type=event_type,
        preview_id=preview_id,
        handle=(handle or "")[:100] or None,
        referrer=(referrer or "")[:500] or None,
        detail=(detail or "")[:300] or None,
        ip_hash=ip_hash,
        user_agent=user_agent,
    ))

# Simple in-memory rate limiting (single-instance backend).
_PREVIEW_BUCKET: dict[str, list[float]] = {}
_PREVIEW_GLOBAL: list[float] = []
_PREVIEW_IP_LIMIT = 5        # per IP per hour
_PREVIEW_GLOBAL_LIMIT = 60   # across all IPs per hour


def _check_preview_rate(ip: str) -> None:
    now = _time.time()
    cutoff = now - 3600
    bucket = [t for t in _PREVIEW_BUCKET.get(ip, []) if t > cutoff]
    _PREVIEW_GLOBAL[:] = [t for t in _PREVIEW_GLOBAL if t > cutoff]
    if len(bucket) >= _PREVIEW_IP_LIMIT:
        raise HTTPException(status_code=429, detail="Too many previews from this address — try again in an hour.")
    if len(_PREVIEW_GLOBAL) >= _PREVIEW_GLOBAL_LIMIT:
        raise HTTPException(status_code=429, detail="Preview service is busy — try again shortly.")
    bucket.append(now)
    _PREVIEW_BUCKET[ip] = bucket
    _PREVIEW_GLOBAL.append(now)


async def _sample_first_post(persona: dict, language: str) -> tuple[str, str]:
    """Generate the twin's first post idea (caption + image subject) — cheap model."""
    client = _get_openai()
    lang_name = _LANGUAGE_NAMES.get(language, "English")
    prompt = (
        "You are an AI Instagram agent with this persona:\n"
        f"Bio: {persona.get('bio', '')}\n"
        f"Persona: {(persona.get('nursery_persona') or '')[:600]}\n"
        f"Style: {persona.get('style_medium', '')}, {persona.get('style_mood', '')}, "
        f"{persona.get('style_palette', '')}\n\n"
        "Write your FIRST post on the platform. Return JSON only:\n"
        '{"caption": "<instagram caption in ' + lang_name + ', casual, in the persona\'s voice, max 150 chars>", '
        '"subject": "<vivid concrete Flux image prompt in English matching the persona\'s aesthetic>"}'
    )
    try:
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.9,
            max_tokens=300,
        )
        raw = json.loads(resp.choices[0].message.content or "{}")
        return raw.get("caption", ""), raw.get("subject", "")
    except Exception:
        return "", ""


class TwinPreviewRequest(BaseModel):
    twitter_username: str
    language: str = "en"
    invite_username: str = ""   # agent username from a friend's invite link
    referrer: str = ""          # first-touch referrer captured by the frontend


class TwinPreviewResponse(BaseModel):
    preview_id: str
    handle: str
    display_name: str
    bio: str | None = None
    nursery_persona: str | None = None
    style_medium: str | None = None
    style_mood: str | None = None
    style_palette: str | None = None
    avatar_url: str | None = None
    sample_caption: str | None = None
    expires_at: str


@router.post("/spawn/preview-twitter", response_model=TwinPreviewResponse)
async def preview_from_twitter(
    body: TwinPreviewRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Public — generate a twin persona preview from an X handle, no sign-in."""
    if not settings.twitter_bearer_token:
        raise HTTPException(status_code=503, detail="Twitter API not configured")

    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
    _check_preview_rate(ip)

    handle = body.twitter_username.lstrip("@").strip()
    if not handle:
        raise HTTPException(status_code=422, detail="twitter_username cannot be empty")

    _funnel(db, "preview_started", request, handle=handle, referrer=body.referrer)
    await db.commit()  # persist even if the preview generation below fails

    try:
        twitter_name, avatar_url, tweets = await _fetch_twitter_profile(handle)
        posts_text = "\n---\n".join(tweets)
        persona = await _analyze_persona("X (Twitter)", posts_text, twitter_name, language=body.language)
    except HTTPException as e:
        _funnel(db, "preview_failed", request, handle=handle, referrer=body.referrer,
                detail=str(e.detail)[:300])
        await db.commit()
        raise
    sample_caption, sample_subject = await _sample_first_post(persona, body.language)

    invited_by_id = None
    if body.invite_username:
        inviter = (await db.execute(
            select(_Agent).where(_Agent.username == body.invite_username.strip().lstrip("@"))
        )).scalar_one_or_none()
        if inviter:
            invited_by_id = inviter.id

    preview = TwinPreview(
        source="twitter",
        handle=handle,
        persona_json=json.dumps(persona),
        avatar_url=avatar_url or None,
        sample_caption=sample_caption or None,
        sample_subject=sample_subject or None,
        language=body.language or "en",
        invited_by_agent_id=invited_by_id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(preview)
    await db.flush()
    _funnel(db, "preview_completed", request, preview_id=preview.id,
            handle=handle, referrer=body.referrer)
    await db.commit()
    await db.refresh(preview)

    return TwinPreviewResponse(
        preview_id=str(preview.id),
        handle=handle,
        display_name=persona.get("display_name") or twitter_name,
        bio=persona.get("bio") or None,
        nursery_persona=persona.get("nursery_persona") or None,
        style_medium=persona.get("style_medium") or None,
        style_mood=persona.get("style_mood") or None,
        style_palette=persona.get("style_palette") or None,
        avatar_url=avatar_url or None,
        sample_caption=sample_caption or None,
        expires_at=preview.expires_at.isoformat(),
    )


@router.get("/spawn/preview/{preview_id}", response_model=TwinPreviewResponse)
async def get_preview(preview_id: uuid_module.UUID, db: AsyncSession = Depends(get_db)):
    """Public — re-fetch a preview (used after the sign-in redirect)."""
    preview = await db.get(TwinPreview, preview_id)
    if preview is None:
        raise HTTPException(status_code=404, detail="Preview not found")
    persona = json.loads(preview.persona_json)
    return TwinPreviewResponse(
        preview_id=str(preview.id),
        handle=preview.handle,
        display_name=persona.get("display_name") or preview.handle,
        bio=persona.get("bio") or None,
        nursery_persona=persona.get("nursery_persona") or None,
        style_medium=persona.get("style_medium") or None,
        style_mood=persona.get("style_mood") or None,
        style_palette=persona.get("style_palette") or None,
        avatar_url=preview.avatar_url,
        sample_caption=preview.sample_caption,
        expires_at=preview.expires_at.isoformat(),
    )


class ClaimPreviewRequest(BaseModel):
    preview_id: str
    referrer: str = ""


@router.post("/spawn/claim-preview", response_model=TwinSpawnResponse, status_code=status.HTTP_201_CREATED)
async def claim_preview(
    body: ClaimPreviewRequest,
    request: Request,
    x_human_token: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Convert an unclaimed preview into a real, living agent (sign-in required)."""
    if not x_human_token:
        raise HTTPException(status_code=401, detail="Sign in required to claim your twin")
    try:
        token_uuid = uuid_module.UUID(x_human_token)
        preview_uuid = uuid_module.UUID(body.preview_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token or preview id")

    human = (await db.execute(select(Human).where(Human.human_token == token_uuid))).scalar_one_or_none()
    if human is None:
        raise HTTPException(status_code=401, detail="Invalid human token")

    preview = await db.get(TwinPreview, preview_uuid)
    if preview is None:
        raise HTTPException(status_code=404, detail="Preview not found")
    if preview.claimed_agent_id is not None:
        raise HTTPException(status_code=409, detail="This twin has already been claimed")
    now = datetime.now(timezone.utc)
    expires = preview.expires_at if preview.expires_at.tzinfo else preview.expires_at.replace(tzinfo=timezone.utc)
    if expires < now:
        raise HTTPException(status_code=410, detail="This preview has expired — generate a new one")

    persona = json.loads(preview.persona_json)
    agent = await _create_twin_agent(human, persona, preview.avatar_url, db, language=preview.language)

    preview.claimed_agent_id = agent.id

    # Friend-twin introduction: mutual follow + seeded memory so they actually meet
    if preview.invited_by_agent_id:
        inviter = await db.get(_Agent, preview.invited_by_agent_id)
        if inviter and inviter.id != agent.id:
            db.add(Follow(follower_id=agent.id, following_id=inviter.id))
            db.add(Follow(follower_id=inviter.id, following_id=agent.id))
            agent.following_count += 1
            agent.follower_count += 1
            inviter.following_count += 1
            inviter.follower_count += 1
            await append_memory(db, agent.id, inviter.id,
                                f"@{inviter.username} is the twin of the friend who invited you here — a natural first conversation partner")
            await append_memory(db, inviter.id, agent.id,
                                f"@{agent.username} just arrived — the twin of a friend of your owner. Welcome them on their first post")
            await maybe_notify(db, type="friend_twin_joined", target_agent=inviter, actor_agent_id=agent.id)

    _funnel(db, "preview_claimed", request, preview_id=preview.id,
            handle=preview.handle, referrer=body.referrer)
    await db.commit()
    await db.refresh(agent)

    return TwinSpawnResponse(
        agent_id=str(agent.id),
        username=agent.username,
        display_name=agent.display_name,
        avatar_url=agent.avatar_url,
        bio=persona.get("bio") or None,
        nursery_persona=persona.get("nursery_persona") or None,
        style_medium=persona.get("style_medium") or None,
        style_mood=persona.get("style_mood") or None,
        style_palette=persona.get("style_palette") or None,
    )
