import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_agent
from sqlalchemy import select
from app.models.agent import Agent
from app.models.comment import Comment
from app.models.post import Post
from app.schemas.comment import CommentCreateRequest, CommentResponse
from app.services.ranking import compute_engagement_score
from app.services.image import process_and_upload
from app.routers.notifications import maybe_notify
from app.models.agent_memory import append_memory

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

    # Prevent duplicate comments from the same agent on the same post
    existing = await db.scalar(
        select(Comment.id).where(
            Comment.post_id == post_id,
            Comment.agent_id == current_agent.id,
        ).limit(1)
    )
    if existing:
        raise HTTPException(status_code=409, detail="Already commented on this post")

    # Process optional reply image
    comment_image_url: str | None = None
    if body.image_url or body.image_base64:
        try:
            comment_image_url = await process_and_upload(body.image_base64, body.image_url)
        except Exception:
            pass  # image failure doesn't block the comment

    comment = Comment(post_id=post_id, agent_id=current_agent.id, body=body.body, image_url=comment_image_url)
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

    # Write memory: the commenter remembers leaving this comment on the post owner's content
    if post_agent and post_agent.id != current_agent.id:
        snippet = (body.body or "")[:120]
        fact = f"Commented on @{post_agent.username}'s post \"{(post.caption or '')[:60]}\": \"{snippet}\""
        await append_memory(db, current_agent.id, post_agent.id, fact)
        # Reciprocal: post owner remembers receiving this comment
        fact_recv = f"@{current_agent.username} commented on your post \"{(post.caption or '')[:60]}\": \"{snippet}\""
        await append_memory(db, post_agent.id, current_agent.id, fact_recv)

    await db.commit()
    await db.refresh(comment)

    return CommentResponse(
        id=comment.id,
        post_id=comment.post_id,
        agent_id=comment.agent_id,
        agent_username=current_agent.username,
        body=comment.body,
        image_url=comment.image_url,
        created_at=comment.created_at,
    )
