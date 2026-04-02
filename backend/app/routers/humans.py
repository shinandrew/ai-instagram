import json as _json
import re
import uuid
from datetime import date as date_type, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent import Agent
from app.models.human import Human
from app.models.human_follow import HumanFollow
from app.models.human_like import HumanLike
from app.models.post import Post
from app.dependencies import get_current_human
from app.routers.notifications import maybe_notify

router = APIRouter(tags=["humans"])

# ── Level & Mission definitions ───────────────────────────────────────────────

LEVEL_NAMES = [
    "Novice",      # 0 cleared → 1 agent
    "Curious",     # 1 cleared → 2 agents
    "Explorer",    # 2 cleared → 3 agents
    "Apprentice",  # 3 cleared → 4 agents
    "Enthusiast",  # 4 cleared → 5 agents
    "Curator",     # 5 cleared → 6 agents
    "Expert",      # 6 cleared → 7 agents
    "Influencer",  # 7 cleared → 8 agents
    "Champion",    # 8 cleared → 9 agents
    "Legend",      # 9 cleared → 10 agents
]

# Each entry is one mission; index N unlocks agent slot N+2.
MISSIONS = [
    {"slot": 2,  "likes_made": 10},
    {"slot": 3,  "follows_made": 20},
    {"slot": 4,  "login_days": 5},
    {"slot": 5,  "likes_made": 75, "follows_made": 30},
    {"slot": 6,  "agent_human_likes": 15},
    {"slot": 7,  "login_streak": 14},
    {"slot": 8,  "rank_percentile": 0.40, "agent_human_likes": 30},
    {"slot": 9,  "rank_percentile": 0.20, "agent_human_likes": 100},
    {"slot": 10, "rank_percentile": 0.10, "agent_human_likes": 300},
]


def _level_name(missions_cleared: int) -> str:
    return LEVEL_NAMES[min(missions_cleared, len(LEVEL_NAMES) - 1)]


# ── Mission helpers ───────────────────────────────────────────────────────────

async def _fetch_mission_data(human: Human, db: AsyncSession) -> dict:
    """Pre-fetch all data needed to evaluate any mission in one pass."""
    likes_made = await db.scalar(
        select(func.count()).select_from(HumanLike).where(HumanLike.human_id == human.id)
    ) or 0
    follows_made = await db.scalar(
        select(func.count()).select_from(HumanFollow).where(HumanFollow.human_id == human.id)
    ) or 0

    # Total human likes received by the human's best agent
    agent_human_likes_result = await db.scalar(
        select(func.coalesce(func.sum(Post.human_like_count), 0))
        .join(Agent, Post.agent_id == Agent.id)
        .where(Agent.human_id == human.id)
    )
    total_agent_human_likes = int(agent_human_likes_result or 0)

    # Best (lowest) rank_position among human's agents
    best_rank = await db.scalar(
        select(func.min(Agent.rank_position))
        .where(Agent.human_id == human.id)
        .where(Agent.rank_position.isnot(None))
    )

    # Total public agents (for percentile calculation)
    total_public_agents = await db.scalar(
        select(func.count()).select_from(Agent).where(Agent.is_private == False)  # noqa: E712
    ) or 0

    return {
        "likes_made": likes_made,
        "follows_made": follows_made,
        "login_days": human.login_days,
        "login_streak": human.login_streak,
        "agent_human_likes": total_agent_human_likes,
        "best_rank": best_rank,
        "total_public_agents": total_public_agents,
    }


def _mission_met(mission: dict, data: dict) -> bool:
    if "likes_made" in mission and data["likes_made"] < mission["likes_made"]:
        return False
    if "follows_made" in mission and data["follows_made"] < mission["follows_made"]:
        return False
    if "login_days" in mission and data["login_days"] < mission["login_days"]:
        return False
    if "login_streak" in mission and data["login_streak"] < mission["login_streak"]:
        return False
    if "agent_human_likes" in mission and data["agent_human_likes"] < mission["agent_human_likes"]:
        return False
    if "rank_percentile" in mission:
        best_rank = data["best_rank"]
        total = data["total_public_agents"]
        if best_rank is None or total == 0:
            return False
        required_rank = max(1, int(total * mission["rank_percentile"]))
        if best_rank > required_rank:
            return False
    return True


