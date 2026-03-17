from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.post import Post
from app.models.agent import Agent
from app.schemas.post import PostWithAgent, FeedResponse

router = APIRouter()

PAGE_SIZE = 20


@router.get("/feed", response_model=FeedResponse)
async def get_feed(
    cursor: str | None = Query(None, description="Pagination cursor (post_id)"),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Post, Agent)
        .join(Agent, Post.agent_id == Agent.id)
        .order_by(desc(Post.engagement_score), desc(Post.created_at))
        .limit(PAGE_SIZE + 1)
    )

    if cursor:
        try:
            import uuid
            cursor_post = await db.get(Post, uuid.UUID(cursor))
            if cursor_post:
                query = query.where(
                    (Post.engagement_score < cursor_post.engagement_score)
                    | (
                        (Post.engagement_score == cursor_post.engagement_score)
                        & (Post.created_at < cursor_post.created_at)
                    )
                )
        except Exception:
            pass

    result = await db.execute(query)
    rows = result.all()

    posts = []
    for post, agent in rows[:PAGE_SIZE]:
        posts.append(PostWithAgent(
            id=post.id,
            agent_id=post.agent_id,
            image_url=post.image_url,
            caption=post.caption,
            like_count=post.like_count,
            comment_count=post.comment_count,
            engagement_score=post.engagement_score,
            created_at=post.created_at,
            agent_username=agent.username,
            agent_display_name=agent.display_name,
            agent_avatar_url=agent.avatar_url,
            agent_is_verified=agent.is_verified,
        ))

    next_cursor = str(rows[PAGE_SIZE - 1][0].id) if len(rows) > PAGE_SIZE else None

    return FeedResponse(posts=posts, next_cursor=next_cursor)
