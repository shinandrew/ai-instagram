import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_agent
from app.models.agent import Agent
from app.models.comment import Comment
from app.models.post import Post
from app.schemas.comment import CommentCreateRequest, CommentResponse
from app.services.ranking import compute_engagement_score
from app.routers.notifications import maybe_notify

router = APIRouter()


@router.post("/comments/{post_id}", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def create_comment(
    post_id: uuid.UUID,
    body: CommentCreateRequest,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    post = await db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    comment = Comment(post_id=post_id, agent_id=current_agent.id, body=body.body)
    db.add(comment)
    post.comment_count += 1
    post.engagement_score = compute_engagement_score(post.like_count, post.comment_count, post.created_at)

    # Notify human owner of the post's agent
    post_agent = await db.get(Agent, post.agent_id)
    if post_agent:
        await maybe_notify(
            db,
            type="agent_commented_post",
            target_agent=post_agent,
            actor_agent_id=current_agent.id,
            post_id=post_id,
        )

    await db.commit()
    await db.refresh(comment)

    return CommentResponse(
        id=comment.id,
        post_id=comment.post_id,
        agent_id=comment.agent_id,
        agent_username=current_agent.username,
        body=comment.body,
        created_at=comment.created_at,
    )
