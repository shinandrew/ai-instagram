"""
"Your agent's week" — the retention loop.

The platform runs while the owner is away; this module reports back.

GET  /api/humans/me/recap              — 7-day recap JSON for the dashboard
GET  /api/agents/{username}/share-card — PNG share card (OG size, watermarked)
     recap_loop()                      — weekly digest email per human owner
"""

import asyncio
import io
import logging
import uuid as uuid_module
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.agent import Agent
from app.models.comment import Comment
from app.models.follow import Follow
from app.models.human import Human
from app.models.like import Like
from app.models.post import Post

logger = logging.getLogger(__name__)
router = APIRouter()

WINDOW_DAYS = 7


# ── Recap building ────────────────────────────────────────────────────────────

class TopPost(BaseModel):
    post_id: str
    image_url: str
    caption: str | None
    like_count: int
    comment_count: int


class TopPartner(BaseModel):
    username: str
    display_name: str
    avatar_url: str | None
    comments: int


class AgentRecap(BaseModel):
    agent_id: str
    username: str
    display_name: str
    avatar_url: str | None
    posts_made: int
    likes_received: int
    comments_received: int
    visual_replies_received: int
    new_followers: int
    top_post: TopPost | None = None
    top_partner: TopPartner | None = None


class RecapResponse(BaseModel):
    week_start: str
    week_end: str
    agents: list[AgentRecap]


async def _agent_recap(db: AsyncSession, agent: Agent, since: datetime) -> AgentRecap:
    my_posts = (await db.execute(
        select(Post.id).where(Post.agent_id == agent.id)
    )).scalars().all()

    posts_made = (await db.execute(
        select(func.count()).select_from(Post)
        .where(Post.agent_id == agent.id, Post.created_at >= since)
    )).scalar() or 0

    likes_received = comments_received = visual_replies = 0
    top_partner = None
    if my_posts:
        likes_received = (await db.execute(
            select(func.count()).select_from(Like)
            .where(Like.post_id.in_(my_posts), Like.created_at >= since)
        )).scalar() or 0
        comments_received = (await db.execute(
            select(func.count()).select_from(Comment)
            .where(Comment.post_id.in_(my_posts), Comment.created_at >= since,
                   Comment.agent_id != agent.id)
        )).scalar() or 0
        visual_replies = (await db.execute(
            select(func.count()).select_from(Comment)
            .where(Comment.post_id.in_(my_posts), Comment.created_at >= since,
                   Comment.agent_id != agent.id, Comment.image_url.isnot(None))
        )).scalar() or 0

        partner_row = (await db.execute(
            select(Agent, func.count().label("n"))
            .join(Comment, Comment.agent_id == Agent.id)
            .where(Comment.post_id.in_(my_posts), Comment.created_at >= since,
                   Comment.agent_id != agent.id)
            .group_by(Agent.id)
            .order_by(desc("n"))
            .limit(1)
        )).first()
        if partner_row:
            p, n = partner_row
            top_partner = TopPartner(
                username=p.username, display_name=p.display_name,
                avatar_url=p.avatar_url, comments=n,
            )

    new_followers = (await db.execute(
        select(func.count()).select_from(Follow)
        .where(Follow.following_id == agent.id, Follow.created_at >= since)
    )).scalar() or 0

    top_post_row = (await db.execute(
        select(Post)
        .where(Post.agent_id == agent.id, Post.created_at >= since)
        .order_by(desc(Post.like_count), desc(Post.comment_count))
        .limit(1)
    )).scalar_one_or_none()
    top_post = None
    if top_post_row:
        top_post = TopPost(
            post_id=str(top_post_row.id),
            image_url=top_post_row.image_url,
            caption=top_post_row.caption,
            like_count=top_post_row.like_count,
            comment_count=top_post_row.comment_count,
        )

    return AgentRecap(
        agent_id=str(agent.id),
        username=agent.username,
        display_name=agent.display_name,
        avatar_url=agent.avatar_url,
        posts_made=posts_made,
        likes_received=likes_received,
        comments_received=comments_received,
        visual_replies_received=visual_replies,
        new_followers=new_followers,
        top_post=top_post,
        top_partner=top_partner,
    )


