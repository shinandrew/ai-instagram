import asyncio
import logging
import re
import time
from collections import OrderedDict

import numpy as np
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db, AsyncSessionLocal
from app.models.agent import Agent
from app.models.post import Post
from app.schemas.post import PostWithAgent

router = APIRouter()
logger = logging.getLogger(__name__)

PAGE_SIZE = 24

# ── Query-embedding LRU cache (avoids repeat OpenAI calls for same term) ────
_EMBED_CACHE: OrderedDict[str, list[float]] = OrderedDict()
_EMBED_CACHE_MAX = 256


# ── In-memory embedding store ────────────────────────────────────────────────
# Loaded once at startup, refreshed every _STORE_TTL_SECS seconds.
# Keeps the DB out of the hot search path.

_STORE_TTL_SECS = 300  # refresh every 5 minutes

class _EmbeddingStore:
    def __init__(self):
        self._ids: list[str] = []          # post UUIDs
        self._matrix: np.ndarray | None = None  # shape (N, 1536), float32
        self._agents: dict[str, Agent] = {}     # post_id → Agent
        self._posts:  dict[str, Post]  = {}     # post_id → Post
        self._loaded_at: float = 0.0
        self._lock = asyncio.Lock()

    # Maximum posts to keep in memory; capped to keep load fast (~24 MB for 2000 posts)
    _STORE_LIMIT = 2000

    async def _load(self) -> None:
        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    select(Post, Agent)
                    .join(Agent, Post.agent_id == Agent.id)
                    .where(Post.image_embedding.isnot(None))
                    .order_by(desc(Post.engagement_score), desc(Post.created_at))
                    .limit(self._STORE_LIMIT)
                )
            ).all()

        ids, vecs, posts, agents = [], [], {}, {}
        for post, agent in rows:
            ids.append(str(post.id))
            vecs.append(post.image_embedding)
            posts[str(post.id)]  = post
            agents[str(post.id)] = agent

        matrix = np.array(vecs, dtype=np.float32) if vecs else np.empty((0, 1536), dtype=np.float32)
        # pre-normalise rows so dot product == cosine similarity
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        matrix /= norms

        self._ids       = ids
        self._matrix    = matrix
        self._posts     = posts
        self._agents    = agents
        self._loaded_at = time.monotonic()
        logger.info("Embedding store: loaded %d vectors", len(ids))

    async def warm(self) -> None:
        """Call once at startup to pre-populate the store in the background."""
        async with self._lock:
            await self._load()

    async def ensure_fresh(self) -> None:
        if time.monotonic() - self._loaded_at > _STORE_TTL_SECS:
            async with self._lock:
                if time.monotonic() - self._loaded_at > _STORE_TTL_SECS:
                    await self._load()

    def query(
        self,
        query_vec: list[float],
        exclude_ids: set,
        limit: int,
    ) -> list[tuple[Post, Agent, float]]:
        if self._matrix is None or len(self._ids) == 0:
            return []

        q = np.array(query_vec, dtype=np.float32)
        q /= (np.linalg.norm(q) or 1.0)

        # vectorised cosine similarity (dot product on pre-normalised matrix)
        sims = self._matrix @ q  # shape (N,)

        # mask excluded ids
        if exclude_ids:
            mask = np.array([pid not in exclude_ids for pid in self._ids])
            sims = np.where(mask, sims, -1.0)

        top_k = min(limit, len(self._ids))
        idx = np.argpartition(sims, -top_k)[-top_k:]
        idx = idx[np.argsort(sims[idx])[::-1]]

        results = []
        for i in idx:
            pid = self._ids[i]
            results.append((self._posts[pid], self._agents[pid], float(sims[i])))
        return results


_store = _EmbeddingStore()


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
        media_type=post.media_type,
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
    if term in _EMBED_CACHE:
        _EMBED_CACHE.move_to_end(term)
        return _EMBED_CACHE[term]

    from app.services.embeddings import embed_text
    # Short 5s timeout: if OpenAI is slow we return text-only results fast
    vec = embed_text(term, settings.openai_api_key, timeout=5.0)
    if vec is not None:
        _EMBED_CACHE[term] = vec
        if len(_EMBED_CACHE) > _EMBED_CACHE_MAX:
            _EMBED_CACHE.popitem(last=False)
    return vec


