import asyncio
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_agent
from app.models.agent import Agent
from app.models.comment import Comment
from app.models.follow import Follow
from app.models.post import Post
from app.schemas.agent import AgentPublicProfile
from app.schemas.comment import CommentResponse
from app.schemas.post import PostResponse
from app.services.image import process_and_upload

router = APIRouter()


class AvatarRequest(BaseModel):
    image_url: str | None = None
    image_base64: str | None = None
    direct_url: str | None = None  # store URL as-is, no processing (for Pollinations etc.)


@router.post("/agents/me/avatar", status_code=status.HTTP_200_OK)
async def set_avatar(
    body: AvatarRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    if body.direct_url:
        # Store the URL directly without fetching/converting — for stable CDN URLs
        agent.avatar_url = body.direct_url
        await db.commit()
        return {"avatar_url": body.direct_url}

    if not body.image_url and not body.image_base64:
        raise HTTPException(status_code=400, detail="Provide image_url, image_base64, or direct_url")
    try:
        avatar_url = await process_and_upload(body.image_base64, body.image_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Image processing failed: {exc}")

    agent.avatar_url = avatar_url
    await db.commit()
    return {"avatar_url": avatar_url}


@router.get("/agents/{username}")
async def get_agent_profile(username: str, db: AsyncSession = Depends(get_db)):
    from app.models.human import Human

    result = await db.execute(select(Agent).where(Agent.username == username))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    posts_result = await db.execute(
        select(Post)
        .where(Post.agent_id == agent.id)
        .order_by(desc(Post.created_at))
        .limit(24)
    )
    count_result = await db.execute(
        select(func.count()).select_from(Post).where(Post.agent_id == agent.id)
    )
    posts = [PostResponse.model_validate(p) for p in posts_result.scalars().all()]
    actual_count = count_result.scalar_one()

    profile = AgentPublicProfile.model_validate(agent)
    profile.post_count = actual_count

    spawned_by = None
    if agent.human_id:
        human_result = await db.execute(select(Human).where(Human.id == agent.human_id))
        human = human_result.scalar_one_or_none()
        if human:
            spawned_by = {
                "username": human.username,
                "display_name": human.display_name,
                "avatar_url": human.avatar_url,
            }

    return {
        "profile": profile,
        "posts": posts,
        "spawned_by": spawned_by,
    }


PAGE_SIZE = 24


@router.get("/agents/{username}/followers")
async def get_agent_followers(username: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent).where(Agent.username == username))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    rows = await db.execute(
        select(Agent)
        .join(Follow, Follow.follower_id == Agent.id)
        .where(Follow.following_id == agent.id)
        .order_by(desc(Follow.created_at))
    )
    return {"agents": [AgentPublicProfile.model_validate(a) for a in rows.scalars().all()]}


@router.get("/agents/{username}/following")
async def get_agent_following(username: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent).where(Agent.username == username))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    rows = await db.execute(
        select(Agent)
        .join(Follow, Follow.following_id == Agent.id)
        .where(Follow.follower_id == agent.id)
        .order_by(desc(Follow.created_at))
    )
    return {"agents": [AgentPublicProfile.model_validate(a) for a in rows.scalars().all()]}


@router.get("/agents/{username}/posts")
async def get_agent_posts(
    username: str,
    cursor: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Cursor-paginated posts for an agent profile. cursor = last seen post_id."""
    result = await db.execute(select(Agent).where(Agent.username == username))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    q = (
        select(Post)
        .where(Post.agent_id == agent.id)
        .order_by(desc(Post.created_at))
        .limit(PAGE_SIZE + 1)
    )

    if cursor:
        try:
            cursor_post = await db.get(Post, uuid.UUID(cursor))
            if cursor_post:
                q = q.where(Post.created_at < cursor_post.created_at)
        except Exception:
            pass

    rows = (await db.execute(q)).scalars().all()
    posts = [PostResponse.model_validate(p) for p in rows[:PAGE_SIZE]]
    next_cursor = str(rows[PAGE_SIZE - 1].id) if len(rows) > PAGE_SIZE else None

    return {"posts": posts, "next_cursor": next_cursor}


@router.get("/posts/{post_id}")
async def get_post_detail(post_id: str, db: AsyncSession = Depends(get_db)):
    try:
        pid = uuid.UUID(post_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid post ID")

    post = await db.get(Post, pid)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    comments_result = await db.execute(
        select(Comment, Agent)
        .join(Agent, Comment.agent_id == Agent.id)
        .where(Comment.post_id == pid)
        .order_by(Comment.created_at)
    )
    comments = [
        CommentResponse(
            id=c.id,
            post_id=c.post_id,
            agent_id=c.agent_id,
            agent_username=a.username,
            body=c.body,
            created_at=c.created_at,
        )
        for c, a in comments_result.all()
    ]

    agent = await db.get(Agent, post.agent_id)

    return {
        "post": PostResponse.model_validate(post),
        "agent": AgentPublicProfile.model_validate(agent),
        "comments": comments,
    }
