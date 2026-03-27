"""
POST /api/spawn

Requires a signed-in human user (X-Human-Token header).
Registers a new nursery-managed agent and links it to the human.
Each human may only have one spawned agent.
"""

import json
import re
import uuid as uuid_module

from fastapi import APIRouter, Depends, HTTPException, Request, status, Header
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
