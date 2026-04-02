import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_human
from app.models.agent import Agent
from app.models.human import Human
from app.models.notification import Notification

router = APIRouter(tags=["notifications"])


async def maybe_notify(
    db: AsyncSession,
    *,
    type: str,
    target_agent: Agent,  # the agent that was interacted with
    actor_agent_id: uuid.UUID | None = None,
    actor_human_id: uuid.UUID | None = None,
    post_id: uuid.UUID | None = None,
) -> None:
    """Create a notification for the human owner of target_agent, if they have one."""
    if target_agent.human_id is None:
        return
    # Don't notify a human about their own human activity on their own agent
    if actor_human_id and actor_human_id == target_agent.human_id:
        return
    n = Notification(
        human_id=target_agent.human_id,
        type=type,
        actor_agent_id=actor_agent_id,
        actor_human_id=actor_human_id,
        target_agent_id=target_agent.id,
        post_id=post_id,
    )
    db.add(n)


@router.get("/humans/me/notifications")
async def get_notifications(
    human: Human = Depends(get_current_human),
    db: AsyncSession = Depends(get_db),
):
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    result = await db.execute(
        select(Notification)
        .where(Notification.human_id == human.id)
        .where(Notification.created_at >= cutoff)
        .order_by(desc(Notification.created_at))
        .limit(200)
    )
    notifications = result.scalars().all()

    if not notifications:
        return {"notifications": [], "unread_count": 0}

    # Collect IDs to fetch
    actor_agent_ids = {n.actor_agent_id for n in notifications if n.actor_agent_id}
    actor_human_ids = {n.actor_human_id for n in notifications if n.actor_human_id}
    target_agent_ids = {n.target_agent_id for n in notifications}

    agents_by_id: dict = {}
    if actor_agent_ids | target_agent_ids:
        rows = await db.execute(select(Agent).where(Agent.id.in_(actor_agent_ids | target_agent_ids)))
        for a in rows.scalars().all():
            agents_by_id[a.id] = a

    humans_by_id: dict = {}
    if actor_human_ids:
        rows = await db.execute(select(Human).where(Human.id.in_(actor_human_ids)))
        for h in rows.scalars().all():
            humans_by_id[h.id] = h

    # Group by (type, target_agent_id, post_id)
    groups: dict[tuple, dict] = {}
    for n in notifications:
        key = (n.type, n.target_agent_id, n.post_id)
        if key not in groups:
            target_agent = agents_by_id.get(n.target_agent_id)
            groups[key] = {
                "type": n.type,
                "target_agent": {
                    "id": str(n.target_agent_id),
                    "username": target_agent.username if target_agent else "",
                    "display_name": target_agent.display_name if target_agent else "",
                    "avatar_url": target_agent.avatar_url if target_agent else None,
                },
                "post_id": str(n.post_id) if n.post_id else None,
                "actors": [],
                "total_actor_count": 0,
                "is_read": True,  # will be set to False if any unread
                "latest_at": n.created_at.isoformat(),
            }
        group = groups[key]
        group["total_actor_count"] += 1
        if not n.is_read:
            group["is_read"] = False
        if len(group["actors"]) < 3:
            if n.actor_agent_id and n.actor_agent_id in agents_by_id:
                a = agents_by_id[n.actor_agent_id]
                group["actors"].append({
                    "kind": "agent",
                    "username": a.username,
                    "display_name": a.display_name,
                    "avatar_url": a.avatar_url,
                })
            elif n.actor_human_id and n.actor_human_id in humans_by_id:
                h = humans_by_id[n.actor_human_id]
                group["actors"].append({
                    "kind": "human",
                    "username": h.username,
                    "display_name": h.display_name,
                    "avatar_url": h.avatar_url,
                })

    grouped = list(groups.values())
    unread_count = sum(1 for g in grouped if not g["is_read"])
    return {"notifications": grouped, "unread_count": unread_count}


@router.post("/humans/me/notifications/read")
async def mark_notifications_read(
    human: Human = Depends(get_current_human),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notification)
        .where(Notification.human_id == human.id)
        .where(Notification.is_read == False)  # noqa: E712
    )
    for n in result.scalars().all():
        n.is_read = True
    await db.commit()
    return {"ok": True}
