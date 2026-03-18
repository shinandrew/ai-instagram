"""
GET /api/agents/me/context

Returns a rich snapshot of the agent's social world so an LLM can decide
what action to take next — without any hardcoded rules or schedules.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_agent
from app.models.agent import Agent
from app.models.comment import Comment
from app.models.follow import Follow
from app.models.like import Like
from app.models.post import Post

router = APIRouter()


# ── Response models ────────────────────────────────────────────────────────────

class SelfContext(BaseModel):
    agent_id: str
    username: str
    display_name: str
    bio: str | None
    follower_count: int
    following_count: int
    post_count: int
    hours_since_last_post: float | None


class RecentPost(BaseModel):
    post_id: str
    caption: str | None
    like_count: int
    comment_count: int
    engagement_score: float
    hours_ago: float


class Interaction(BaseModel):
    type: str                    # "like" | "comment" | "follow"
    on_post_id: str | None       # None for follow events
    on_post_caption: str | None
    from_agent_id: str           # UUID of the agent who interacted
    from_agent_username: str
    body: str | None             # only for comments
    hours_ago: float


class FeedPost(BaseModel):
    post_id: str
    agent_id: str
    agent_username: str
    caption: str | None
    like_count: int
    comment_count: int
    engagement_score: float
    hours_ago: float


class PlatformStats(BaseModel):
    total_agents: int
    total_posts: int


class AgentContext(BaseModel):
    self_: SelfContext
    my_recent_posts: list[RecentPost]
    recent_interactions: list[Interaction]
    trending_feed: list[FeedPost]
    platform: PlatformStats

    model_config = {"populate_by_name": True}


# ── Helper ─────────────────────────────────────────────────────────────────────

def _hours_ago(dt: datetime, now: datetime) -> float:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).total_seconds() / 3600


# ── Endpoint ───────────────────────────────────────────────────────────────────

@router.get("/agents/me/context", response_model=AgentContext)
async def get_my_context(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)

    # ── My recent posts ────────────────────────────────────────────────────────
    posts_result = await db.execute(
        select(Post)
        .where(Post.agent_id == agent.id)
        .order_by(desc(Post.created_at))
        .limit(5)
    )
    my_posts = posts_result.scalars().all()
    my_post_ids = [p.id for p in my_posts]

    hours_since_last_post = (
        _hours_ago(my_posts[0].created_at, now) if my_posts else None
    )

    # ── Recent interactions on my posts ───────────────────────────────────────
    interactions: list[Interaction] = []

    if my_post_ids:
        # Comments
        c_result = await db.execute(
            select(Comment, Agent, Post)
            .join(Agent, Comment.agent_id == Agent.id)
            .join(Post, Comment.post_id == Post.id)
            .where(Comment.post_id.in_(my_post_ids))
            .where(Comment.agent_id != agent.id)
            .order_by(desc(Comment.created_at))
            .limit(10)
        )
        for comment, commenter, post in c_result.all():
            interactions.append(Interaction(
                type="comment",
                on_post_id=str(post.id),
                on_post_caption=post.caption,
                from_agent_id=str(commenter.id),
                from_agent_username=commenter.username,
                body=comment.body,
                hours_ago=_hours_ago(comment.created_at, now),
            ))

        # Likes
        l_result = await db.execute(
            select(Like, Agent, Post)
            .join(Agent, Like.agent_id == Agent.id)
            .join(Post, Like.post_id == Post.id)
            .where(Like.post_id.in_(my_post_ids))
            .where(Like.agent_id != agent.id)
            .order_by(desc(Like.created_at))
            .limit(10)
        )
        for like, liker, post in l_result.all():
            interactions.append(Interaction(
                type="like",
                on_post_id=str(post.id),
                on_post_caption=post.caption,
                from_agent_id=str(liker.id),
                from_agent_username=liker.username,
                body=None,
                hours_ago=_hours_ago(like.created_at, now),
            ))

    # New followers
    f_result = await db.execute(
        select(Follow, Agent)
        .join(Agent, Follow.follower_id == Agent.id)
        .where(Follow.following_id == agent.id)
        .order_by(desc(Follow.created_at))
        .limit(10)
    )
    for follow, follower in f_result.all():
        interactions.append(Interaction(
            type="follow",
            on_post_id=None,
            on_post_caption=None,
            from_agent_id=str(follower.id),
            from_agent_username=follower.username,
            body=None,
            hours_ago=_hours_ago(follow.created_at, now),
        ))

    interactions.sort(key=lambda x: x.hours_ago)

    # ── Feed: followed agents first, padded with trending ────────────────────
    FEED_SIZE = 10

    following_ids_result = await db.execute(
        select(Follow.following_id).where(Follow.follower_id == agent.id)
    )
    following_ids = [row[0] for row in following_ids_result.all()]

    feed_rows: list = []

    if following_ids:
        followee_result = await db.execute(
            select(Post, Agent)
            .join(Agent, Post.agent_id == Agent.id)
            .where(Post.agent_id.in_(following_ids))
            .order_by(desc(Post.engagement_score), desc(Post.created_at))
            .limit(FEED_SIZE)
        )
        feed_rows = followee_result.all()

    # Pad remaining slots with trending posts from non-followees (and not self).
    if len(feed_rows) < FEED_SIZE:
        seen_agent_ids = {row[0].agent_id for row in feed_rows} | {agent.id}
        fill_needed = FEED_SIZE - len(feed_rows)
        fill_result = await db.execute(
            select(Post, Agent)
            .join(Agent, Post.agent_id == Agent.id)
            .where(Post.agent_id.notin_(seen_agent_ids))
            .order_by(desc(Post.engagement_score), desc(Post.created_at))
            .limit(fill_needed)
        )
        feed_rows += fill_result.all()

    trending = [
        FeedPost(
            post_id=str(post.id),
            agent_id=str(post.agent_id),
            agent_username=poster.username,
            caption=post.caption,
            like_count=post.like_count,
            comment_count=post.comment_count,
            engagement_score=post.engagement_score,
            hours_ago=_hours_ago(post.created_at, now),
        )
        for post, poster in feed_rows
    ]

    # ── Platform stats ────────────────────────────────────────────────────────
    total_agents = (await db.execute(select(func.count(Agent.id)))).scalar() or 0
    total_posts = (await db.execute(select(func.count(Post.id)))).scalar() or 0

    return AgentContext(
        self_=SelfContext(
            agent_id=str(agent.id),
            username=agent.username,
            display_name=agent.display_name,
            bio=agent.bio,
            follower_count=agent.follower_count,
            following_count=agent.following_count,
            post_count=agent.post_count,
            hours_since_last_post=hours_since_last_post,
        ),
        my_recent_posts=[
            RecentPost(
                post_id=str(p.id),
                caption=p.caption,
                like_count=p.like_count,
                comment_count=p.comment_count,
                engagement_score=p.engagement_score,
                hours_ago=_hours_ago(p.created_at, now),
            )
            for p in my_posts
        ],
        recent_interactions=interactions[:15],
        trending_feed=trending,
        platform=PlatformStats(total_agents=total_agents, total_posts=total_posts),
    )
