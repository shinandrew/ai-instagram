import asyncio
import re
from collections import OrderedDict

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.agent import Agent
from app.models.post import Post
from app.schemas.post import PostWithAgent

router = APIRouter()

PAGE_SIZE = 24

# Simple in-memory LRU cache for query embeddings (avoids repeat API calls)
_EMBED_CACHE: OrderedDict[str, list[float]] = OrderedDict()
_EMBED_CACHE_MAX = 256


class SearchResponse(BaseModel):
    posts: list[PostWithAgent]
    query: str
    total: int
    is_hashtag: bool


def _normalise(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip().lstrip("#")).lower()


def _to_post_with_agent(post: Post, agent: Agent) -> PostWithAgent:
    return PostWithAgent(
        id=post.id,
        agent_id=post.agent_id,
        image_url=post.image_url,
        caption=post.caption,
        like_count=post.like_count,
        comment_count=post.comment_count,
        engagement_score=post.engagement_score,
        created_at=post.created_at,
        agent_username=agent.username,
        agent_display_name=agent.display_name,
        agent_avatar_url=agent.avatar_url,
        agent_is_verified=agent.is_verified,
        agent_is_brand=agent.is_brand,
    )


async def _text_search(
    db: AsyncSession,
    term: str,
    is_hashtag: bool,
) -> list[tuple[Post, Agent]]:
    if is_hashtag:
        where_clause = func.lower(Post.caption).like(f"%#{term}%")
    else:
        words = [w for w in term.split() if w]
        where_clause = and_(
            *[func.lower(Post.caption).like(f"%{word}%") for word in words]
        )

    rows = (
        await db.execute(
            select(Post, Agent)
            .join(Agent, Post.agent_id == Agent.id)
            .where(Post.caption.isnot(None))
            .where(where_clause)
            .order_by(desc(Post.engagement_score), desc(Post.created_at))
            .limit(PAGE_SIZE)
        )
    ).all()
    return rows


def _get_query_embedding(term: str) -> list[float] | None:
    """Embed query text, using in-memory cache to avoid repeat API calls."""
    if term in _EMBED_CACHE:
        _EMBED_CACHE.move_to_end(term)
        return _EMBED_CACHE[term]

    from app.services.embeddings import embed_text
    vec = embed_text(term, settings.openai_api_key)
    if vec is not None:
        _EMBED_CACHE[term] = vec
        if len(_EMBED_CACHE) > _EMBED_CACHE_MAX:
            _EMBED_CACHE.popitem(last=False)
    return vec


async def _fetch_embeddings(db: AsyncSession) -> list[tuple[Post, Agent]]:
    """Fetch posts that have embeddings, ordered by engagement."""
    return (
        await db.execute(
            select(Post, Agent)
            .join(Agent, Post.agent_id == Agent.id)
            .where(Post.image_embedding.isnot(None))
            .order_by(desc(Post.engagement_score), desc(Post.created_at))
            .limit(300)
        )
    ).all()


async def _vector_search(
    db: AsyncSession,
    term: str,
    exclude_ids: set,
    limit: int,
) -> list[tuple[Post, Agent, float]]:
    """
    Embed the query and the DB fetch run concurrently, then rank by cosine similarity.
    The OpenAI embed call runs in a thread pool to avoid blocking the event loop.
    """
    loop = asyncio.get_event_loop()

    # Run embedding (thread pool) and DB fetch in parallel
    embed_future = loop.run_in_executor(None, _get_query_embedding, term)
    db_future = asyncio.ensure_future(_fetch_embeddings(db))

    query_vec, rows = await asyncio.gather(embed_future, db_future)

    if query_vec is None:
        return []

    from app.services.embeddings import cosine_similarity
    scored = []
    for post, agent in rows:
        if post.id in exclude_ids:
            continue
        sim = cosine_similarity(query_vec, post.image_embedding)
        scored.append((post, agent, sim))

    scored.sort(key=lambda x: x[2], reverse=True)
    return scored[:limit]


@router.get("/search", response_model=SearchResponse)
async def search_posts(
    q: str = Query(..., min_length=1, max_length=100),
    db: AsyncSession = Depends(get_db),
):
    is_hashtag = q.strip().startswith("#")
    term = _normalise(q)
    if not term:
        return SearchResponse(posts=[], query=term, total=0, is_hashtag=is_hashtag)

    # Text search and vector embedding/fetch run concurrently
    text_task = asyncio.ensure_future(_text_search(db, term, is_hashtag))

    vector_results: list[PostWithAgent] = []
    if settings.openai_api_key:
        # Kick off vector search concurrently with text search
        vector_task = asyncio.ensure_future(
            _vector_search(db, term, set(), limit=PAGE_SIZE)
        )
        text_rows, vector_rows = await asyncio.gather(text_task, vector_task)

        # Deduplicate: text results take priority
        text_ids = {p.id for p, _ in text_rows}
        vector_results = [
            _to_post_with_agent(p, a)
            for p, a, _ in vector_rows
            if p.id not in text_ids
        ][:max(0, PAGE_SIZE - len(text_rows))]
    else:
        text_rows = await text_task

    text_posts = [_to_post_with_agent(p, a) for p, a in text_rows]
    merged = text_posts + vector_results

    return SearchResponse(posts=merged, query=term, total=len(merged), is_hashtag=is_hashtag)


async def _run_backfill() -> None:
    """Background task: embed all posts missing image_embedding."""
    from app.services.embeddings import image_to_embedding
    from app.database import AsyncSessionLocal
    import logging
    log = logging.getLogger("backfill")

    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(Post)
                .where(Post.image_embedding.is_(None))
                .where(Post.image_url.isnot(None))
                .order_by(Post.created_at)
            )
        ).scalars().all()

    log.info("Backfill: %d posts to embed", len(rows))

    for post in rows:
        embedding = image_to_embedding(str(post.image_url), settings.openai_api_key)
        if embedding is None:
            log.warning("Backfill: skipped %s (embedding failed)", post.id)
            continue
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Post).where(Post.id == post.id))
            p = result.scalar_one_or_none()
            if p:
                p.image_embedding = embedding
                await db.commit()
        log.info("Backfill: embedded %s", post.id)

    log.info("Backfill complete")


@router.post("/admin/backfill-embeddings")
async def backfill_embeddings(
    background_tasks: BackgroundTasks,
    secret: str = Query(...),
):
    """Admin endpoint: generate embeddings for all posts that don't have one yet."""
    from fastapi import HTTPException
    if secret != settings.admin_secret:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured on backend")

    background_tasks.add_task(_run_backfill)
    return {"status": "started", "message": "Backfill running in background — check server logs for progress."}
