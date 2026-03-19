"""
GET /api/nursery/agents

Internal endpoint for the nursery worker. Returns all nursery-enabled agents
with their API keys and persona configs. Protected by X-Nursery-Secret header.
"""

import json

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.config import settings
from app.database import get_db
from app.models.agent import Agent

router = APIRouter()


class NurseryAgent(BaseModel):
    agent_id: str
    username: str
    display_name: str
    api_key: str
    avatar_url: str | None
    nursery_persona: str | None
    style_medium: str | None
    style_mood: str | None
    style_palette: str | None
    style_extra: str | None


@router.post("/nursery/reset-avatars", status_code=200)
async def reset_broken_avatars(
    x_nursery_secret: str = Header(..., alias="X-Nursery-Secret"),
    db: AsyncSession = Depends(get_db),
):
    """Clear avatar_url for all agents whose avatar is hosted on Pollinations (broken)."""
    if x_nursery_secret != settings.nursery_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid nursery secret")

    result = await db.execute(select(Agent))
    agents = result.scalars().all()
    count = 0
    for agent in agents:
        if agent.avatar_url and "pollinations.ai" in agent.avatar_url:
            agent.avatar_url = None
            count += 1
    await db.commit()
    return {"reset": count}


@router.get("/nursery/agents", response_model=list[NurseryAgent])
async def list_nursery_agents(
    x_nursery_secret: str = Header(..., alias="X-Nursery-Secret"),
    db: AsyncSession = Depends(get_db),
):
    if x_nursery_secret != settings.nursery_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid nursery secret")

    result = await db.execute(
        select(Agent).where(Agent.nursery_enabled == True)  # noqa: E712
    )
    agents = result.scalars().all()

    out = []
    for agent in agents:
        style = {}
        if agent.nursery_style:
            try:
                style = json.loads(agent.nursery_style)
            except Exception:
                pass
        out.append(NurseryAgent(
            agent_id=str(agent.id),
            username=agent.username,
            display_name=agent.display_name,
            api_key=agent.api_key,
            avatar_url=agent.avatar_url,
            nursery_persona=agent.nursery_persona,
            style_medium=style.get("medium"),
            style_mood=style.get("mood"),
            style_palette=style.get("palette"),
            style_extra=style.get("extra"),
        ))
    return out
