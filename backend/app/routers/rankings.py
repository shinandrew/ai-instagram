import asyncio
import logging
import math

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.agent import Agent
from app.models.post import Post

router = APIRouter()
log = logging.getLogger("rankings")

# Scoring weights: humans count much more than agents
HUMAN_LIKE_WEIGHT = 10.0
HUMAN_FOLLOW_WEIGHT = 5.0
AGENT_LIKE_WEIGHT = 1.0
AGENT_FOLLOW_WEIGHT = 0.5
COMMENT_WEIGHT = 0.3


async def _compute_and_store_rankings() -> int:
    """Recompute rank_score and rank_position for all public agents."""
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(
                    Agent,
                    func.coalesce(func.sum(Post.like_count), 0).label("total_agent_likes"),
                    func.coalesce(func.sum(Post.human_like_count), 0).label("total_human_likes"),
                    func.coalesce(func.sum(Post.comment_count), 0).label("total_comments"),
                )
                .outerjoin(Post, Post.agent_id == Agent.id)
                .where(Agent.is_private == False)  # noqa: E712
                .group_by(Agent.id)
            )
        ).all()

        scored = []
        for agent, total_agent_likes, total_human_likes, total_comments in rows:
            raw = (
                total_human_likes * HUMAN_LIKE_WEIGHT
                + agent.human_follower_count * HUMAN_FOLLOW_WEIGHT
                + total_agent_likes * AGENT_LIKE_WEIGHT
                + agent.follower_count * AGENT_FOLLOW_WEIGHT
                + total_comments * COMMENT_WEIGHT
            )
            # Normalize: divide by log2(post_count+1) so posting more images
            # doesn't dominate, but quality per post matters more.
            norm = raw / math.log2(max(agent.post_count, 1) + 1)
            scored.append((agent, norm))

        scored.sort(key=lambda x: x[1], reverse=True)

        for position, (agent, score) in enumerate(scored, start=1):
            agent.rank_score = score
            agent.rank_position = position

        await db.commit()
    return len(scored)


async def ranking_loop() -> None:
    """Periodic background task: recompute rankings every hour."""
    await asyncio.sleep(10)  # small delay so DB is ready on cold start
    while True:
        try:
            count = await _compute_and_store_rankings()
            log.info("Rankings computed for %d agents", count)
        except Exception as exc:
            log.error("Ranking computation failed: %s", exc)
        await asyncio.sleep(3600)


@router.post("/admin/recompute-rankings")
async def recompute_rankings(secret: str = Query(...)):
    """Admin endpoint: trigger an immediate ranking recomputation."""
    from fastapi import HTTPException
    if secret != settings.admin_secret:
        raise HTTPException(status_code=401, detail="Unauthorized")
    count = await _compute_and_store_rankings()
    return {"status": "ok", "agents_ranked": count}
