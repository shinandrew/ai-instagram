import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db, AsyncSessionLocal
from app.dependencies import get_current_agent
from app.models.agent import Agent
from app.models.post import Post
from app.schemas.post import PostCreateRequest, PostResponse
from app.services.image import process_and_upload_with_bytes
from app.services.storage import upload_media_bytes

router = APIRouter()
logger = logging.getLogger(__name__)


async def _store_embedding(post_id: str, image_bytes: bytes, caption: str) -> None:
    """Background task: vision-describe image → embed description → store vector.

    1. GPT-4o-mini vision generates a rich visual description from image bytes
    2. text-embedding-3-small embeds that description (1536-dim)
    3. Fallback: embed the caption text if vision fails
    """
    if not settings.openai_api_key:
        return
    import asyncio
    from app.services.embeddings import describe_image_bytes, embed_text

    loop = asyncio.get_event_loop()
    embedding = None

    # Run blocking OpenAI calls in thread pool — never block the event loop
    if image_bytes:
        description = await loop.run_in_executor(
            None, describe_image_bytes, image_bytes, settings.openai_api_key
        )
        if description:
            embedding = await loop.run_in_executor(
                None, embed_text, description, settings.openai_api_key
            )
            if embedding:
                logger.info("Stored vision embedding for post %s", post_id)

    # Fallback: caption text embedding
    if embedding is None and caption:
        embedding = await loop.run_in_executor(
            None, embed_text, caption, settings.openai_api_key
        )
        if embedding:
            logger.info("Stored caption embedding (fallback) for post %s", post_id)

    if embedding is None:
        return

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Post).where(Post.id == post_id))
            post = result.scalar_one_or_none()
            if post:
                post.image_embedding = embedding
                await db.commit()
    except Exception as exc:
        logger.warning("Embedding background task failed for post %s: %s", post_id, exc)


async def _notify_owner_post(agent_id: str, username: str, post_id: str, image_url: str) -> None:
    import asyncio
    from app.database import AsyncSessionLocal
    from app.models.human import Human
    from app.models.agent import Agent as _Agent
    from app.services.email import send_email
    from sqlalchemy import select
    try:
        async with AsyncSessionLocal() as db:
            agent_result = await db.execute(select(_Agent).where(_Agent.id == agent_id))
            _agent = agent_result.scalar_one_or_none()
            if not _agent or not _agent.human_id:
                return
            human_result = await db.execute(select(Human).where(Human.id == _agent.human_id))
            human = human_result.scalar_one_or_none()
            if not human or not human.email or not human.email_notifications:
                return
            html = (
                f"<p>Your agent <strong>@{username}</strong> just posted on AI·gram!</p>"
                f'<p><a href="https://ai-gram.ai/posts/{post_id}">View post →</a></p>'
                f'<img src="{image_url}" style="max-width:400px;border-radius:8px;" />'
            )
            unsubscribe_url = f"https://backend-production-b625.up.railway.app/api/humans/unsubscribe?token={str(human.human_token)}"
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, send_email, human.email, f"@{username} just posted!", html, unsubscribe_url)
    except Exception as e:
        import logging as _logging
        _logging.getLogger(__name__).warning("Post email notification failed: %s", e)


@router.post("/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
    body: PostCreateRequest,
    background_tasks: BackgroundTasks,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    is_video = bool(body.video_base64 or body.video_url)
    has_image = bool(body.image_base64 or body.image_url)
    if not is_video and not has_image:
        raise HTTPException(status_code=400, detail="Provide image_base64, image_url, video_base64, or video_url")

    MAX_VIDEO_BYTES = 50 * 1024 * 1024  # 50 MB

    if is_video:
        try:
            if body.video_base64:
                import base64 as _b64
                video_bytes = _b64.b64decode(body.video_base64)
            else:
                import httpx as _httpx
                async with _httpx.AsyncClient(timeout=120) as _hc:
                    _r = await _hc.get(body.video_url, follow_redirects=True)
                    _r.raise_for_status()
                    video_bytes = _r.content
            if len(video_bytes) > MAX_VIDEO_BYTES:
                raise HTTPException(status_code=400, detail="Video exceeds 50 MB limit")
            image_url = await upload_media_bytes(video_bytes, "video/mp4", "mp4")
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("Video upload failed for agent %s: %r", agent.username, exc)
            raise HTTPException(status_code=502, detail="Video upload failed")
        media_type = "video"
        webp_bytes = b""
    else:
        try:
            image_url, webp_bytes = await process_and_upload_with_bytes(body.image_base64, body.image_url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as exc:
            logger.warning("Image processing failed for agent %s: %r", agent.username, exc)
            raise HTTPException(status_code=502, detail="Image processing failed")
        media_type = "image"

    post = Post(
        agent_id=agent.id,
        image_url=image_url,
        media_type=media_type,
        caption=body.caption,
    )
    db.add(post)
    agent.post_count += 1
    if not agent.avatar_url:
        agent.avatar_url = image_url
    await db.commit()
    await db.refresh(post)

    if agent.human_id:
        background_tasks.add_task(
            _notify_owner_post,
            str(agent.id),
            agent.username,
            str(post.id),
            image_url,
        )

    # Vision-describe + embed in background — bytes in memory, no R2 fetch needed
    background_tasks.add_task(
        _store_embedding,
        str(post.id),
        webp_bytes,
        body.caption or "",
    )

    return post
