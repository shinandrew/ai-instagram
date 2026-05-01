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
    from app.services.embeddings import describe_image_bytes, embed_text

    embedding = None

    # Primary: GPT-4o-mini visual description → embedding
    if image_bytes:
        description = describe_image_bytes(image_bytes, settings.openai_api_key)
        if description:
            embedding = embed_text(description, settings.openai_api_key)
            if embedding:
                logger.info("Stored vision embedding for post %s", post_id)

    # Fallback: caption text embedding
    if embedding is None and caption:
        embedding = embed_text(caption, settings.openai_api_key)
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


@router.post("/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
    body: PostCreateRequest,
    background_tasks: BackgroundTasks,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    if not body.image_base64 and not body.image_url:
        raise HTTPException(status_code=400, detail="Provide image_base64 or image_url")

    try:
        image_url, webp_bytes = await process_and_upload_with_bytes(body.image_base64, body.image_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as exc:
        logger.warning("Image processing failed for agent %s: %r", agent.username, exc)
        raise HTTPException(status_code=502, detail="Image processing failed")

    post = Post(
        agent_id=agent.id,
        image_url=image_url,
        caption=body.caption,
    )
    db.add(post)
    agent.post_count += 1
    if not agent.avatar_url:
        agent.avatar_url = image_url
    await db.commit()
    await db.refresh(post)

    # Vision-describe + embed in background — bytes in memory, no R2 fetch needed
    background_tasks.add_task(
        _store_embedding,
        str(post.id),
        webp_bytes,
        body.caption or "",
    )

    return post
