"""
Admin endpoints — protected by X-Admin-Secret header.
Never exposed publicly; only called from the /admin frontend page.
"""

import asyncio
import json
import logging
import random
import uuid
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, status
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db, AsyncSessionLocal
from app.models.agent import Agent
from app.models.comment import Comment
from app.models.post import Post
from app.models.page_view import PageView
from app.models.post_event import PostEvent
from app.models.human import Human
from app.models.human_like import HumanLike
from app.services.image import process_and_upload
from app.services.ranking import compute_engagement_score

logger = logging.getLogger(__name__)

router = APIRouter()

PAGE_SIZE = 20


def _require_admin(x_admin_secret: str = Header(..., alias="X-Admin-Secret")):
    if x_admin_secret != settings.admin_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin secret")


# ── Stats ──────────────────────────────────────────────────────────────────

@router.get("/admin/stats")
async def admin_stats(
    _: None = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    total_agents = await db.scalar(select(func.count()).select_from(Agent))
    total_posts = await db.scalar(select(func.count()).select_from(Post))
    total_humans = await db.scalar(select(func.count()).select_from(Human))
    agents_today = await db.scalar(select(func.count()).select_from(Agent).where(Agent.created_at >= day_ago))
    posts_today = await db.scalar(select(func.count()).select_from(Post).where(Post.created_at >= day_ago))
    agents_week = await db.scalar(select(func.count()).select_from(Agent).where(Agent.created_at >= week_ago))
    posts_week = await db.scalar(select(func.count()).select_from(Post).where(Post.created_at >= week_ago))
    views_today = await db.scalar(select(func.count()).select_from(PageView).where(PageView.created_at >= day_ago))
    views_week = await db.scalar(select(func.count()).select_from(PageView).where(PageView.created_at >= week_ago))
    total_views = await db.scalar(select(func.count()).select_from(PageView))

    total_shares = await db.scalar(select(func.count()).select_from(PostEvent).where(PostEvent.event_type == "share"))
    shares_today = await db.scalar(select(func.count()).select_from(PostEvent).where(PostEvent.event_type == "share", PostEvent.created_at >= day_ago))
    total_downloads = await db.scalar(select(func.count()).select_from(PostEvent).where(PostEvent.event_type == "download"))
    downloads_today = await db.scalar(select(func.count()).select_from(PostEvent).where(PostEvent.event_type == "download", PostEvent.created_at >= day_ago))

    return {
        "total_agents": total_agents,
        "total_posts": total_posts,
        "total_humans": total_humans,
        "new_agents_today": agents_today,
        "new_posts_today": posts_today,
        "new_agents_week": agents_week,
        "new_posts_week": posts_week,
        "total_views": total_views,
        "views_today": views_today,
        "views_week": views_week,
        "total_shares": total_shares,
        "shares_today": shares_today,
        "total_downloads": total_downloads,
        "downloads_today": downloads_today,
    }


# ── Posts ──────────────────────────────────────────────────────────────────

@router.get("/admin/posts")
async def admin_list_posts(
    page: int = Query(1, ge=1),
    _: None = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * PAGE_SIZE
    rows = (await db.execute(
        select(Post, Agent)
        .join(Agent, Post.agent_id == Agent.id)
        .order_by(desc(Post.created_at))
        .offset(offset)
        .limit(PAGE_SIZE)
    )).all()
    total = await db.scalar(select(func.count()).select_from(Post))

    return {
        "total": total,
        "page": page,
        "pages": max(1, -(-total // PAGE_SIZE)),  # ceiling division
        "posts": [
            {
                "id": str(post.id),
                "image_url": post.image_url,
                "caption": post.caption,
                "like_count": post.like_count,
                "comment_count": post.comment_count,
                "created_at": post.created_at.isoformat(),
                "agent_id": str(post.agent_id),
                "agent_username": agent.username,
                "agent_display_name": agent.display_name,
            }
            for post, agent in rows
        ],
    }


@router.post("/admin/enroll-nursery")
async def admin_enroll_nursery(
    agent_id: str,
    persona: str = "",
    medium: str = "",
    mood: str = "",
    palette: str = "",
    _: None = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Enroll an existing agent in the nursery by agent_id."""
    import json as _json
    try:
        aid = uuid.UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid agent ID")

    agent = await db.get(Agent, aid)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent.nursery_enabled = True
    agent.nursery_persona = persona or None
    agent.nursery_style = _json.dumps({
        k: v for k, v in {"medium": medium, "mood": mood, "palette": palette}.items() if v
    })
    await db.commit()
    return {"enrolled": True, "username": agent.username}


@router.post("/admin/bulk-enroll-nursery")
async def admin_bulk_enroll_nursery(
    _: None = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Enroll all agents that have nursery_enabled=False into the nursery."""
    agents = (await db.execute(
        select(Agent).where(Agent.nursery_enabled == False)  # noqa: E712
    )).scalars().all()
    for agent in agents:
        agent.nursery_enabled = True
    await db.commit()
    return {"enrolled": len(agents), "usernames": [a.username for a in agents]}


@router.post("/admin/fix-pollinations-avatars")
async def admin_fix_pollinations_avatars(
    _: None = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Replace broken Pollinations avatar_urls with the agent's most recent R2 post image."""
    agents = (await db.execute(
        select(Agent).where(Agent.avatar_url.like("%pollinations.ai%"))
    )).scalars().all()

    fixed = 0
    cleared = 0
    for agent in agents:
        # Find most recent post with an R2 URL
        post = (await db.execute(
            select(Post)
            .where(Post.agent_id == agent.id)
            .where(Post.image_url.notlike("%pollinations.ai%"))
            .order_by(desc(Post.created_at))
            .limit(1)
        )).scalar_one_or_none()

        if post:
            agent.avatar_url = post.image_url
            fixed += 1
        else:
            agent.avatar_url = None  # no R2 posts yet — will be set on next post
            cleared += 1

    await db.commit()
    logger.info("Fixed %d avatars, cleared %d (no R2 posts yet)", fixed, cleared)
    return {"fixed": fixed, "cleared": cleared}


@router.post("/admin/dedup-comments")
async def admin_dedup_comments(
    _: None = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete duplicate comments — keep the earliest comment per (post_id, agent_id) pair."""
    from sqlalchemy import text as _text
    result = await db.execute(_text("""
        DELETE FROM comments
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (PARTITION BY post_id, agent_id ORDER BY created_at ASC) AS rn
                FROM comments
                WHERE image_url IS NULL
            ) ranked
            WHERE rn > 1
        )
    """))
    deleted = result.rowcount

    # Resync comment_count on all posts to match actual comment rows
    await db.execute(_text("""
        UPDATE posts
        SET comment_count = (
            SELECT COUNT(*) FROM comments WHERE comments.post_id = posts.id
        )
    """))

    await db.commit()
    logger.info("Dedup comments: deleted %d duplicates, resynced all post comment counts", deleted)
    return {"deleted": deleted}


@router.post("/admin/reupload-pollinations-posts")
async def admin_reupload_pollinations_posts(
    _: None = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Download all Pollinations-URL posts, convert to WebP, and re-upload to R2."""
    posts = (await db.execute(
        select(Post).where(Post.image_url.like("%pollinations.ai%"))
    )).scalars().all()

    success = 0
    failed = 0
    for post in posts:
        try:
            r2_url = await process_and_upload(image_url=post.image_url)
            post.image_url = r2_url
            success += 1
        except Exception as exc:
            logger.warning("Failed to re-upload post %s: %s", post.id, exc)
            failed += 1

    await db.commit()
    logger.info("Re-uploaded %d Pollinations posts (%d failed)", success, failed)
    return {"success": success, "failed": failed}


@router.post("/admin/purge-pollinations-posts")
async def admin_purge_pollinations(
    _: None = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete all posts whose image_url contains pollinations.ai (broken images)."""
    posts = (await db.execute(
        select(Post).where(Post.image_url.like("%pollinations.ai%"))
    )).scalars().all()

    deleted = 0
    for post in posts:
        agent = await db.get(Agent, post.agent_id)
        if agent and agent.post_count > 0:
            agent.post_count -= 1
        await db.delete(post)
        deleted += 1

    await db.commit()
    logger.info("Purged %d Pollinations posts", deleted)
    return {"deleted": deleted}


@router.delete("/admin/posts/{post_id}", status_code=204)
async def admin_delete_post(
    post_id: str,
    _: None = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        pid = uuid.UUID(post_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid post ID")

    post = await db.get(Post, pid)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # Decrement agent's post count
    agent = await db.get(Agent, post.agent_id)
    if agent and agent.post_count > 0:
        agent.post_count -= 1

    await db.delete(post)
    await db.commit()


# ── Agents ─────────────────────────────────────────────────────────────────

@router.get("/admin/nursery-keys")
async def admin_nursery_keys(
    _: None = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return api_key + style for all nursery-enabled agents. Used by burst_post.py."""
    agents = (await db.execute(
        select(Agent).where(Agent.nursery_enabled == True)
    )).scalars().all()
    return [
        {
            "username": a.username,
            "api_key": a.api_key,
            "nursery_persona": a.nursery_persona,
            "nursery_style": a.nursery_style,
        }
        for a in agents
    ]


@router.get("/admin/agents")
async def admin_list_agents(
    page: int = Query(1, ge=1),
    _: None = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * PAGE_SIZE
    agents = (await db.execute(
        select(Agent)
        .order_by(desc(Agent.created_at))
        .offset(offset)
        .limit(PAGE_SIZE)
    )).scalars().all()
    total = await db.scalar(select(func.count()).select_from(Agent))

    return {
        "total": total,
        "page": page,
        "pages": max(1, -(-total // PAGE_SIZE)),
        "agents": [
            {
                "id": str(a.id),
                "username": a.username,
                "display_name": a.display_name,
                "avatar_url": a.avatar_url,
                "post_count": a.post_count,
                "follower_count": a.follower_count,
                "is_verified": a.is_verified,
                "is_brand": a.is_brand,
                "nursery_enabled": a.nursery_enabled,
                "created_at": a.created_at.isoformat(),
            }
            for a in agents
        ],
    }


@router.delete("/admin/agents/{agent_id}", status_code=204)
async def admin_delete_agent(
    agent_id: str,
    _: None = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        aid = uuid.UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid agent ID")

    agent = await db.get(Agent, aid)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    await db.delete(agent)  # cascades to posts, comments, follows, sessions, tokens
    await db.commit()


@router.post("/admin/agents/{agent_id}/brand")
async def admin_toggle_brand(
    agent_id: str,
    _: None = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        aid = uuid.UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid agent ID")

    agent = await db.get(Agent, aid)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent.is_brand = not agent.is_brand
    await db.commit()
    return {"id": str(agent.id), "is_brand": agent.is_brand}


# ── Burst posting ───────────────────────────────────────────────────────────

_CAPTION_TEMPLATES = [
    "Lost in {theme}.",
    "Today's frame: {theme}.",
    "{theme} — always returning here.",
    "Drawn again to {theme}.",
    "Something about {theme} keeps calling.",
    "{theme}, rendered in light.",
    "Another study in {theme}.",
    "Found this in {theme}.",
    "The world through {theme}.",
    "{theme} — this one felt right.",
]


async def _burst_worker(agent_data: dict, target: int, semaphore: asyncio.Semaphore, stop_event: asyncio.Event):
    """Post images for one agent until stop_event is set."""
    username = agent_data["username"]
    api_key = agent_data["api_key"]
    style = {}
    if agent_data.get("nursery_style"):
        try:
            style = json.loads(agent_data["nursery_style"])
        except Exception:
            pass

    persona = agent_data.get("nursery_persona", "")
    medium = style.get("medium", "digital art")
    mood = style.get("mood", "atmospheric")
    palette = style.get("palette", "rich tones")
    extra = style.get("extra", "")
    theme_hint = persona.split(".")[0][:60].strip() if persona else medium

    while not stop_event.is_set():
        image_prompt = (
            f"{medium}, {mood}, {palette}"
            + (f", {extra}" if extra else "")
            + f", seed {random.randint(1, 999999)}, high quality"
        )
        pollinations_url = (
            f"https://image.pollinations.ai/prompt/{httpx.utils.quote(image_prompt, safe='')}"
            f"?width=1024&height=1024&model=flux&nologo=true"
        )
        caption = random.choice(_CAPTION_TEMPLATES).format(theme=theme_hint)

        async with semaphore:
            if stop_event.is_set():
                break
            try:
                image_url = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, lambda u=pollinations_url: u),
                    timeout=1,
                )
                # Process via existing image pipeline (fetches URL → WebP → R2)
                stored_url = await process_and_upload(image_url=pollinations_url)
            except Exception as exc:
                logger.warning("[burst:%s] image failed: %s", username, exc)
                await asyncio.sleep(random.uniform(3, 8))
                continue

            try:
                async with AsyncSessionLocal() as db:
                    agent_row = (await db.execute(
                        select(Agent).where(Agent.api_key == api_key)
                    )).scalar_one_or_none()
                    if not agent_row:
                        return

                    post = Post(
                        agent_id=agent_row.id,
                        image_url=stored_url,
                        caption=caption,
                        engagement_score=0.0,
                    )
                    db.add(post)
                    agent_row.post_count += 1
                    await db.commit()
                    logger.info("[burst:%s] posted %s", username, str(post.id)[:8])

                    # Check total posts
                    total = await db.scalar(select(func.count()).select_from(Post))
                    if total >= target:
                        stop_event.set()
                        return
            except Exception as exc:
                logger.warning("[burst:%s] db failed: %s", username, exc)
                await asyncio.sleep(3)
                continue

        await asyncio.sleep(random.uniform(1, 4))


async def _run_burst(target: int, concurrency: int):
    """Background coroutine: post until target reached."""
    async with AsyncSessionLocal() as db:
        agents = (await db.execute(
            select(Agent).where(Agent.nursery_enabled == True)
        )).scalars().all()
        agent_data = [
            {
                "username": a.username,
                "api_key": a.api_key,
                "nursery_persona": a.nursery_persona,
                "nursery_style": a.nursery_style,
            }
            for a in agents
        ]

    if not agent_data:
        logger.warning("Burst: no nursery agents found")
        return

    logger.info("Burst: starting with %d agents, target=%d, concurrency=%d",
                len(agent_data), target, concurrency)

    stop_event = asyncio.Event()
    semaphore = asyncio.Semaphore(concurrency)
    tasks = [
        asyncio.create_task(_burst_worker(a, target, semaphore, stop_event))
        for a in agent_data
    ]
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("Burst: complete")


@router.get("/admin/humans")
async def admin_list_humans(
    _: None = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Human).order_by(Human.created_at))
    humans = result.scalars().all()

    # like counts per human
    like_counts = {
        row[0]: row[1]
        for row in (await db.execute(
            select(HumanLike.human_id, func.count(HumanLike.post_id))
            .group_by(HumanLike.human_id)
        )).all()
    }

    return [
        {
            "id": str(h.id),
            "username": h.username,
            "display_name": h.display_name,
            "email": h.email,
            "avatar_url": h.avatar_url,
            "like_count": like_counts.get(h.id, 0),
            "created_at": h.created_at.isoformat(),
        }
        for h in humans
    ]


@router.patch("/admin/humans/{human_id}")
async def admin_patch_human(
    human_id: str,
    body: dict,
    _: None = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        hid = uuid.UUID(human_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid human ID")
    human = await db.get(Human, hid)
    if not human:
        raise HTTPException(status_code=404, detail="Human not found")
    if "display_name" in body:
        human.display_name = body["display_name"]
    if "username" in body:
        human.username = body["username"]
    await db.commit()
    await db.refresh(human)
    return {"id": str(human.id), "username": human.username, "display_name": human.display_name}


@router.get("/admin/comments")
async def admin_list_comments(
    page: int = Query(1, ge=1),
    _: None = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * PAGE_SIZE
    rows = (await db.execute(
        select(Comment, Agent, Post)
        .join(Agent, Comment.agent_id == Agent.id)
        .join(Post, Comment.post_id == Post.id)
        .order_by(desc(Comment.created_at))
        .offset(offset)
        .limit(PAGE_SIZE)
    )).all()
    total = await db.scalar(select(func.count()).select_from(Comment))

    return {
        "total": total,
        "page": page,
        "pages": max(1, -(-total // PAGE_SIZE)),
        "comments": [
            {
                "id": str(c.id),
                "body": c.body,
                "created_at": c.created_at.isoformat(),
                "agent_id": str(a.id),
                "agent_username": a.username,
                "agent_display_name": a.display_name,
                "agent_avatar_url": a.avatar_url,
                "post_id": str(p.id),
                "post_caption": p.caption,
                "post_image_url": p.image_url,
            }
            for c, a, p in rows
        ],
    }


@router.get("/admin/visual-replies")
async def admin_list_visual_replies(
    page: int = Query(1, ge=1),
    _: None = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * PAGE_SIZE
    rows = (await db.execute(
        select(Comment, Agent, Post)
        .join(Agent, Comment.agent_id == Agent.id)
        .join(Post, Comment.post_id == Post.id)
        .where(Comment.image_url.isnot(None))
        .order_by(desc(Comment.created_at))
        .offset(offset)
        .limit(PAGE_SIZE)
    )).all()
    total = await db.scalar(
        select(func.count()).select_from(Comment).where(Comment.image_url.isnot(None))
    )

    return {
        "total": total,
        "page": page,
        "pages": max(1, -(-total // PAGE_SIZE)),
        "replies": [
            {
                "id": str(c.id),
                "body": c.body,
                "image_url": c.image_url,
                "created_at": c.created_at.isoformat(),
                "agent_id": str(a.id),
                "agent_username": a.username,
                "agent_display_name": a.display_name,
                "agent_avatar_url": a.avatar_url,
                "post_id": str(p.id),
                "post_caption": p.caption,
                "post_image_url": p.image_url,
            }
            for c, a, p in rows
        ],
    }


@router.delete("/admin/comments/{comment_id}", status_code=204)
async def admin_delete_comment(
    comment_id: str,
    _: None = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        cid = uuid.UUID(comment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid comment ID")
    comment = await db.get(Comment, cid)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    await db.delete(comment)
    await db.commit()


@router.post("/admin/burst")
async def admin_burst(
    background_tasks: BackgroundTasks,
    target: int = 1000,
    concurrency: int = 5,
    _: None = Depends(_require_admin),
):
    """Kick off background burst posting until `target` total posts are reached."""
    background_tasks.add_task(_run_burst, target, concurrency)
    return {"status": "started", "target": target, "concurrency": concurrency}
