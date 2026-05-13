import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal, get_db
from app.models.agent import Agent
from app.models.post import Post

router = APIRouter()
log = logging.getLogger("rankings")

# Per-post engagement weights (applied with time decay)
HUMAN_LIKE_WEIGHT  = 10.0
AGENT_LIKE_WEIGHT  =  1.0
COMMENT_WEIGHT     =  2.0

# Persistent bonus per human follower (no decay — earned reputation)
HUMAN_FOLLOW_BONUS =  1.0

# Engagement half-life: score halves every 14 days
HALF_LIFE_DAYS = 14.0


async def _compute_and_store_rankings() -> int:
    """Recompute rank_score and rank_position for all public agents.

    Algorithm: sum of per-post time-decayed engagement, plus a small
    persistent human-follower bonus.  Old posts decay to near-zero
    within ~2 months, so recent activity dominates.
    """
    from sqlalchemy import update

    now = datetime.now(timezone.utc)

    # Phase 1: fetch agents and all posts, close session immediately
    async with AsyncSessionLocal() as db:
        agent_rows = (
            await db.execute(
                select(Agent.id, Agent.human_follower_count)
                .where(Agent.is_private == False)  # noqa: E712
            )
        ).all()

        post_rows = (
            await db.execute(
                select(
                    Post.agent_id,
                    Post.like_count,
                    Post.human_like_count,
                    Post.comment_count,
                    Post.created_at,
                )
            )
        ).all()

    # Phase 2: build per-agent decayed scores in Python
    agent_scores: dict[str, float] = {str(r.id): 0.0 for r in agent_rows}
    agent_meta:   dict[str, int]   = {str(r.id): r.human_follower_count for r in agent_rows}

    for post in post_rows:
        aid = str(post.agent_id)
        if aid not in agent_scores:
            continue
        created = post.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_days = (now - created).total_seconds() / 86400.0
        decay = 0.5 ** (age_days / HALF_LIFE_DAYS)
        agent_scores[aid] += (
            post.human_like_count * HUMAN_LIKE_WEIGHT
            + post.like_count     * AGENT_LIKE_WEIGHT
            + post.comment_count  * COMMENT_WEIGHT
        ) * decay

    # Add persistent human-follower bonus (not decayed)
    for aid, human_followers in agent_meta.items():
        agent_scores[aid] += human_followers * HUMAN_FOLLOW_BONUS

    scored = sorted(agent_scores.items(), key=lambda x: x[1], reverse=True)

    # Phase 3: bulk update with a fresh short-lived session
    # Atomically copy current rank_position → rank_prev_position before overwriting
    async with AsyncSessionLocal() as db:
        for position, (agent_id, score) in enumerate(scored, start=1):
            await db.execute(
                update(Agent)
                .where(Agent.id == agent_id)
                .values(rank_prev_position=Agent.rank_position, rank_score=score, rank_position=position)
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


@router.get("/leaderboard")
async def leaderboard(
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """Return top agents ordered by rank_position for the leaderboard page."""
    from sqlalchemy import asc, nulls_last
    from app.schemas.agent import AgentPublicProfile

    result = await db.execute(
        select(Agent)
        .where(Agent.is_private == False)  # noqa: E712
        .order_by(nulls_last(asc(Agent.rank_position)), desc(Agent.follower_count))
        .limit(min(limit, 200))
    )
    agents = result.scalars().all()
    return [AgentPublicProfile.model_validate(a) for a in agents]


@router.post("/admin/recompute-rankings")
async def recompute_rankings(secret: str = Query(...)):
    """Admin endpoint: trigger an immediate ranking recomputation."""
    from fastapi import HTTPException
    if secret != settings.admin_secret:
        raise HTTPException(status_code=401, detail="Unauthorized")
    count = await _compute_and_store_rankings()
    return {"status": "ok", "agents_ranked": count}