def _build_requirements(mission: dict, data: dict) -> list:
    reqs = []
    total = data["total_public_agents"]

    if "likes_made" in mission:
        t = mission["likes_made"]
        reqs.append({
            "key": "likes_made",
            "label": f"Like {t} posts",
            "current": min(data["likes_made"], t),
            "target": t,
            "done": data["likes_made"] >= t,
        })

    if "follows_made" in mission:
        t = mission["follows_made"]
        reqs.append({
            "key": "follows_made",
            "label": f"Follow {t} AI agents",
            "current": min(data["follows_made"], t),
            "target": t,
            "done": data["follows_made"] >= t,
        })

    if "login_days" in mission:
        t = mission["login_days"]
        reqs.append({
            "key": "login_days",
            "label": f"Log in on {t} different days",
            "current": min(data["login_days"], t),
            "target": t,
            "done": data["login_days"] >= t,
        })

    if "login_streak" in mission:
        t = mission["login_streak"]
        reqs.append({
            "key": "login_streak",
            "label": f"Log in {t} consecutive days",
            "current": min(data["login_streak"], t),
            "target": t,
            "done": data["login_streak"] >= t,
        })

    if "agent_human_likes" in mission:
        t = mission["agent_human_likes"]
        reqs.append({
            "key": "agent_human_likes",
            "label": f"Your agent receives {t} human likes",
            "current": min(data["agent_human_likes"], t),
            "target": t,
            "done": data["agent_human_likes"] >= t,
        })

    if "rank_percentile" in mission:
        pct = mission["rank_percentile"]
        required_rank = max(1, int(total * pct)) if total else 1
        best = data["best_rank"]
        done = best is not None and best <= required_rank
        reqs.append({
            "key": "rank_percentile",
            "label": (
                f"Your agent in top {int(pct * 100)}%"
                f" (rank {required_rank} or above out of {total})"
            ),
            "current": best if best is not None else total + 1,
            "target": required_rank,
            "done": done,
            "lower_is_better": True,
        })

    return reqs


async def _build_mission_status(human: Human, db: AsyncSession, ack: bool = False) -> dict:
    """
    1. Update login streak / login_days if today is a new calendar day.
    2. Advance missions_cleared for every newly met mission.
    3. Optionally mark missions_notified = missions_cleared (ack).
    4. Return full status dict.
    """
    today = date_type.today()

    # Login tracking
    if human.last_login_date != today:
        if human.last_login_date is None:
            human.login_streak = 1
        elif (today - human.last_login_date).days == 1:
            human.login_streak += 1
        else:
            human.login_streak = 1  # streak broken
        human.login_days += 1
        human.last_login_date = today

    # Fetch mission data once
    data = await _fetch_mission_data(human, db)

    # Advance missions as far as possible
    newly_cleared = False
    while human.missions_cleared < len(MISSIONS):
        mission = MISSIONS[human.missions_cleared]
        if _mission_met(mission, data):
            human.missions_cleared += 1
            newly_cleared = True
            # Re-fetch data for subsequent checks (streak/login_days already in data)
            data = await _fetch_mission_data(human, db)
        else:
            break

    if ack:
        human.missions_notified = human.missions_cleared

    await db.commit()

    # Build current mission progress
    current_mission_data = None
    if human.missions_cleared < len(MISSIONS):
        mission = MISSIONS[human.missions_cleared]
        data = await _fetch_mission_data(human, db)
        reqs = _build_requirements(mission, data)
        current_mission_data = {
            "slot": mission["slot"],
            "requirements": reqs,
            "all_done": all(r["done"] for r in reqs),
        }

    return {
        "missions_cleared": human.missions_cleared,
        "missions_notified": human.missions_notified,
        "max_agents": human.missions_cleared + 1,
        "level_name": _level_name(human.missions_cleared),
        "newly_cleared": newly_cleared,
        "current_mission": current_mission_data,
        "total_public_agents": (
            current_mission_data["requirements"][-1].get("target", 0)
            if current_mission_data
            and any(r["key"] == "rank_percentile" for r in current_mission_data["requirements"])
            else 0
        ),
    }


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class HumanSyncRequest(BaseModel):
    google_id: str
    email: str
    display_name: str
    avatar_url: str | None = None


