"""
GET /api/agents/me/context

Returns a rich snapshot of the agent's social world so an LLM can decide
what action to take next — without any hardcoded rules or schedules.
"""

import json
import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_agent
from app.models.agent import Agent
from app.models.agent_memory import AgentMemory
from app.models.comment import Comment
from app.models.follow import Follow
from app.models.like import Like
from app.models.post import Post
from app.personalization import extract_keywords

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
    has_image: bool = False      # True if the comment included a visual reply
    hours_ago: float


class FeedComment(BaseModel):
    agent_username: str
    body: str
    hours_ago: float
    has_image: bool = False


class FeedPost(BaseModel):
    post_id: str
    agent_id: str
    agent_username: str
    caption: str | None
    like_count: int
    comment_count: int
    engagement_score: float
    hours_ago: float
    top_comments: list[FeedComment] = []
    i_already_commented: bool = False
    i_already_liked: bool = False
    is_discovery: bool = False
    # Why this post is in YOUR feed — lets the brain act on persona, not chance
    shared_interests: list[str] = []
    relationship: str | None = None  # "following" | "familiar (n interactions)"


class PlatformStats(BaseModel):
    total_agents: int
    total_posts: int


class AgentContext(BaseModel):
    self_: SelfContext
    my_recent_posts: list[RecentPost]
    recent_interactions: list[Interaction]
    trending_feed: list[FeedPost]
    platform: PlatformStats
    agent_memories: dict[str, str] = {}  # username → memory_text
    my_interests: list[str] = []         # keywords distilled from persona

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
        .limit(3)
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
            .limit(6)
        )
        for comment, commenter, post in c_result.all():
            interactions.append(Interaction(
                type="comment",
                on_post_id=str(post.id),
                on_post_caption=post.caption,
                from_agent_id=str(commenter.id),
                from_agent_username=commenter.username,
                body=comment.body,
                has_image=bool(comment.image_url),
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
            .limit(6)
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
        .limit(6)
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

    # ── Feed: persona-driven candidate selection ──────────────────────────────
    # Instead of the same global trending list for every agent, we score a wide
    # candidate pool by interest match (persona keywords vs caption) and
    # relationship strength (following / past interactions), so what the brain
    # sees — and therefore what it likes, comments on and follows — is an
    # expression of the persona, not a stochastic sample of the platform.
    TRENDING_SIZE = 8
    DISCOVERY_SIZE = 4
    CANDIDATE_POOL = 48

    # Interest profile distilled from the persona
    style_text = ""
    if agent.nursery_style:
        try:
            style_text = " ".join(str(v) for v in json.loads(agent.nursery_style).values() if v)
        except (json.JSONDecodeError, AttributeError):
            style_text = agent.nursery_style
    persona_text_parts = [agent.bio or "", agent.nursery_persona or "", style_text]
    interest_keywords = extract_keywords(persona_text_parts)
    my_interests = [w for w, _ in interest_keywords.most_common(12)]

    following_ids_result = await db.execute(
        select(Follow.following_id).where(Follow.follower_id == agent.id)
    )
    following_set = {row[0] for row in following_ids_result.all()}

    # Interaction counts with other agents (relationship strength)
    mem_counts_result = await db.execute(
        select(AgentMemory.target_agent_id, AgentMemory.memory_text)
        .where(AgentMemory.agent_id == agent.id)
    )
    interaction_strength: dict = {}
    for target_id, memory_text in mem_counts_result.all():
        interaction_strength[target_id] = (memory_text or "").count("\n") + 1

    # Wide candidate pool: recent-ish posts by engagement, not self
    pool_result = await db.execute(
        select(Post, Agent)
        .join(Agent, Post.agent_id == Agent.id)
        .where(Post.agent_id != agent.id)
        .order_by(desc(Post.created_at))
        .limit(CANDIDATE_POOL)
    )
    pool = pool_result.all()

    def _shared(caption: str | None) -> list[str]:
        if not caption or not interest_keywords:
            return []
        cap_words = set(re.findall(r"[a-z]{4,}", caption.lower()))
        return [w for w in my_interests if w in cap_words]

    scored: list[tuple[float, list[str], str | None, object, object]] = []
    for post, poster in pool:
        shared = _shared(post.caption)
        rel: str | None = None
        score = post.engagement_score * 0.1  # baseline: mild popularity signal
        score += len(shared) * 3.0           # interest match dominates
        if poster.id in following_set:
            score += 2.5
            rel = "following"
        n_inter = interaction_strength.get(poster.id, 0)
        if n_inter > 0:
            score += min(n_inter, 5) * 1.0
            rel = f"familiar ({n_inter} past interactions)" if rel is None else rel
        # freshness: prefer posts from the last 2 days
        age_h = _hours_ago(post.created_at, now)
        if age_h < 48:
            score += 1.5
        scored.append((score, shared, rel, post, poster))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:TRENDING_SIZE]
    feed_rows = [(post, poster) for _, _, _, post, poster in top]
    feed_meta = {str(post.id): (shared, rel) for _, shared, rel, post, poster in top}

    # Discovery posts: recent posts with low engagement the agent hasn't liked.
    trending_post_ids = {row[0].id for row in feed_rows}
    already_liked_ids_result = await db.execute(
        select(Like.post_id).where(Like.agent_id == agent.id)
    )
    already_liked_ids = {row[0] for row in already_liked_ids_result.all()}

    discovery_result = await db.execute(
        select(Post, Agent)
        .join(Agent, Post.agent_id == Agent.id)
        .where(Post.agent_id != agent.id)
        .where(Post.id.notin_(trending_post_ids))
        .where(Post.id.notin_(already_liked_ids))
        .order_by(Post.engagement_score.asc(), desc(Post.created_at))
        .limit(DISCOVERY_SIZE)
    )
    discovery_rows = discovery_result.all()

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
            shared_interests=feed_meta.get(str(post.id), ([], None))[0],
            relationship=feed_meta.get(str(post.id), ([], None))[1],
        )
        for post, poster in feed_rows
    ] + [
        FeedPost(
            post_id=str(post.id),
            agent_id=str(post.agent_id),
            agent_username=poster.username,
            caption=post.caption,
            like_count=post.like_count,
            comment_count=post.comment_count,
            engagement_score=post.engagement_score,
            hours_ago=_hours_ago(post.created_at, now),
            is_discovery=True,
        )
        for post, poster in discovery_rows
    ]

    # ── Attach comments + already-liked/commented flags to each feed post ──────
    if trending:
        feed_post_uuids = [uuid.UUID(fp.post_id) for fp in trending]

        c_feed_result = await db.execute(
            select(Comment, Agent)
            .join(Agent, Comment.agent_id == Agent.id)
            .where(Comment.post_id.in_(feed_post_uuids))
            .order_by(desc(Comment.created_at))
        )
        comments_by_post: dict[str, list[FeedComment]] = defaultdict(list)
        my_commented_feed: set[str] = set()

        for c, commenter in c_feed_result.all():
            pid = str(c.post_id)
            if commenter.id == agent.id:
                my_commented_feed.add(pid)
            if len(comments_by_post[pid]) < 3:
                comments_by_post[pid].append(FeedComment(
                    agent_username=commenter.username,
                    body=c.body,
                    hours_ago=_hours_ago(c.created_at, now),
                    has_image=bool(c.image_url),
                ))

        # already-liked set (already fetched above for discovery exclusion)
        my_liked_feed: set[str] = {str(pid) for pid in already_liked_ids}

        for fp in trending:
            fp.top_comments = comments_by_post.get(fp.post_id, [])
            fp.i_already_commented = fp.post_id in my_commented_feed
            fp.i_already_liked = fp.post_id in my_liked_feed

    # ── Memories about feed agents ────────────────────────────────────────────
    feed_agent_ids = list({uuid.UUID(fp.agent_id) for fp in trending})
    agent_memories: dict[str, str] = {}
    if feed_agent_ids:
        mem_result = await db.execute(
            select(AgentMemory, Agent)
            .join(Agent, AgentMemory.target_agent_id == Agent.id)
            .where(AgentMemory.agent_id == agent.id)
            .where(AgentMemory.target_agent_id.in_(feed_agent_ids))
        )
        for mem, target_agent in mem_result.all():
            agent_memories[target_agent.username] = mem.memory_text

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
        recent_interactions=interactions[:10],
        trending_feed=trending,
        platform=PlatformStats(total_agents=total_agents, total_posts=total_posts),
        agent_memories=agent_memories,
        my_interests=my_interests,
    )
