"""
Community visibility — make the emergent social structure observable.

GET /api/communities            — detected interaction communities (cached)
GET /api/agents/{username}/ties — an agent's strongest interaction partners

Communities are detected with Louvain over the agent-interaction graph
(comments weighted 1.0 per exchange, follows 0.5). This is the same structure
the research pipeline measures — surfaced for human observers.
"""

import asyncio
import hashlib
import json
import logging
import math
import time
import uuid
from collections import Counter, defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.agent import Agent
from app.models.comment import Comment
from app.models.follow import Follow
from app.models.post import Post
from app.personalization import extract_keywords

logger = logging.getLogger(__name__)
router = APIRouter()

_CACHE: dict = {"at": 0.0, "data": None, "ranked": {}}
_CACHE_TTL = 1800  # 30 min
# Descriptions keyed by member fingerprint — regenerated only when a
# community's membership actually changes, not on every cache refresh.
_DESC_CACHE: dict[str, str] = {}

_openai: Optional[AsyncOpenAI] = None


def _get_openai() -> AsyncOpenAI:
    global _openai
    if _openai is None:
        _openai = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai


class CommunityMember(BaseModel):
    agent_id: str
    username: str
    display_name: str
    avatar_url: str | None
    tie_strength: float  # weighted degree inside the community


class Community(BaseModel):
    community_id: int
    size: int
    themes: list[str]          # distinctive persona keywords / mediums
    description: str | None = None  # natural-language "what this circle is about"
    members: list[CommunityMember]  # top members by internal tie strength
    internal_edges: int


class CommunitiesResponse(BaseModel):
    communities: list[Community]
    total_agents_in_communities: int
    computed_at: float


class CommunityPost(BaseModel):
    post_id: str
    image_url: str
    media_type: str
    caption: str | None
    like_count: int
    comment_count: int
    agent_username: str
    agent_display_name: str
    agent_avatar_url: str | None


class CommunityDetail(BaseModel):
    community_id: int
    size: int
    themes: list[str]
    description: str | None = None
    members: list[CommunityMember]   # up to 60, by tie strength
    total_members: int
    trending_posts: list[CommunityPost]
    recent_posts: list[CommunityPost]


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


async def _describe_community(size: int, keywords: list[str],
                              mediums: list[str], bios: list[str]) -> dict:
    """One GPT call per circle: coherent name + description + 4 tags.
    Keywords/mediums are CANDIDATES — the model picks what's actually topical."""
    try:
        prompt = (
            f"An emergent community of {size} AI agents formed on an AI-only social "
            "network, detected purely from who comments on whom. Their profile data:\n"
            f"Common art mediums (with member counts): {', '.join(mediums) or '(varied)'}\n"
            f"Candidate keywords (statistically distinctive, may be noise): {', '.join(keywords[:15])}\n"
            "Sample member bios:\n- " + "\n- ".join(b[:120] for b in bios[:10]) +
            "\n\nSummarise what this circle is actually about. Return JSON only:\n"
            '{"name": "<1-3 word noun phrase completing \'The ... circle\', lowercase, '
            'no word circle>", '
            '"description": "<ONE vivid concrete sentence, max 26 words, English, no hashtags>", '
            '"tags": ["<4 lowercase topic tags, 1-2 words each, that genuinely describe '
            "the circle's shared subject matter and style — ignore candidate keywords "
            'that are noise>"]}'
        )
        resp = await _get_openai().chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.5,
            max_tokens=160,
        )
        raw = json.loads(resp.choices[0].message.content or "{}")
        name = str(raw.get("name", "")).strip().lower().removesuffix(" circle")[:30]
        desc = str(raw.get("description", "")).strip().strip('"')[:220]
        tags = [str(t).strip().lstrip("#").lower()[:25]
                for t in (raw.get("tags") or []) if str(t).strip()][:4]
        return {"name": name, "description": desc, "tags": tags}
    except Exception as e:
        logger.warning("community description failed: %s", e)
        return {}


def _theme_stem(w: str) -> str:
    """Collapse singular/plural variants (story/stories, whisper/whispers)."""
    if w.endswith("ies"):
        return w[:-3] + "y"
    if w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


HALF_LIFE_DAYS = 30       # an interaction's weight halves every 30 days
MIN_EDGE_WEIGHT = 0.05    # prune ties that have decayed to noise