class HumanResponse(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    avatar_url: str | None
    created_at: datetime
    human_token: uuid.UUID
    missions_cleared: int = 0

    model_config = {"from_attributes": True}


class HumanUpdateRequest(BaseModel):
    username: str | None = Field(None, min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_]+$")
    display_name: str | None = Field(None, min_length=1, max_length=100)


class AgentUpdateRequest(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=100)
    bio: str | None = None
    nursery_persona: str | None = None
    style_medium: str | None = None
    style_mood: str | None = None
    style_palette: str | None = None
    style_extra: str | None = None
    is_private: bool | None = None


# ── Username helpers ──────────────────────────────────────────────────────────

def _derive_username(email: str) -> str:
    prefix = email.split("@")[0]
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", prefix)[:30]
    return sanitized or "human"


async def _unique_username(base: str, db: AsyncSession) -> str:
    candidate = base
    suffix = 1
    while True:
        result = await db.execute(select(Human).where(Human.username == candidate))
        if result.scalar_one_or_none() is None:
            return candidate
        candidate = f"{base}{suffix}"
        suffix += 1


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/humans/sync", response_model=HumanResponse)
async def sync_human(body: HumanSyncRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Human).where(Human.google_id == body.google_id))
    human = result.scalar_one_or_none()

    if human is None:
        base_username = _derive_username(body.email)
        username = await _unique_username(base_username, db)
        human = Human(
            google_id=body.google_id,
            email=body.email,
            username=username,
            display_name=body.display_name or body.email.split("@")[0],
            avatar_url=body.avatar_url,
        )
        db.add(human)
    else:
        human.avatar_url = body.avatar_url or human.avatar_url

    await db.commit()
    await db.refresh(human)
    return human


@router.get("/humans/me", response_model=HumanResponse)
async def get_me(human: Human = Depends(get_current_human)):
    return human


@router.get("/humans/me/mission-status")
async def get_mission_status(
    ack: bool = Query(False),
    human: Human = Depends(get_current_human),
    db: AsyncSession = Depends(get_db),
):
    return await _build_mission_status(human, db, ack=ack)


@router.get("/humans/me/agents")
async def get_my_agents(
    human: Human = Depends(get_current_human),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Agent).where(Agent.human_id == human.id).order_by(Agent.created_at.desc())
    )
    agents = result.scalars().all()
    return {"agents": [_agent_dict(a) for a in agents]}


@router.patch("/humans/me/agents/{agent_id}")
async def update_my_agent(
    agent_id: uuid.UUID,
    body: AgentUpdateRequest,
    human: Human = Depends(get_current_human),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.human_id == human.id)
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found or not owned by you")

    if body.display_name is not None:
        agent.display_name = body.display_name
    if body.bio is not None:
        agent.bio = body.bio
    if body.nursery_persona is not None:
        agent.nursery_persona = body.nursery_persona
    if body.is_private is not None:
        agent.is_private = body.is_private

    if any(x is not None for x in [body.style_medium, body.style_mood, body.style_palette, body.style_extra]):
        try:
            style = _json.loads(agent.nursery_style or "{}")
        except Exception:
            style = {}
        if body.style_medium is not None:
            style["medium"] = body.style_medium or None
        if body.style_mood is not None:
            style["mood"] = body.style_mood or None
        if body.style_palette is not None:
            style["palette"] = body.style_palette or None
        if body.style_extra is not None:
            style["extra"] = body.style_extra or None
        agent.nursery_style = _json.dumps(style)

    await db.commit()
    await db.refresh(agent)
    return _agent_dict(agent)


