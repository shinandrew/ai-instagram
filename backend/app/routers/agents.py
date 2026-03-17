import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent import Agent
from app.models.comment import Comment
from app.models.post import Post
from app.schemas.agent import AgentPublicProfile
from app.schemas.comment import CommentResponse
from app.schemas.post import PostResponse

router = APIRouter()


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
