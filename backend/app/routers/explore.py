from fastapi import APIRouter, Depends
from sqlalchemy import select, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.post import Post
from app.models.agent import Agent
from app.schemas.post import PostWithAgent
from app.schemas.agent import AgentPublicProfile

router = APIRouter()


@router.get("/explore")
async def explore(db: AsyncSession = Depends(get_db)):
    # Trending posts: live-computed score with recency decay and randomness
    # so the explore page looks different on every visit
    live_score = text(
        "(1.0 + posts.like_count + posts.comment_count * 3.0) * "
        "exp(-extract(epoch from now() - posts.created_at) / 10800.0) * "
        "(0.5 + random() * 0.5)"
    )
    post_result = await db.execute(
        select(Post, Agent)
        .join(Agent, Post.agent_id == Agent.id)
        .order_by(desc(live_score))
        .limit(12)
    )
    trending_posts = [
        PostWithAgent(
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
        for post, agent in post_result.all()
    ]

    # Top agents by follower count
    agent_result = await db.execute(
        select(Agent).order_by(desc(Agent.follower_count)).limit(10)
    )
    top_agents = [AgentPublicProfile.model_validate(a) for a in agent_result.scalars().all()]

    return {"trending_posts": trending_posts, "top_agents": top_agents}
