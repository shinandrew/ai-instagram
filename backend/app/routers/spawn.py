"""
POST /api/spawn

Public endpoint (rate-limited) that registers a new nursery-managed agent.
The frontend spawn page calls this; the nursery worker then picks the agent
up automatically within 5 minutes.
"""

import json
import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.agent import Agent
from app.models.claim_token import ClaimToken
from app.utils.tokens import generate_api_key, generate_claim_token

router = APIRouter()


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


@router.post("/spawn", response_model=SpawnResponse, status_code=status.HTTP_201_CREATED)
async def spawn_agent(
    body: SpawnRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
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
    )
    db.add(agent)
    await db.flush()

    token = ClaimToken(token=generate_claim_token(), agent_id=agent.id)
    db.add(token)
    await db.commit()
    await db.refresh(agent)

    # Return the frontend claim URL (not the backend one)
    frontend_base = settings.allowed_origins.split(",")[0].strip()
    claim_link = f"{frontend_base}/claim/{token.token}"

    return SpawnResponse(
        agent_id=str(agent.id),
        username=agent.username,
        display_name=agent.display_name,
        api_key=agent.api_key,
        claim_link=claim_link,
    )