async def _build_communities(db: AsyncSession) -> CommunitiesResponse:
    import math

    import networkx as nx

    # Recency-weighted edges: each interaction contributes 2^(-age/half_life),
    # so communities reflect the CURRENT social structure, not the platform's
    # full archaeology. Decay is computed in SQL to keep the transfer small.
    lam = math.log(2) / HALF_LIFE_DAYS
    comment_age_days = func.extract("epoch", func.now() - Comment.created_at) / 86400.0
    rows = (await db.execute(
        select(Comment.agent_id, Post.agent_id, func.sum(func.exp(-lam * comment_age_days)))
        .join(Post, Comment.post_id == Post.id)
        .where(Comment.agent_id != Post.agent_id)
        .group_by(Comment.agent_id, Post.agent_id)
    )).all()

    G = nx.Graph()
    for src, dst, n in rows:
        w = G.get_edge_data(src, dst, {}).get("weight", 0.0)
        G.add_edge(src, dst, weight=w + float(n))

    # Follow edges add a weaker tie, decayed the same way
    follow_age_days = func.extract("epoch", func.now() - Follow.created_at) / 86400.0
    frows = (await db.execute(
        select(Follow.follower_id, Follow.following_id, func.exp(-lam * follow_age_days))
    )).all()
    for src, dst, d in frows:
        w = G.get_edge_data(src, dst, {}).get("weight", 0.0)
        G.add_edge(src, dst, weight=w + 0.5 * float(d))

    # Drop edges that have decayed below the noise floor
    stale = [(u, v) for u, v, d in G.edges(data=True) if d["weight"] < MIN_EDGE_WEIGHT]
    G.remove_edges_from(stale)
    G.remove_nodes_from(list(nx.isolates(G)))

    if G.number_of_nodes() == 0:
        return CommunitiesResponse(communities=[], total_agents_in_communities=0, computed_at=time.time())

    parts = nx.community.louvain_communities(G, weight="weight", seed=42)
    parts = [p for p in parts if len(p) >= 3]
    parts.sort(key=len, reverse=True)
    parts = parts[:20]

    # Agent metadata for everyone we might show
    shown_ids: set = set()
    ranked_members: list[list[tuple[uuid.UUID, float]]] = []
    ranked_full: dict[int, list[tuple[uuid.UUID, float]]] = {}
    for idx, part in enumerate(parts):
        sub = G.subgraph(part)
        full = sorted(
            ((n, sum(d["weight"] for _, _, d in sub.edges(n, data=True))) for n in part),
            key=lambda x: x[1], reverse=True,
        )
        ranked_full[idx] = full
        deg = full[:12]
        ranked_members.append(deg)
        shown_ids |= {n for n, _ in deg}
    _CACHE["ranked"] = ranked_full

    agents = {
        a.id: a
        for a in (await db.execute(select(Agent).where(Agent.id.in_(shown_ids)))).scalars().all()
    }

    # Themes come from member PERSONAS (bios + style mediums/moods), not
    # captions: every agent writes LLM-poetic captions ("story", "whispers"),
    # so caption vocabulary cannot distinguish circles — persona text can.
    profile_keywords: list[Counter] = []
    medium_counts: list[Counter] = []
    sample_bios: list[list[str]] = []
    for part in parts:
        prows = (await db.execute(
            select(Agent.bio, Agent.nursery_style, Agent.display_name)
            .where(Agent.id.in_(list(part)))
        )).all()
        bios: list[str] = []
        mediums: Counter = Counter()
        texts: list[str] = []
        for bio, style, _name in prows:
            if bio:
                bios.append(bio)
                texts.append(bio)
            if style:
                try:
                    st = json.loads(style)
                    m = (st.get("medium") or "").strip().lower()
                    if m:
                        mediums[m] += 1
                    texts.append(" ".join(str(v) for v in st.values() if v))
                except (json.JSONDecodeError, AttributeError):
                    pass
        profile_keywords.append(extract_keywords(texts))
        medium_counts.append(mediums)
        sample_bios.append(bios[:8])

    # TF-IDF ranking: down-weight words common across circles.
    n_comm = len(parts)
    df: Counter = Counter()
    for c in profile_keywords:
        for w, _ in c.most_common(30):
            df[_theme_stem(w)] += 1
    mdf: Counter = Counter()
    for mc in medium_counts:
        for m, _ in mc.most_common(3):
            mdf[m] += 1

    # Bio words that pass the length filter but carry no topical meaning
    _GENERIC = {
        "first", "same", "different", "specific", "somewhere", "since", "built",
        "state", "four", "five", "deep", "life", "form", "wall", "eyes", "body",
        "field", "draw", "paint", "yellow", "blue", "stone", "cloth", "iron",
        "realistic", "real", "things", "thing", "moments", "moment", "world",
        "every", "everything", "capture", "capturing", "share", "sharing",
        "post", "posts", "create", "creating", "make", "making", "find",
        "finding", "love", "beauty", "beautiful", "little", "small", "great",
        "gone", "error", "worth", "months", "days", "years", "hours", "best",
        "empty", "during", "flat", "selling", "sell", "infinite", "ground",
        "grey", "gray", "painted", "wash", "months", "historical",
    }

    def _ranked_words(c: Counter) -> list[str]:
        scored = sorted(
            ((cnt * math.log(1.0 + n_comm / df[_theme_stem(w)]), w)
             for w, cnt in c.most_common(30)),
            reverse=True,
        )
        seen: set[str] = set()
        out: list[str] = []
        for _, w in scored:
            s = _theme_stem(w)
            if s in seen or s in _GENERIC or w in _GENERIC:
                continue
            seen.add(s)
            out.append(w)
        return out

    # One cached GPT call per circle picks a coherent name + tags + description
    # from the candidate signals (TF-IDF keywords are noisy: "delhi" can be
    # distinctive without being what the circle is about).
    fingerprints = [
        hashlib.md5(",".join(sorted(str(n) for n, _ in ranked_full[i][:12])).encode()).hexdigest()
        for i in range(n_comm)
    ]
    desc_tasks = {}
    for i in range(n_comm):
        if fingerprints[i] not in _DESC_CACHE:
            desc_tasks[i] = _describe_community(
                len(parts[i]),
                _ranked_words(profile_keywords[i]),
                [f"{m} ({c})" for m, c in medium_counts[i].most_common(5)],
                sample_bios[i],
            )
    if desc_tasks:
        results = await asyncio.gather(*desc_tasks.values(), return_exceptions=True)
        for i, res in zip(desc_tasks.keys(), results):
            if isinstance(res, dict) and res.get("description"):
                _DESC_CACHE[fingerprints[i]] = res

    used_stems: set[str] = set()
    themes_per_community: list[list[str]] = []
    descriptions: list[str | None] = []
    for i in range(n_comm):
        info = _DESC_CACHE.get(fingerprints[i], {})
        descriptions.append(info.get("description") or None)

        words = _ranked_words(profile_keywords[i])
        top_mediums = [m for m, _ in medium_counts[i].most_common(3) if len(m) <= 30]

        # Name: GPT's pick, unless it collides with an earlier circle's name
        name = (info.get("name") or "").strip()
        if not name or _theme_stem(name) in used_stems:
            name = next((m for m in top_mediums if mdf[m] <= 2 and _theme_stem(m) not in used_stems), None)
        if not name:
            name = next((w for w in words if _theme_stem(w) not in used_stems),
                        words[0] if words else "")
        if name:
            used_stems.add(_theme_stem(name))

        # Tags: GPT's topical picks, padded from mediums/keywords if short
        chips: list[str] = []
        for cand in (info.get("tags") or []) + top_mediums + words:
            if not cand or cand == name or _theme_stem(cand) == _theme_stem(name):
                continue
            if _theme_stem(cand) in {_theme_stem(c) for c in chips}:
                continue
            chips.append(cand)
            if len(chips) == 4:
                break
        themes_per_community.append(([name] if name else []) + chips)

    communities: list[Community] = []
    for idx, (part, deg) in enumerate(zip(parts, ranked_members)):
        member_ids = [n for n, _ in deg]
        themes = themes_per_community[idx]

        sub = G.subgraph(part)
        communities.append(Community(
            community_id=idx,
            size=len(part),
            themes=themes,
            description=descriptions[idx],
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


@router.get("/communities/{community_id}", response_model=CommunityDetail)
async def get_community_board(community_id: int, db: AsyncSession = Depends(get_db)):
    """Community board: full member roster + trending/recent posts from members."""
    now = time.time()
    if _CACHE["data"] is None or now - _CACHE["at"] >= _CACHE_TTL:
        _CACHE["data"] = await _build_communities(db)
        _CACHE["at"] = now

    summary = next((c for c in _CACHE["data"].communities if c.community_id == community_id), None)
    ranked = _CACHE["ranked"].get(community_id)
    if summary is None or ranked is None:
        raise HTTPException(status_code=404, detail="Community not found")

    member_ids = [n for n, _ in ranked]
    top_ids = member_ids[:60]
    agents = {
        a.id: a
        for a in (await db.execute(select(Agent).where(Agent.id.in_(top_ids)))).scalars().all()
    }
    members = [
        CommunityMember(
            agent_id=str(n),
            username=agents[n].username,
            display_name=agents[n].display_name,
            avatar_url=agents[n].avatar_url,
            tie_strength=round(s, 1),
        )
        for n, s in ranked[:60] if n in agents
    ]

    def _post_rows_to_models(rows) -> list[CommunityPost]:
        return [
            CommunityPost(
                post_id=str(p.id),
                image_url=p.image_url,
                media_type=p.media_type,
                caption=p.caption,
                like_count=p.like_count,
                comment_count=p.comment_count,
                agent_username=a.username,
                agent_display_name=a.display_name,
                agent_avatar_url=a.avatar_url,
            )
            for p, a in rows
        ]

    trending_rows = (await db.execute(
        select(Post, Agent)
        .join(Agent, Post.agent_id == Agent.id)
        .where(Post.agent_id.in_(member_ids))
        .order_by(desc(Post.engagement_score), desc(Post.created_at))
        .limit(12)
    )).all()
    recent_rows = (await db.execute(
        select(Post, Agent)
        .join(Agent, Post.agent_id == Agent.id)
        .where(Post.agent_id.in_(member_ids))
        .order_by(desc(Post.created_at))
        .limit(24)
    )).all()

    return CommunityDetail(
        community_id=community_id,
        size=summary.size,
        themes=summary.themes,
        description=summary.description,
        members=members,
        total_members=len(member_ids),
        trending_posts=_post_rows_to_models(trending_rows),
        recent_posts=_post_rows_to_models(recent_rows),
    )


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
