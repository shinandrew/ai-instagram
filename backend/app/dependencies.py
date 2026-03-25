from fastapi import Header, HTTPException, status, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent import Agent


async def get_current_agent(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> Agent:
    result = await db.execute(select(Agent).where(Agent.api_key == x_api_key))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return agent


async def get_current_agent_optional(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> Agent | None:
    """Like get_current_agent but returns None instead of 401 when no key provided."""
    if not x_api_key:
        return None
    result = await db.execute(select(Agent).where(Agent.api_key == x_api_key))
    return result.scalar_one_or_none()


async def get_current_human(
    x_human_token: str = Header(..., alias="X-Human-Token"),
    db: AsyncSession = Depends(get_db),
):
    from app.models.human import Human
    try:
        import uuid as _uuid
        token = _uuid.UUID(x_human_token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid human token",
        )
    result = await db.execute(select(Human).where(Human.human_token == token))
    human = result.scalar_one_or_none()
    if human is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid human token",
        )
    return human
