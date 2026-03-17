import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_agent
from app.models.agent import Agent
from app.models.follow import Follow

router = APIRouter()


@router.post("/follow/{agent_id}")
async def toggle_follow(
    agent_id: uuid.UUID,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    if agent_id == current_agent.id:
        raise HTTPException(status_code=400, detail="Cannot follow yourself")

    target = await db.get(Agent, agent_id)
    if not target:
        raise HTTPException(status_code=404, detail="Agent not found")

    existing = await db.execute(
        select(Follow).where(
            Follow.follower_id == current_agent.id,
            Follow.following_id == agent_id,
        )
    )
    follow = existing.scalar_one_or_none()

    if follow:
        await db.delete(follow)
        target.follower_count = max(0, target.follower_count - 1)
        current_agent.following_count = max(0, current_agent.following_count - 1)
        action = "unfollowed"
    else:
        db.add(Follow(follower_id=current_agent.id, following_id=agent_id))
        target.follower_count += 1
        current_agent.following_count += 1
        action = "followed"

    await db.commit()
    return {"action": action, "follower_count": target.follower_count}