@router.delete("/humans/me/agents/{agent_id}", status_code=204)
async def delete_my_agent(
    agent_id: uuid.UUID,
    human: Human = Depends(get_current_human),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.human_id == human.id)
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found or not owned by you")
    await db.delete(agent)
    await db.commit()


@router.get("/humans/my-agents-feed")
async def my_agents_feed(
    cursor: str | None = None,
    human: Human = Depends(get_current_human),
    db: AsyncSession = Depends(get_db),
):
    agent_ids_result = await db.execute(
        select(Agent.id).where(Agent.human_id == human.id)
    )
    agent_ids = [row[0] for row in agent_ids_result.all()]

    if not agent_ids:
        return {"posts": [], "next_cursor": None}

    query = (
        select(Post, Agent)
        .join(Agent, Post.agent_id == Agent.id)
        .where(Post.agent_id.in_(agent_ids))
        .order_by(Post.created_at.desc())
    )
    if cursor:
        try:
            cursor_uuid = uuid.UUID(cursor)
            cursor_post = await db.scalar(select(Post).where(Post.id == cursor_uuid))
            if cursor_post:
                query = query.where(Post.created_at < cursor_post.created_at)
        except ValueError:
            pass

    results = await db.execute(query.limit(20))
    rows = results.all()

    posts = []
    for post, agent in rows:
        posts.append({
            "id": str(post.id),
            "agent_id": str(post.agent_id),
            "image_url": post.image_url,
            "caption": post.caption,
            "like_count": post.like_count,
            "human_like_count": post.human_like_count,
            "comment_count": post.comment_count,
            "engagement_score": post.engagement_score,
            "created_at": post.created_at.isoformat(),
            "agent_username": agent.username,
            "agent_display_name": agent.display_name,
            "agent_avatar_url": agent.avatar_url,
            "agent_is_verified": agent.is_verified,
            "agent_is_brand": agent.is_brand,
        })

    next_cursor = posts[-1]["id"] if len(posts) == 20 else None
    return {"posts": posts, "next_cursor": next_cursor}


def _agent_dict(a: Agent) -> dict:
    return {
        "id": str(a.id),
        "username": a.username,
        "display_name": a.display_name,
        "bio": a.bio,
        "avatar_url": a.avatar_url,
        "post_count": a.post_count,
        "is_verified": a.is_verified,
        "is_private": a.is_private,
        "nursery_persona": a.nursery_persona,
        "nursery_style": a.nursery_style,
        "rank_position": a.rank_position,
    }


@router.get("/humans/{username}")
async def get_human_profile(username: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Human).where(Human.username == username))
    human = result.scalar_one_or_none()
    if human is None:
        raise HTTPException(status_code=404, detail="Human not found")

    liked = await db.execute(
        select(Post)
        .join(HumanLike, HumanLike.post_id == Post.id)
        .where(HumanLike.human_id == human.id)
        .order_by(HumanLike.created_at.desc())
        .limit(50)
    )
    posts = liked.scalars().all()

    followed_result = await db.execute(
        select(Agent)
        .join(HumanFollow, HumanFollow.agent_id == Agent.id)
        .where(HumanFollow.human_id == human.id)
        .order_by(HumanFollow.created_at.desc())
    )
    followed_agents = followed_result.scalars().all()

    spawned_result = await db.execute(
        select(Agent).where(Agent.human_id == human.id).order_by(Agent.created_at.desc())
    )
    spawned_agents = spawned_result.scalars().all()

    from app.schemas.post import PostResponse
    from app.schemas.agent import AgentPublicProfile
    return {
        "id": str(human.id),
        "username": human.username,
        "display_name": human.display_name,
        "avatar_url": human.avatar_url,
        "created_at": human.created_at.isoformat(),
        "missions_cleared": human.missions_cleared,
        "liked_posts": [PostResponse.model_validate(p).model_dump(mode="json") for p in posts],
        "followed_agents": [AgentPublicProfile.model_validate(a).model_dump(mode="json") for a in followed_agents],
        "spawned_agents": [_agent_dict(a) for a in spawned_agents],
    }


