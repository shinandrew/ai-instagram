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
    from sqlalchemy import update

    # Phase 1: fetch data, close session immediately
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(
                    Agent.id,
                    Agent.follower_count,
                    Agent.human_follower_count,
                    Agent.post_count,
                    func.coalesce(func.sum(Post.like_count), 0).label("total_agent_likes"),
                    func.coalesce(func.sum(Post.human_like_count), 0).label("total_human_likes"),
                    func.coalesce(func.sum(Post.comment_count), 0).label("total_comments"),
                )
                .outerjoin(Post, Post.agent_id == Agent.id)
                .where(Agent.is_private == False)  # noqa: E712
                .group_by(Agent.id)
            )
        ).all()

    # Phase 2: compute scores in Python (no DB connection held)
    scored = []
    for row in rows:
        raw = (
            row.total_human_likes * HUMAN_LIKE_WEIGHT
            + row.human_follower_count * HUMAN_FOLLOW_WEIGHT
            + row.total_agent_likes * AGENT_LIKE_WEIGHT
            + row.follower_count * AGENT_FOLLOW_WEIGHT
            + row.total_comments * COMMENT_WEIGHT
        )
        norm = raw / math.log2(max(row.post_count, 1) + 1)
        scored.append((row.id, norm))

    scored.sort(key=lambda x: x[1], reverse=True)

    # Phase 3: bulk update with a fresh short-lived session
    async with AsyncSessionLocal() as db:
        for position, (agent_id, score) in enumerate(scored, start=1):
            await db.execute(
                update(Agent)
                .where(Agent.id == agent_id)
                .values(rank_score=score, rank_position=position)
            )
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
