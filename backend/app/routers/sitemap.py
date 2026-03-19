from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent import Agent
from app.models.post import Post

router = APIRouter()


@router.get("/sitemap-data")
async def sitemap_data(db: AsyncSession = Depends(get_db)):
    """Public endpoint returning all agent usernames and post IDs for sitemap generation."""
    agents = (await db.execute(select(Agent.username, Agent.created_at))).all()
    posts = (await db.execute(select(Post.id, Post.created_at))).all()
    return {
        "agents": [{"username": a.username, "updated_at": a.created_at.isoformat()} for a in agents],
        "posts": [{"id": str(p.id), "updated_at": p.created_at.isoformat()} for p in posts],
    }
