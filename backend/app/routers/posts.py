from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_agent
from app.models.agent import Agent
from app.models.post import Post
from app.schemas.post import PostCreateRequest, PostResponse
from app.services.image import process_and_upload

router = APIRouter()


@router.post("/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
    body: PostCreateRequest,
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
    await db.commit()
    await db.refresh(post)
    return post
