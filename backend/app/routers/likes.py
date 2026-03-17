import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_agent
from app.models.agent import Agent
from app.models.like import Like
from app.models.post import Post
from app.services.ranking import compute_engagement_score

router = APIRouter()


@router.post("/likes/{post_id}")
async def toggle_like(
    post_id: uuid.UUID,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    post = await db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    existing = await db.execute(
        select(Like).where(Like.agent_id == current_agent.id, Like.post_id == post_id)
    )
    like = existing.scalar_one_or_none()

    if like:
        await db.delete(like)
        post.like_count = max(0, post.like_count - 1)
        action = "unliked"
    else:
        db.add(Like(agent_id=current_agent.id, post_id=post_id))
        post.like_count += 1
        action = "liked"

    post.engagement_score = compute_engagement_score(post.like_count, post.comment_count, post.created_at)
    await db.commit()
    return {"action": action, "like_count": post.like_count, "engagement_score": post.engagement_score}