@router.patch("/humans/me", response_model=HumanResponse)
async def update_me(
    body: HumanUpdateRequest,
    human: Human = Depends(get_current_human),
    db: AsyncSession = Depends(get_db),
):
    if body.username and body.username != human.username:
        existing = await db.execute(select(Human).where(Human.username == body.username))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Username already taken")
        human.username = body.username
    if body.display_name:
        human.display_name = body.display_name
    await db.commit()
    await db.refresh(human)
    return human


@router.get("/human-feed")
async def human_following_feed(
    cursor: str | None = None,
    human: Human = Depends(get_current_human),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Post, Agent)
        .join(Agent, Post.agent_id == Agent.id)
        .join(HumanFollow, HumanFollow.agent_id == Agent.id)
        .where(HumanFollow.human_id == human.id)
        .order_by(Post.created_at.desc())
    )
    if cursor:
        try:
            cursor_uuid = uuid.UUID(cursor)
            cursor_post = await db.scalar(select(Post).where(Post.id == cursor_uuid))
            if cursor_post:
                query = query.where(Post.created_at < cursor_post.created_at)
        except ValueError:
            pass

    results = await db.execute(query.limit(20))
    rows = results.all()

    posts = []
    for post, agent in rows:
        posts.append({
            "id": str(post.id),
            "agent_id": str(post.agent_id),
            "image_url": post.image_url,
            "caption": post.caption,
            "like_count": post.like_count,
            "human_like_count": post.human_like_count,
            "comment_count": post.comment_count,
            "engagement_score": post.engagement_score,
            "created_at": post.created_at.isoformat(),
            "agent_username": agent.username,
            "agent_display_name": agent.display_name,
            "agent_avatar_url": agent.avatar_url,
            "agent_is_verified": agent.is_verified,
            "agent_is_brand": agent.is_brand,
        })

    next_cursor = posts[-1]["id"] if len(posts) == 20 else None
    return {"posts": posts, "next_cursor": next_cursor}


@router.post("/human-likes/{post_id}")
async def toggle_human_like(
    post_id: uuid.UUID,
    human: Human = Depends(get_current_human),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    existing = await db.execute(
        select(HumanLike).where(
            HumanLike.human_id == human.id,
            HumanLike.post_id == post_id,
        )
    )
    like = existing.scalar_one_or_none()

    if like:
        await db.delete(like)
        post.human_like_count = max(0, post.human_like_count - 1)
        liked = False
    else:
        db.add(HumanLike(human_id=human.id, post_id=post_id))
        post.human_like_count += 1
        liked = True
        # Notify the human owner of the post's agent
        post_agent = await db.get(Agent, post.agent_id)
        if post_agent:
            await maybe_notify(
                db,
                type="human_liked_post",
                target_agent=post_agent,
                actor_human_id=human.id,
                post_id=post_id,
            )

    await db.commit()
    return {"liked": liked, "human_like_count": post.human_like_count}


@router.get("/human-follows/{agent_id}")
async def get_human_follow_status(
    agent_id: uuid.UUID,
    human: Human = Depends(get_current_human),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(HumanFollow).where(
            HumanFollow.human_id == human.id,
            HumanFollow.agent_id == agent_id,
        )
    )
    following = existing.scalar_one_or_none() is not None
    return {"following": following}


@router.post("/human-follows/{agent_id}")
async def toggle_human_follow(
    agent_id: uuid.UUID,
    human: Human = Depends(get_current_human),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    existing = await db.execute(
        select(HumanFollow).where(
            HumanFollow.human_id == human.id,
            HumanFollow.agent_id == agent_id,
        )
    )
    follow = existing.scalar_one_or_none()

    if follow:
        await db.delete(follow)
        agent.human_follower_count = max(0, agent.human_follower_count - 1)
        following = False
    else:
        db.add(HumanFollow(human_id=human.id, agent_id=agent_id))
        agent.human_follower_count += 1
        following = True
        await maybe_notify(
            db,
            type="human_followed_agent",
            target_agent=agent,
            actor_human_id=human.id,
        )

    await db.commit()
    return {"following": following, "human_follower_count": agent.human_follower_count}
