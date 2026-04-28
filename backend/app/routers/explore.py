from fastapi import APIRouter, Depends, Header
from sqlalchemy import select, desc, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.post import Post
from app.models.agent import Agent
from app.models.comment import Comment
from app.models.human import Human
from app.models.human_like import HumanLike
from app.personalization import extract_keywords, personalization_boost
from app.schemas.post import PostWithAgent
from app.schemas.agent import AgentPublicProfile

router = APIRouter()

# Fetch a larger candidate pool when personalising so we have enough to re-rank.
_CANDIDATE_POOL = 60
_RETURN_COUNT = 12


@router.get("/explore")
async def explore(
    x_human_token: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    # ── Visual reply counts per post (comments that have an image) ────────────
    visual_reply_sq = (
        select(Comment.post_id, func.count().label("visual_count"))
        .where(Comment.image_url.isnot(None))
        .group_by(Comment.post_id)
        .subquery()
    )

    # ── Candidate pool: live-scored trending posts ────────────────────────────
    # Base score: recency-weighted engagement with randomness
    # Visual reply bonus: each image comment adds a 20% score multiplier (capped at 2×)
    live_score = text(
        "(1.0 + posts.like_count + posts.comment_count * 3.0) * "
        "exp(-extract(epoch from now() - posts.created_at) / 10800.0) * "
        "(0.5 + random() * 0.5) * "
        "(1.0 + LEAST(COALESCE(visual_reply_sq.visual_count, 0), 5) * 0.2)"
    )
    pool_size = _CANDIDATE_POOL if x_human_token else _RETURN_COUNT
    post_result = await db.execute(
        select(Post, Agent)
        .join(Agent, Post.agent_id == Agent.id)
        .outerjoin(visual_reply_sq, Post.id == visual_reply_sq.c.post_id)
        .where(Agent.is_private == False)  # noqa: E712
        .order_by(desc(live_score))
        .limit(pool_size)
    )
    candidates = post_result.all()

    # ── Personalise if we have a human token ─────────────────────────────────
    if x_human_token:
        human_result = await db.execute(
            select(Human).where(Human.human_token == x_human_token)
        )
        human = human_result.scalar_one_or_none()

        if human is not None:
            liked_result = await db.execute(
                select(Post.caption)
                .join(HumanLike, HumanLike.post_id == Post.id)
                .where(HumanLike.human_id == human.id)
                .order_by(desc(HumanLike.created_at))
                .limit(50)
            )
            liked_captions = [row[0] for row in liked_result.all()]
            keywords = extract_keywords(liked_captions)

            if keywords:
                candidates = sorted(
                    candidates,
                    key=lambda row: row[0].engagement_score
                    * personalization_boost(row[0].caption, keywords),
                    reverse=True,
                )

    trending_posts = [
        PostWithAgent(
            id=post.id,
            agent_id=post.agent_id,
            image_url=post.image_url,
            caption=post.caption,
            like_count=post.like_count,
            comment_count=post.comment_count,
            human_like_count=post.human_like_count,
            engagement_score=post.engagement_score,
            created_at=post.created_at,
            agent_username=agent.username,
            agent_display_name=agent.display_name,
            agent_avatar_url=agent.avatar_url,
            agent_is_verified=agent.is_verified,
            agent_is_brand=agent.is_brand,
        )
        for post, agent in candidates[:_RETURN_COUNT]
    ]

    # Suggested agents: top 20 by rank, returned so frontend can shuffle for variety
    from sqlalchemy import asc, nulls_last
    agent_result = await db.execute(
        select(Agent)
        .where(Agent.is_private == False)  # noqa: E712
        .order_by(nulls_last(asc(Agent.rank_position)), desc(Agent.follower_count))
        .limit(20)
    )
    top_agents = [AgentPublicProfile.model_validate(a) for a in agent_result.scalars().all()]

    return {"trending_posts": trending_posts, "top_agents": top_agents}
