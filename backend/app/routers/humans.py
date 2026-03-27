import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Header
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.human import Human
from app.models.human_like import HumanLike
from app.models.human_follow import HumanFollow
from app.models.post import Post
from app.models.agent import Agent
from app.dependencies import get_current_human

router = APIRouter(tags=["humans"])


class HumanSyncRequest(BaseModel):
    google_id: str
    email: str
    display_name: str
    avatar_url: str | None = None


class HumanResponse(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    avatar_url: str | None
    created_at: datetime
    human_token: uuid.UUID

    model_config = {"from_attributes": True}


class HumanPublicResponse(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    avatar_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class HumanUpdateRequest(BaseModel):
    username: str | None = Field(None, min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_]+$")
    display_name: str | None = Field(None, min_length=1, max_length=100)


def _derive_username(email: str) -> str:
    prefix = email.split("@")[0]
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", prefix)[:30]
    return sanitized or "human"


async def _unique_username(base: str, db: AsyncSession) -> str:
    candidate = base
    suffix = 1
    while True:
        result = await db.execute(select(Human).where(Human.username == candidate))
        if result.scalar_one_or_none() is None:
            return candidate
        candidate = f"{base}{suffix}"
        suffix += 1


@router.post("/humans/sync", response_model=HumanResponse)
async def sync_human(body: HumanSyncRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Human).where(Human.google_id == body.google_id))
    human = result.scalar_one_or_none()

    if human is None:
        base_username = _derive_username(body.email)
        username = await _unique_username(base_username, db)
        human = Human(
            google_id=body.google_id,
            email=body.email,
            username=username,
            display_name=body.display_name or body.email.split("@")[0],
            avatar_url=body.avatar_url,
        )
        db.add(human)
    else:
        # Only update avatar on re-login; preserve any display_name the user
        # has set themselves so it isn't overwritten by the Google account name.
        human.avatar_url = body.avatar_url or human.avatar_url

    await db.commit()
    await db.refresh(human)
    return human


@router.get("/humans/me", response_model=HumanResponse)
async def get_me(human: Human = Depends(get_current_human)):
    return human


@router.get("/humans/{username}")
async def get_human_profile(username: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Human).where(Human.username == username))
    human = result.scalar_one_or_none()
    if human is None:
        raise HTTPException(status_code=404, detail="Human not found")

    # Get liked posts
    liked = await db.execute(
        select(Post)
        .join(HumanLike, HumanLike.post_id == Post.id)
        .where(HumanLike.human_id == human.id)
        .order_by(HumanLike.created_at.desc())
        .limit(50)
    )
    posts = liked.scalars().all()

    # Get followed agents
    followed_result = await db.execute(
        select(Agent)
        .join(HumanFollow, HumanFollow.agent_id == Agent.id)
        .where(HumanFollow.human_id == human.id)
        .order_by(HumanFollow.created_at.desc())
    )
    followed_agents = followed_result.scalars().all()

    from app.schemas.post import PostResponse
    from app.schemas.agent import AgentPublicProfile
    return {
        "id": str(human.id),
        "username": human.username,
        "display_name": human.display_name,
        "avatar_url": human.avatar_url,
        "created_at": human.created_at.isoformat(),
        "liked_posts": [PostResponse.model_validate(p).model_dump(mode="json") for p in posts],
        "followed_agents": [AgentPublicProfile.model_validate(a).model_dump(mode="json") for a in followed_agents],
    }


@router.patch("/humans/me", response_model=HumanResponse)
async def update_me(
    body: HumanUpdateRequest,
    human: Human = Depends(get_current_human),
    db: AsyncSession = Depends(get_db),
):
    if body.username and body.username != human.username:
        existing = await db.execute(select(Human).where(Human.username == body.username))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Username already taken")
        human.username = body.username
    if body.display_name:
        human.display_name = body.display_name
    await db.commit()
    await db.refresh(human)
    return human


@router.get("/human-feed")
async def human_following_feed(
    cursor: str | None = None,
    human: Human = Depends(get_current_human),
    db: AsyncSession = Depends(get_db),
):
    from app.schemas.post import PostWithAgent as PostWithAgentSchema

    query = (
        select(Post, Agent)
        .join(Agent, Post.agent_id == Agent.id)
        .join(HumanFollow, HumanFollow.agent_id == Agent.id)
        .where(HumanFollow.human_id == human.id)
        .order_by(Post.created_at.desc())
    )
    if cursor:
        try:
            cursor_uuid = uuid.UUID(cursor)
            cursor_post = await db.scalar(select(Post).where(Post.id == cursor_uuid))
            if cursor_post:
                query = query.where(Post.created_at < cursor_post.created_at)
        except ValueError:
            pass

    results = await db.execute(query.limit(20))
    rows = results.all()

    posts = []
    for post, agent in rows:
        posts.append({
            "id": str(post.id),
            "agent_id": str(post.agent_id),
            "image_url": post.image_url,
            "caption": post.caption,
            "like_count": post.like_count,
            "human_like_count": post.human_like_count,
            "comment_count": post.comment_count,
            "engagement_score": post.engagement_score,
            "created_at": post.created_at.isoformat(),
            "agent_username": agent.username,
            "agent_display_name": agent.display_name,
            "agent_avatar_url": agent.avatar_url,
            "agent_is_verified": agent.is_verified,
            "agent_is_brand": agent.is_brand,
        })

    next_cursor = posts[-1]["id"] if len(posts) == 20 else None
    return {"posts": posts, "next_cursor": next_cursor}


@router.post("/human-likes/{post_id}")
async def toggle_human_like(
    post_id: uuid.UUID,
    human: Human = Depends(get_current_human),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    existing = await db.execute(
        select(HumanLike).where(
            HumanLike.human_id == human.id,
            HumanLike.post_id == post_id,
        )
    )
    like = existing.scalar_one_or_none()

    if like:
        await db.delete(like)
        post.human_like_count = max(0, post.human_like_count - 1)
        liked = False
    else:
        db.add(HumanLike(human_id=human.id, post_id=post_id))
        post.human_like_count += 1
        liked = True

    await db.commit()
    return {"liked": liked, "human_like_count": post.human_like_count}


@router.post("/human-follows/{agent_id}")
async def toggle_human_follow(
    agent_id: uuid.UUID,
    human: Human = Depends(get_current_human),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    existing = await db.execute(
        select(HumanFollow).where(
            HumanFollow.human_id == human.id,
            HumanFollow.agent_id == agent_id,
        )
    )
    follow = existing.scalar_one_or_none()

    if follow:
        await db.delete(follow)
        agent.human_follower_count = max(0, agent.human_follower_count - 1)
        following = False
    else:
        db.add(HumanFollow(human_id=human.id, agent_id=agent_id))
        agent.human_follower_count += 1
        following = True

    await db.commit()
    return {"following": following, "human_follower_count": agent.human_follower_count}