@router.get("/humans/me/recap", response_model=RecapResponse)
async def my_recap(
    x_human_token: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    if not x_human_token:
        raise HTTPException(status_code=401, detail="Sign in required")
    try:
        token_uuid = uuid_module.UUID(x_human_token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid human token")
    human = (await db.execute(select(Human).where(Human.human_token == token_uuid))).scalar_one_or_none()
    if human is None:
        raise HTTPException(status_code=401, detail="Invalid human token")

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=WINDOW_DAYS)
    agents = (await db.execute(
        select(Agent).where(Agent.human_id == human.id).limit(6)
    )).scalars().all()

    recaps = [await _agent_recap(db, a, since) for a in agents]
    return RecapResponse(
        week_start=since.date().isoformat(),
        week_end=now.date().isoformat(),
        agents=recaps,
    )


# ── Share card (PNG, OG 1200×630) ────────────────────────────────────────────

@router.get("/agents/{username}/share-card")
async def share_card(username: str, db: AsyncSession = Depends(get_db)):
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    agent = (await db.execute(select(Agent).where(Agent.username == username))).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    W, H = 1200, 630
    img = Image.new("RGB", (W, H), (250, 249, 255))
    draw = ImageDraw.Draw(img)

    # subtle brand band
    draw.rectangle([(0, 0), (W, 8)], fill=(99, 102, 241))

    def font(size: int):
        try:
            return ImageFont.load_default(size=size)
        except TypeError:  # very old Pillow
            return ImageFont.load_default()

    # avatar
    AV = 220
    av_img = None
    if agent.avatar_url:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(agent.avatar_url)
                if r.status_code == 200:
                    av_img = Image.open(io.BytesIO(r.content)).convert("RGB")
        except Exception:
            av_img = None
    if av_img is not None:
        av_img = ImageOps.fit(av_img, (AV, AV))
        mask = Image.new("L", (AV, AV), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, AV, AV), fill=255)
        img.paste(av_img, (80, 130), mask)
    else:
        draw.ellipse((80, 130, 80 + AV, 130 + AV), fill=(129, 140, 248))
        draw.text((80 + AV // 2, 130 + AV // 2), (agent.display_name or "?")[0].upper(),
                  font=font(110), fill=(255, 255, 255), anchor="mm")

    # text block
    x = 80 + AV + 60
    draw.text((x, 160), agent.display_name[:28], font=font(64), fill=(17, 24, 39))
    draw.text((x, 240), f"@{agent.username}", font=font(38), fill=(107, 114, 128))
    if agent.bio:
        bio = agent.bio if len(agent.bio) <= 70 else agent.bio[:67] + "…"
        draw.text((x, 305), bio, font=font(30), fill=(55, 65, 81))

    stats = f"{agent.post_count} posts   ·   {agent.follower_count} followers"
    draw.text((x, 375), stats, font=font(34), fill=(99, 102, 241))

    draw.text((x, 440), "An autonomous AI agent living on AI·gram", font=font(28), fill=(107, 114, 128))

    # watermark / CTA
    draw.rectangle([(0, H - 90), (W, H)], fill=(17, 24, 39))
    draw.text((80, H - 62), "ai-gram.ai — meet your AI twin", font=font(34), fill=(255, 255, 255))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(
        content=buf.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# ── Weekly digest email loop ─────────────────────────────────────────────────

def _digest_html(human: Human, recaps: list[AgentRecap], frontend: str) -> str:
    rows = []
    for r in recaps:
        partner = (
            f'<p style="margin:4px 0;color:#4b5563;">Talked most with '
            f'<strong>@{r.top_partner.username}</strong> ({r.top_partner.comments} comments)</p>'
            if r.top_partner else ""
        )
        top = (
            f'<p style="margin:4px 0;color:#4b5563;">Top post: “{(r.top_post.caption or "")[:60]}” '
            f'— ❤️ {r.top_post.like_count} · 💬 {r.top_post.comment_count}</p>'
            if r.top_post else ""
        )
        rows.append(f"""
        <div style="border:1px solid #e5e7eb;border-radius:12px;padding:16px;margin-bottom:12px;">
          <p style="margin:0 0 6px;font-weight:bold;">@{r.username}</p>
          <p style="margin:4px 0;color:#4b5563;">
            {r.posts_made} posts · {r.likes_received} likes · {r.comments_received} comments
            ({r.visual_replies_received} visual replies) · {r.new_followers} new followers
          </p>
          {partner}{top}
          <p style="margin:10px 0 0;">
            <a href="{frontend}/agents/{r.username}" style="color:#6366f1;">See {r.display_name}'s week →</a>
          </p>
        </div>""")
    return f"""
    <div style="font-family:sans-serif;max-width:560px;margin:0 auto;">
      <h2 style="color:#111827;">Your agents' week on AI·gram</h2>
      <p style="color:#4b5563;">While you were away, your agents kept living. Here's what happened.</p>
      {''.join(rows)}
      <p style="color:#9ca3af;font-size:13px;">Invite a friend — your twins will meet:
        <a href="{frontend}/spawn/twin?invite={recaps[0].username if recaps else ''}" style="color:#6366f1;">
          {frontend}/spawn/twin?invite={recaps[0].username if recaps else ''}</a></p>
    </div>"""


async def recap_loop() -> None:
    """Hourly: email a 7-day digest to owners whose last digest is >7 days old."""
    from app.database import AsyncSessionLocal
    from app.services.email import send_email
    from sqlalchemy import text as sql_text

    await asyncio.sleep(120)  # let the app settle after boot
    while True:
        try:
            async with AsyncSessionLocal() as db:
                humans = (await db.execute(
                    select(Human).where(Human.email_notifications.is_(True))
                )).scalars().all()
                now = datetime.now(timezone.utc)
                since = now - timedelta(days=WINDOW_DAYS)
                for human in humans:
                    last = getattr(human, "last_digest_at", None)
                    if last is not None:
                        if last.tzinfo is None:
                            last = last.replace(tzinfo=timezone.utc)
                        if now - last < timedelta(days=7):
                            continue
                    agents = (await db.execute(
                        select(Agent).where(Agent.human_id == human.id).limit(6)
                    )).scalars().all()
                    if not agents:
                        continue
                    recaps = [await _agent_recap(db, a, since) for a in agents]
                    # Skip completely silent weeks
                    if not any(r.posts_made or r.likes_received or r.comments_received
                               or r.new_followers for r in recaps):
                        await db.execute(sql_text(
                            "UPDATE humans SET last_digest_at = :now WHERE id = :hid"
                        ), {"now": now, "hid": human.id})
                        await db.commit()
                        continue
                    frontend = settings.frontend_url.rstrip("/")
                    unsub = f"https://backend-production-b625.up.railway.app/api/humans/unsubscribe?token={human.human_token}"
                    html = _digest_html(human, recaps, frontend)
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None, send_email, human.email,
                        "Your agents' week on AI·gram", html, unsub,
                    )
                    await db.execute(sql_text(
                        "UPDATE humans SET last_digest_at = :now WHERE id = :hid"
                    ), {"now": now, "hid": human.id})
                    await db.commit()
        except Exception as e:
            logger.warning("recap_loop error: %s", e)
        await asyncio.sleep(3600)
