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
from app.services.image import process_and_upload

router = APIRouter()
logger = logging.getLogger(__name__)


async def _generate_and_store_embedding(post_id: str, image_url: str) -> None:
    """Background task: describe image → embed → store."""
    if not settings.openai_api_key:
        return
    from app.services.embeddings import image_to_embedding
    try:
        embedding = image_to_embedding(image_url, settings.openai_api_key)
        if embedding is None:
            return
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Post).where(Post.id == post_id))
            post = result.scalar_one_or_none()
            if post:
                post.image_embedding = embedding
                await db.commit()
                logger.info("Stored embedding for post %s", post_id)
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
        image_url = await process_and_upload(body.image_base64, body.image_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=502, detail="Image processing failed")

    post = Post(
        agent_id=agent.id,
        image_url=image_url,
        caption=body.caption,
    )
    db.add(post)
    agent.post_count += 1
    # Use first post image as avatar — it's already in R2, always fast and reliable
    if not agent.avatar_url:
        agent.avatar_url = image_url
    await db.commit()
    await db.refresh(post)

    # Generate image embedding asynchronously — doesn't block the response
    background_tasks.add_task(
        _generate_and_store_embedding,
        str(post.id),
        image_url,
    )

    return post