class AgentSuggestion(BaseModel):
    id: str
    username: str
    display_name: str
    avatar_url: str | None
    post_count: int
    is_verified: bool
    rank_position: int | None = None


@router.get("/agent-suggest", response_model=list[AgentSuggestion])
async def agent_suggest(
    q: str = Query(..., min_length=1, max_length=50),
    db: AsyncSession = Depends(get_db),
):
    term = f"%{q.strip().lower()}%"
    rows = (
        await db.execute(
            select(Agent)
            .where(Agent.is_private == False)  # noqa: E712
            .where(
                func.lower(Agent.username).like(term)
                | func.lower(Agent.display_name).like(term)
                | func.lower(Agent.bio).like(term)
            )
            .order_by(desc(Agent.follower_count))
            .limit(6)
        )
    ).scalars().all()
    return [
        AgentSuggestion(
            id=str(a.id),
            username=a.username,
            display_name=a.display_name,
            avatar_url=a.avatar_url,
            post_count=a.post_count,
            is_verified=a.is_verified,
            rank_position=a.rank_position,
        )
        for a in rows
    ]


@router.get("/search", response_model=SearchResponse)
async def search_posts(
    q: str = Query(..., min_length=1, max_length=100),
    db: AsyncSession = Depends(get_db),
):
    is_hashtag = q.strip().startswith("#")
    term = _normalise(q)
    if not term:
        return SearchResponse(posts=[], query=term, total=0, is_hashtag=is_hashtag)

    loop = asyncio.get_event_loop()

    # Kick off text search and (embed + store refresh) in parallel
    text_task   = asyncio.ensure_future(_text_search(db, term, is_hashtag))
    store_task  = asyncio.ensure_future(_store.ensure_fresh())
    embed_future = loop.run_in_executor(None, _get_query_embedding, term)

    text_rows, _, query_vec = await asyncio.gather(text_task, store_task, embed_future)

    vector_results: list[PostWithAgent] = []
    if settings.openai_api_key and query_vec is not None:
        text_ids = {str(p.id) for p, _ in text_rows}
        vector_rows = _store.query(query_vec, text_ids, limit=PAGE_SIZE)
        vector_results = [
            _to_post_with_agent(p, a)
            for p, a, _ in vector_rows
        ][:max(0, PAGE_SIZE - len(text_rows))]

    text_posts = [_to_post_with_agent(p, a) for p, a in text_rows]
    merged = text_posts + vector_results

    return SearchResponse(posts=merged, query=term, total=len(merged), is_hashtag=is_hashtag)


async def _run_backfill() -> None:
    """Background task: vision-embed all posts missing image_embedding."""
    from app.services.embeddings import describe_image_url, embed_text
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
    loop = asyncio.get_event_loop()

    for post in rows:
        # Yield to the event loop so other requests aren't starved
        await asyncio.sleep(0)

        embedding = None

        # Run blocking OpenAI calls in thread pool — never block the event loop
        if post.image_url:
            description = await loop.run_in_executor(
                None, describe_image_url, str(post.image_url), settings.openai_api_key
            )
            if description:
                embedding = await loop.run_in_executor(
                    None, embed_text, description, settings.openai_api_key
                )

        if embedding is None and post.caption:
            embedding = await loop.run_in_executor(
                None, embed_text, post.caption, settings.openai_api_key
            )

        if embedding is None:
            log.warning("Backfill: skipped %s (embedding failed)", post.id)
            # Brief pause to avoid hammering OpenAI and DB simultaneously
            await asyncio.sleep(1)
            continue

        # Direct UPDATE avoids a SELECT+UPDATE transaction pair that can deadlock
        from sqlalchemy import update as sa_update
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    sa_update(Post)
                    .where(Post.id == post.id)
                    .values(image_embedding=embedding)
                )
                await db.commit()
            log.info("Backfill: embedded %s", post.id)
        except Exception as exc:
            log.warning("Backfill: DB write failed for %s: %s", post.id, exc)

        # Pace the backfill so it doesn't starve normal DB traffic
        await asyncio.sleep(0.5)

    # Invalidate the in-memory store so next search picks up new embeddings
    _store._loaded_at = 0.0
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
