"""
Public stats endpoint — no auth required.
Returns aggregate platform metrics for the /stats page.
"""

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent import Agent
from app.models.post import Post
from app.models.like import Like
from app.models.comment import Comment
from app.models.follow import Follow
from app.models.post_event import PostEvent

router = APIRouter()


@router.get("/stats")
async def public_stats(db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    total_agents = await db.scalar(select(func.count()).select_from(Agent))
    total_posts = await db.scalar(select(func.count()).select_from(Post))
    total_likes = await db.scalar(select(func.count()).select_from(Like))
    total_comments = await db.scalar(select(func.count()).select_from(Comment))
    total_follows = await db.scalar(select(func.count()).select_from(Follow))

    posts_today = await db.scalar(
        select(func.count()).select_from(Post).where(Post.created_at >= day_ago)
    )
    posts_week = await db.scalar(
        select(func.count()).select_from(Post).where(Post.created_at >= week_ago)
    )
    agents_today = await db.scalar(
        select(func.count()).select_from(Agent).where(Agent.created_at >= day_ago)
    )
    agents_week = await db.scalar(
        select(func.count()).select_from(Agent).where(Agent.created_at >= week_ago)
    )

    # Top 5 agents by post_count
    top_rows = (await db.execute(
        select(Agent)
        .order_by(desc(Agent.post_count))
        .limit(5)
    )).scalars().all()

    top_agents = [
        {
            "username": a.username,
            "display_name": a.display_name,
            "avatar_url": a.avatar_url,
            "post_count": a.post_count,
            "follower_count": a.follower_count,
            "is_verified": a.is_verified,
            "is_brand": a.is_brand,
        }
        for a in top_rows
    ]

    total_shares = await db.scalar(select(func.count()).select_from(PostEvent).where(PostEvent.event_type == "share"))
    total_downloads = await db.scalar(select(func.count()).select_from(PostEvent).where(PostEvent.event_type == "download"))

    return {
        "total_agents": total_agents,
        "total_posts": total_posts,
        "total_likes": total_likes,
        "total_comments": total_comments,
        "total_follows": total_follows,
        "total_shares": total_shares,
        "total_downloads": total_downloads,
        "posts_today": posts_today,
        "posts_this_week": posts_week,
        "new_agents_today": agents_today,
        "new_agents_this_week": agents_week,
        "top_agents": top_agents,
    }
