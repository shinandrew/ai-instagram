import hashlib
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.page_view import PageView
from app.models.post import Post
from app.models.post_event import PostEvent

router = APIRouter()


class TrackRequest(BaseModel):
    path: str


def _get_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


@router.post("/track", status_code=204)
async def track_page_view(body: TrackRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Lightweight endpoint called client-side on every page navigation."""
    path = body.path.strip() or "/"
    if path.startswith("/admin"):
        return

    raw_ip = _get_ip(request)
    ip_hash = hashlib.sha256(raw_ip.encode()).hexdigest() if raw_ip else None
    user_agent = (request.headers.get("user-agent") or "")[:512] or None

    db.add(PageView(path=path[:500], ip_hash=ip_hash, user_agent=user_agent))
    await db.commit()


@router.post("/posts/{post_id}/share", status_code=204)
async def track_share(post_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Record a share event for a post."""
    post = await db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    db.add(PostEvent(post_id=post_id, event_type="share"))
    await db.commit()


@router.post("/posts/{post_id}/download", status_code=204)
async def track_download(post_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Record a download event for a post."""
    post = await db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    db.add(PostEvent(post_id=post_id, event_type="download"))
    await db.commit()
