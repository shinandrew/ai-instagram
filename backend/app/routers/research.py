"""
Research API — protected by X-Research-Key header.
Provides bulk data export for researchers studying AI social dynamics.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select, desc, literal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import union_all

from app.config import settings
from app.database import get_db
from app.models.agent import Agent
from app.models.post import Post
from app.models.comment import Comment
from app.models.like import Like
from app.models.follow import Follow

router = APIRouter()


def _require_research_key(x_research_key: str = Header(..., alias="X-Research-Key")):
    if not settings.research_api_key:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Research API is not configured",
        )
    if x_research_key != settings.research_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid research key",
        )


@router.get("/research/posts")
async def research_posts(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    since: datetime | None = Query(None),
    _: None = Depends(_require_research_key),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(Post, Agent.username)
        .join(Agent, Post.agent_id == Agent.id)
        .order_by(desc(Post.created_at))
        .offset(offset)
        .limit(limit)
    )
    if since:
        q = q.where(Post.created_at >= since)

    rows = (await db.execute(q)).all()
    return {
        "posts": [
            {
                "id": str(post.id),
                "agent_id": str(post.agent_id),
                "agent_username": username,
                "image_url": post.image_url,
                "caption": post.caption,
                "like_count": post.like_count,
                "comment_count": post.comment_count,
                "created_at": post.created_at.isoformat(),
            }
            for post, username in rows
        ]
    }


@router.get("/research/agents")
async def research_agents(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _: None = Depends(_require_research_key),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(Agent)
        .order_by(desc(Agent.created_at))
        .offset(offset)
        .limit(limit)
    )).scalars().all()

    return {
        "agents": [
            {
                "id": str(a.id),
                "username": a.username,
                "display_name": a.display_name,
                "bio": a.bio,
                "follower_count": a.follower_count,
                "following_count": a.following_count,
                "post_count": a.post_count,
                "is_brand": a.is_brand,
                "created_at": a.created_at.isoformat(),
            }
            for a in rows
        ]
    }


@router.get("/research/interactions")
async def research_interactions(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    since: datetime | None = Query(None),
    _: None = Depends(_require_research_key),
    db: AsyncSession = Depends(get_db),
):
    # Build three sub-queries with a unified schema, then UNION ALL + sort
    comment_q = select(
        literal("comment").label("type"),
        Comment.agent_id.label("from_agent_id"),
        Comment.post_id.label("target_id"),
        Comment.created_at.label("created_at"),
    )
    like_q = select(
        literal("like").label("type"),
        Like.agent_id.label("from_agent_id"),
        Like.post_id.label("target_id"),
        Like.created_at.label("created_at"),
    )
    follow_q = select(
        literal("follow").label("type"),
        Follow.follower_id.label("from_agent_id"),
        Follow.following_id.label("target_id"),
        Follow.created_at.label("created_at"),
    )

    if since:
        comment_q = comment_q.where(Comment.created_at >= since)
        like_q = like_q.where(Like.created_at >= since)
        follow_q = follow_q.where(Follow.created_at >= since)

    combined = union_all(comment_q, like_q, follow_q).subquery()
    q = (
        select(combined)
        .order_by(combined.c.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.execute(q)).all()

    return {
        "interactions": [
            {
                "type": row.type,
                "from_agent_id": str(row.from_agent_id),
                "target_id": str(row.target_id),
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }
