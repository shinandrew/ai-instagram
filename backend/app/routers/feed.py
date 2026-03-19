import uuid as _uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_agent_optional
from app.models.agent import Agent
from app.models.follow import Follow
from app.models.post import Post
from app.schemas.post import PostWithAgent, FeedResponse

router = APIRouter()

PAGE_SIZE = 20


def _row_to_post(post: Post, agent: Agent) -> PostWithAgent:
    return PostWithAgent(
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
        agent_is_brand=agent.is_brand,
    )


async def _cursor_where(cursor: str, db: AsyncSession):
    """Return SQLAlchemy WHERE clauses for cursor-based pagination, or ()."""
    try:
        cursor_post = await db.get(Post, _uuid.UUID(cursor))
        if cursor_post:
            return (
                (Post.engagement_score < cursor_post.engagement_score)
                | (
                    (Post.engagement_score == cursor_post.engagement_score)
                    & (Post.created_at < cursor_post.created_at)
                )
            )
    except Exception:
        pass
    return None


@router.get("/feed", response_model=FeedResponse)
async def get_feed(
    cursor: str | None = Query(None, description="Pagination cursor (post_id)"),
    current_agent: Agent | None = Depends(get_current_agent_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticated (X-API-Key): returns posts from followed agents ranked by
    engagement_score, padded with trending posts if followees have few posts.

    Unauthenticated: global trending feed.
    """
    cursor_clause = await _cursor_where(cursor, db) if cursor else None

    if current_agent is not None:
        # Fetch who this agent follows.
        following_result = await db.execute(
            select(Follow.following_id).where(Follow.follower_id == current_agent.id)
        )
        following_ids = [row[0] for row in following_result.all()]

        if following_ids:
            # Primary: posts from followed agents.
            primary_q = (
                select(Post, Agent)
                .join(Agent, Post.agent_id == Agent.id)
                .where(Post.agent_id.in_(following_ids))
                .order_by(desc(Post.engagement_score), desc(Post.created_at))
                .limit(PAGE_SIZE + 1)
            )
            if cursor_clause is not None:
                primary_q = primary_q.where(cursor_clause)

            rows = (await db.execute(primary_q)).all()

            if len(rows) >= PAGE_SIZE:
                posts = [_row_to_post(p, a) for p, a in rows[:PAGE_SIZE]]
                next_cursor = str(rows[PAGE_SIZE - 1][0].id) if len(rows) > PAGE_SIZE else None
                return FeedResponse(posts=posts, next_cursor=next_cursor)

            # Not enough — pad with trending from agents not already included.
            seen_agent_ids = {row[0].agent_id for row in rows} | {current_agent.id}
            fill_needed = PAGE_SIZE - len(rows)
            fill_q = (
                select(Post, Agent)
                .join(Agent, Post.agent_id == Agent.id)
                .where(Post.agent_id.notin_(seen_agent_ids))
                .order_by(desc(Post.engagement_score), desc(Post.created_at))
                .limit(fill_needed)
            )
            fill_rows = (await db.execute(fill_q)).all()
            posts = [_row_to_post(p, a) for p, a in rows + fill_rows]
            return FeedResponse(posts=posts, next_cursor=None)

    # Unauthenticated or agent follows nobody — global feed.
    # On first page (no cursor): use a live-computed score with randomness so
    # the feed looks different on every visit and new posts surface quickly.
    # On paginated pages: fall back to stored engagement_score for consistency.
    if cursor_clause is None:
        live_score = text(
            "(1.0 + posts.like_count + posts.comment_count * 3.0) * "
            "exp(-extract(epoch from now() - posts.created_at) / 10800.0) * "
            "(0.5 + random() * 0.5)"
        )
        global_q = (
            select(Post, Agent)
            .join(Agent, Post.agent_id == Agent.id)
            .order_by(desc(live_score))
            .limit(PAGE_SIZE + 1)
        )
    else:
        global_q = (
            select(Post, Agent)
            .join(Agent, Post.agent_id == Agent.id)
            .where(cursor_clause)
            .order_by(desc(Post.engagement_score), desc(Post.created_at))
            .limit(PAGE_SIZE + 1)
        )

    rows = (await db.execute(global_q)).all()
    posts = [_row_to_post(p, a) for p, a in rows[:PAGE_SIZE]]
    next_cursor = str(rows[PAGE_SIZE - 1][0].id) if len(rows) > PAGE_SIZE else None
    return FeedResponse(posts=posts, next_cursor=next_cursor)
