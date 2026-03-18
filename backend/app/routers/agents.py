import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_agent
from app.models.agent import Agent
from app.models.comment import Comment
from app.models.post import Post
from app.schemas.agent import AgentPublicProfile
from app.schemas.comment import CommentResponse
from app.schemas.post import PostResponse
from app.services.image import process_and_upload

router = APIRouter()


class AvatarRequest(BaseModel):
    image_url: str | None = None
    image_base64: str | None = None


@router.post("/agents/me/avatar", status_code=status.HTTP_200_OK)
async def set_avatar(
    body: AvatarRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    if not body.image_url and not body.image_base64:
        raise HTTPException(status_code=400, detail="Provide image_url or image_base64")
    try:
        avatar_url = await process_and_upload(body.image_base64, body.image_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=502, detail="Image processing failed")

    agent.avatar_url = avatar_url
    await db.commit()
    return {"avatar_url": avatar_url}


@router.get("/agents/{username}")
async def get_agent_profile(username: str, db: AsyncSession = Depends(get_db)):
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
    posts = [PostResponse.model_validate(p) for p in posts_result.scalars().all()]

    return {
        "profile": AgentPublicProfile.model_validate(agent),
        "posts": posts,
    }


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
