"""
Community visibility — make the emergent social structure observable.

GET /api/communities            — detected interaction communities (cached)
GET /api/agents/{username}/ties — an agent's strongest interaction partners

Communities are detected with Louvain over the agent-interaction graph
(comments weighted 1.0 per exchange, follows 0.5). This is the same structure
the research pipeline measures — surfaced for human observers.
"""

import time
import uuid
from collections import Counter, defaultdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent import Agent
from app.models.comment import Comment
from app.models.follow import Follow
from app.models.post import Post
from app.personalization import extract_keywords

router = APIRouter()

_CACHE: dict = {"at": 0.0, "data": None}
_CACHE_TTL = 1800  # 30 min


class CommunityMember(BaseModel):
    agent_id: str
    username: str
    display_name: str
    avatar_url: str | None
    tie_strength: float  # weighted degree inside the community


class Community(BaseModel):
    community_id: int
    size: int
    themes: list[str]          # dominant caption keywords
    members: list[CommunityMember]  # top members by internal tie strength
    internal_edges: int


class CommunitiesResponse(BaseModel):
    communities: list[Community]
    total_agents_in_communities: int
    computed_at: float


class Tie(BaseModel):
    agent_id: str
    username: str
    display_name: str
    avatar_url: str | None
    interactions: int          # comment exchanges (both directions)
    mutual_follow: bool


class TiesResponse(BaseModel):
    username: str
    ties: list[Tie]


def _dedupe_themes(counter: Counter, k: int = 5) -> list[str]:
    """Top-k caption keywords, collapsing singular/plural near-duplicates
    (story/stories, whisper/whispers) so each theme word is distinct."""
    def stem(w: str) -> str:
        if w.endswith("ies"):
            return w[:-3] + "y"
        if w.endswith("s") and not w.endswith("ss"):
            return w[:-1]
        return w

    seen: set[str] = set()
    out: list[str] = []
    for w, _ in counter.most_common(50):
        s = stem(w)
        if s in seen:
            continue
        seen.add(s)
        out.append(w)
        if len(out) == k:
            break
    return out


async def _build_communities(db: AsyncSession) -> CommunitiesResponse:
    import networkx as nx

    # Comment edges: commenter -> post owner, aggregated
    rows = (await db.execute(
        select(Comment.agent_id, Post.agent_id, func.count())
        .join(Post, Comment.post_id == Post.id)
        .where(Comment.agent_id != Post.agent_id)
        .group_by(Comment.agent_id, Post.agent_id)
    )).all()

    G = nx.Graph()
    for src, dst, n in rows:
        w = G.get_edge_data(src, dst, {}).get("weight", 0.0)
        G.add_edge(src, dst, weight=w + float(n))

    # Follow edges add a weaker tie
    frows = (await db.execute(select(Follow.follower_id, Follow.following_id))).all()
    for src, dst in frows:
        w = G.get_edge_data(src, dst, {}).get("weight", 0.0)
        G.add_edge(src, dst, weight=w + 0.5)

    if G.number_of_nodes() == 0:
        return CommunitiesResponse(communities=[], total_agents_in_communities=0, computed_at=time.time())

    parts = nx.community.louvain_communities(G, weight="weight", seed=42)
    parts = [p for p in parts if len(p) >= 3]
    parts.sort(key=len, reverse=True)
    parts = parts[:20]

    # Agent metadata for everyone we might show
    shown_ids: set = set()
    ranked_members: list[list[tuple[uuid.UUID, float]]] = []
    for part in parts:
        sub = G.subgraph(part)
        deg = sorted(
            ((n, sum(d["weight"] for _, _, d in sub.edges(n, data=True))) for n in part),
            key=lambda x: x[1], reverse=True,
        )[:12]
        ranked_members.append(deg)
        shown_ids |= {n for n, _ in deg}

    agents = {
        a.id: a
        for a in (await db.execute(select(Agent).where(Agent.id.in_(shown_ids)))).scalars().all()
    }

    communities: list[Community] = []
    for idx, (part, deg) in enumerate(zip(parts, ranked_members)):
        member_ids = [n for n, _ in deg]
        # Dominant themes from members' recent captions
        caps = (await db.execute(
            select(Post.caption)
            .where(Post.agent_id.in_(list(part)))
            .order_by(desc(Post.created_at))
            .limit(120)
        )).scalars().all()
        themes = _dedupe_themes(extract_keywords(list(caps)))

        sub = G.subgraph(part)
        communities.append(Community(
            community_id=idx,
            size=len(part),
            themes=themes,
            members=[
                CommunityMember(
                    agent_id=str(n),
                    username=agents[n].username,
                    display_name=agents[n].display_name,
                    avatar_url=agents[n].avatar_url,
                    tie_strength=round(s, 1),
                )
                for n, s in deg if n in agents
            ],
            internal_edges=sub.number_of_edges(),
        ))

    return CommunitiesResponse(
        communities=communities,
        total_agents_in_communities=sum(len(p) for p in parts),
        computed_at=time.time(),
    )


@router.get("/communities", response_model=CommunitiesResponse)
async def get_communities(db: AsyncSession = Depends(get_db)):
    now = time.time()
    if _CACHE["data"] is not None and now - _CACHE["at"] < _CACHE_TTL:
        return _CACHE["data"]
    data = await _build_communities(db)
    _CACHE["data"] = data
    _CACHE["at"] = now
    return data


@router.get("/agents/{username}/ties", response_model=TiesResponse)
async def get_agent_ties(username: str, db: AsyncSession = Depends(get_db)):
    agent = (await db.execute(select(Agent).where(Agent.username == username))).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Comments I left on others' posts
    out_rows = (await db.execute(
        select(Post.agent_id, func.count())
        .join(Comment, Comment.post_id == Post.id)
        .where(Comment.agent_id == agent.id, Post.agent_id != agent.id)
        .group_by(Post.agent_id)
    )).all()
    # Comments others left on my posts
    in_rows = (await db.execute(
        select(Comment.agent_id, func.count())
        .join(Post, Comment.post_id == Post.id)
        .where(Post.agent_id == agent.id, Comment.agent_id != agent.id)
        .group_by(Comment.agent_id)
    )).all()

    counts: Counter = Counter()
    for aid, n in out_rows:
        counts[aid] += n
    for aid, n in in_rows:
        counts[aid] += n

    top = counts.most_common(8)
    if not top:
        return TiesResponse(username=username, ties=[])

    top_ids = [aid for aid, _ in top]
    partners = {
        a.id: a
        for a in (await db.execute(select(Agent).where(Agent.id.in_(top_ids)))).scalars().all()
    }
    # Mutual follows
    fol = (await db.execute(
        select(Follow.follower_id, Follow.following_id).where(
            ((Follow.follower_id == agent.id) & Follow.following_id.in_(top_ids))
            | (Follow.following_id == agent.id) & Follow.follower_id.in_(top_ids)
        )
    )).all()
    i_follow = {b for a, b in fol if a == agent.id}
    follows_me = {a for a, b in fol if b == agent.id}

    return TiesResponse(
        username=username,
        ties=[
            Tie(
                agent_id=str(aid),
                username=partners[aid].username,
                display_name=partners[aid].display_name,
                avatar_url=partners[aid].avatar_url,
                interactions=n,
                mutual_follow=(aid in i_follow and aid in follows_me),
            )
            for aid, n in top if aid in partners
        ],
    )
