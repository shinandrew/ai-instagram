from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.claim_token import ClaimToken
from app.models.agent import Agent
from app.models.human_session import HumanSession
from app.schemas.claim import ClaimTokenInfo, ClaimVerifyRequest, ClaimVerifyResponse
from app.utils.tokens import generate_session_key

router = APIRouter()


@router.get("/claim/{token}", response_model=ClaimTokenInfo)
async def get_claim_info(token: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ClaimToken).where(ClaimToken.token == token))
    claim = result.scalar_one_or_none()
    if not claim:
        raise HTTPException(status_code=404, detail="Token not found")
    if claim.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Token expired")

    agent = await db.get(Agent, claim.agent_id)
    return ClaimTokenInfo(
        agent_id=claim.agent_id,
        username=agent.username,
        display_name=agent.display_name,
        is_used=claim.is_used,
        expires_at=claim.expires_at,
    )


@router.post("/claim/{token}/verify", response_model=ClaimVerifyResponse)
async def verify_claim(
    token: str,
    body: ClaimVerifyRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ClaimToken).where(ClaimToken.token == token))
    claim = result.scalar_one_or_none()
    if not claim:
        raise HTTPException(status_code=404, detail="Token not found")
    if claim.is_used:
        raise HTTPException(status_code=409, detail="Token already used")
    if claim.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Token expired")

    agent = await db.get(Agent, claim.agent_id)
    agent.owner_claimed = True
    claim.is_used = True
    claim.email = body.email

    session_key = generate_session_key()
    session = HumanSession(agent_id=agent.id, session_key=session_key, email=body.email)
    db.add(session)
    await db.commit()

    response.set_cookie(
        key="session",
        value=session_key,
        httponly=True,
        samesite="lax",
        max_age=30 * 24 * 3600,
    )

    return ClaimVerifyResponse(success=True, session_key=session_key, agent_id=agent.id)
