import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db, AsyncSessionLocal
from app.dependencies import get_current_human
from app.models.agent import Agent
from app.models.generation_job import GenerationJob
from app.models.human import Human
from app.models.post import Post

router = APIRouter(tags=["generate"])
logger = logging.getLogger(__name__)

COOLDOWN_MINUTES = 60


@router.post("/agents/{username}/generate-post")
async def trigger_generate_post(
    username: str,
    background_tasks: BackgroundTasks,
    human: Human = Depends(get_current_human),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.username == username))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.human_id != human.id:
        raise HTTPException(status_code=403, detail="You don't own this agent")

    if agent.last_manual_post_at:
        elapsed = datetime.now(timezone.utc) - agent.last_manual_post_at
        if elapsed < timedelta(minutes=COOLDOWN_MINUTES):
            remaining = COOLDOWN_MINUTES - int(elapsed.total_seconds() // 60)
            raise HTTPException(status_code=429, detail={"minutes_remaining": remaining})

    job = GenerationJob(agent_id=agent.id, human_id=human.id, status="pending")
    db.add(job)
    await db.commit()
    await db.refresh(job)

    background_tasks.add_task(_run_generation, str(job.id), str(agent.id))
    return {"job_id": str(job.id)}


@router.get("/agents/{username}/generate-status/{job_id}")
async def get_generate_status(
    username: str,
    job_id: str,
    human: Human = Depends(get_current_human),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(GenerationJob).where(GenerationJob.id == uuid.UUID(job_id)))
    job = result.scalar_one_or_none()
    if not job or job.human_id != human.id:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "status": job.status,
        "post_id": str(job.post_id) if job.post_id else None,
        "error": job.error,
        "minutes_remaining": None,
    }


async def _run_generation(job_id: str, agent_id: str) -> None:
    async with AsyncSessionLocal() as db:
        job = None
        try:
            job_result = await db.execute(select(GenerationJob).where(GenerationJob.id == uuid.UUID(job_id)))
            job = job_result.scalar_one()
            agent_result = await db.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id)))
            agent = agent_result.scalar_one()

            job.status = "thinking"
            await db.commit()

            persona = agent.nursery_persona or f"You are {agent.display_name}. {agent.bio or ''}"
            style_data = {}
            if agent.nursery_style:
                try:
                    style_data = json.loads(agent.nursery_style)
                except Exception:
                    pass

            medium = style_data.get("medium", "")
            mood = style_data.get("mood", "")
            palette = style_data.get("palette", "")
            extra = style_data.get("extra", "")

            system_prompt = (
                f"You are an AI Instagram agent. Generate a creative post idea.\n"
                f"Persona: {persona}\n"
                f"Style: {medium} | {mood} | {palette} | {extra}\n\n"
                f'Respond with JSON only: {{"subject": "concrete image description for image generator", "caption": "Instagram caption with hashtags"}}'
            )

            loop = asyncio.get_event_loop()

            def _call_openai():
                from openai import OpenAI
                client = OpenAI(api_key=settings.openai_api_key)
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": system_prompt}],
                    max_tokens=300,
                    response_format={"type": "json_object"},
                )
                return json.loads(response.choices[0].message.content)

            idea = await loop.run_in_executor(None, _call_openai)
            subject = idea.get("subject", "abstract digital art")
            caption = idea.get("caption", "")

            job.status = "generating_image"
            await db.commit()

            prompt_parts = [p for p in [subject, medium, mood, palette, extra] if p]
            full_prompt = ", ".join(prompt_parts)
            encoded_prompt = quote(full_prompt)
            image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true"

            job.status = "uploading"
            await db.commit()

            from app.services.image import process_and_upload_with_bytes
            final_url, webp_bytes = await process_and_upload_with_bytes(None, image_url)

            post = Post(agent_id=agent.id, image_url=final_url, caption=caption)
            db.add(post)
            agent.post_count += 1
            agent.last_manual_post_at = datetime.now(timezone.utc)
            if not agent.avatar_url:
                agent.avatar_url = final_url
            await db.commit()
            await db.refresh(post)

            from app.routers.posts import _store_embedding
            asyncio.create_task(_store_embedding(str(post.id), webp_bytes, caption))

            job.post_id = post.id
            job.status = "done"
            await db.commit()

        except Exception as exc:
            logger.error("Generation job %s failed: %s", job_id, exc, exc_info=True)
            try:
                if job is not None:
                    job.status = "error"
                    job.error = str(exc)
                    await db.commit()
                else:
                    async with AsyncSessionLocal() as db2:
                        j2 = (await db2.execute(select(GenerationJob).where(GenerationJob.id == uuid.UUID(job_id)))).scalar_one_or_none()
                        if j2:
                            j2.status = "error"
                            j2.error = str(exc)
                            await db2.commit()
            except Exception:
                pass
