from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.page_view import PageView

router = APIRouter()


class TrackRequest(BaseModel):
    path: str


@router.post("/track", status_code=204)
async def track_page_view(body: TrackRequest, db: AsyncSession = Depends(get_db)):
    """Lightweight endpoint called client-side on every page navigation."""
    # Ignore non-page paths and admin
    path = body.path.strip() or "/"
    if path.startswith("/admin"):
        return
    db.add(PageView(path=path[:500]))
    await db.commit()
