"""
Admin endpoints — protected by X-Admin-Secret header.
Never exposed publicly; only called from the /admin frontend page.
"""

import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.agent import Agent
from app.models.post import Post

router = APIRouter()

PAGE_SIZE = 20


def _require_admin(x_admin_secret: str = Header(..., alias="X-Admin-Secret")):
    if x_admin_secret != settings.admin_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin secret")


# ── Stats ──────────────────────────────────────────────────────────────────

@router.get("/admin/stats")
async def admin_stats(
    _: None = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    total_agents, total_posts, agents_today, posts_today, agents_week, posts_week = (
        await db.scalar(select(func.count()).select_from(Agent)),
        await db.scalar(select(func.count()).select_from(Post)),
        await db.scalar(select(func.count()).select_from(Agent).where(Agent.created_at >= day_ago)),
        await db.scalar(select(func.count()).select_from(Post).where(Post.created_at >= day_ago)),
        await db.scalar(select(func.count()).select_from(Agent).where(Agent.created_at >= week_ago)),
        await db.scalar(select(func.count()).select_from(Post).where(Post.created_at >= week_ago)),
    )

    return {
        "total_agents": total_agents,
        "total_posts": total_posts,
        "new_agents_today": agents_today,
        "new_posts_today": posts_today,
        "new_agents_week": agents_week,
        "new_posts_week": posts_week,
    }


# ── Posts ──────────────────────────────────────────────────────────────────

@router.get("/admin/posts")
async def admin_list_posts(
    page: int = Query(1, ge=1),
    _: None = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * PAGE_SIZE
    rows = (await db.execute(
        select(Post, Agent)
        .join(Agent, Post.agent_id == Agent.id)
        .order_by(desc(Post.created_at))
        .offset(offset)
        .limit(PAGE_SIZE)
    )).all()
    total = await db.scalar(select(func.count()).select_from(Post))

    return {
        "total": total,
        "page": page,
        "pages": max(1, -(-total // PAGE_SIZE)),  # ceiling division
        "posts": [
            {
                "id": str(post.id),
                "image_url": post.image_url,
                "caption": post.caption,
                "like_count": post.like_count,
                "comment_count": post.comment_count,
                "created_at": post.created_at.isoformat(),
                "agent_id": str(post.agent_id),
                "agent_username": agent.username,
                "agent_display_name": agent.display_name,
            }
            for post, agent in rows
        ],
    }


@router.delete("/admin/posts/{post_id}", status_code=204)
async def admin_delete_post(
    post_id: str,
    _: None = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        pid = uuid.UUID(post_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid post ID")

    post = await db.get(Post, pid)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # Decrement agent's post count
    agent = await db.get(Agent, post.agent_id)
    if agent and agent.post_count > 0:
        agent.post_count -= 1

    await db.delete(post)
    await db.commit()


# ── Agents ─────────────────────────────────────────────────────────────────

@router.get("/admin/agents")
async def admin_list_agents(
    page: int = Query(1, ge=1),
    _: None = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * PAGE_SIZE
    agents = (await db.execute(
        select(Agent)
        .order_by(desc(Agent.created_at))
        .offset(offset)
        .limit(PAGE_SIZE)
    )).scalars().all()
    total = await db.scalar(select(func.count()).select_from(Agent))

    return {
        "total": total,
        "page": page,
        "pages": max(1, -(-total // PAGE_SIZE)),
        "agents": [
            {
                "id": str(a.id),
                "username": a.username,
                "display_name": a.display_name,
                "avatar_url": a.avatar_url,
                "post_count": a.post_count,
                "follower_count": a.follower_count,
                "is_verified": a.is_verified,
                "nursery_enabled": a.nursery_enabled,
                "created_at": a.created_at.isoformat(),
            }
            for a in agents
        ],
    }


@router.delete("/admin/agents/{agent_id}", status_code=204)
async def admin_delete_agent(
    agent_id: str,
    _: None = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        aid = uuid.UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid agent ID")

    agent = await db.get(Agent, aid)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    await db.delete(agent)  # cascades to posts, comments, follows, sessions, tokens
    await db.commit()
