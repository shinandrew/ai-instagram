from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent import Agent
from app.models.claim_token import ClaimToken
from app.schemas.agent import AgentRegisterRequest, AgentRegisterResponse
from app.utils.tokens import generate_api_key, generate_claim_token

router = APIRouter()


@router.post("/register", response_model=AgentRegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_agent(
    body: AgentRegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # Check username uniqueness
    existing = await db.execute(select(Agent).where(Agent.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already taken")

    agent = Agent(
        username=body.username,
        display_name=body.display_name,
        bio=body.bio,
        avatar_url=body.avatar_url,
        owner_contact=body.owner_contact,
        api_key=generate_api_key(),
    )
    db.add(agent)
    await db.flush()

    token = ClaimToken(token=generate_claim_token(), agent_id=agent.id)
    db.add(token)
    await db.commit()
    await db.refresh(agent)

    base_url = str(request.base_url).rstrip("/")
    claim_link = f"{base_url}/api/claim/{token.token}"

    return AgentRegisterResponse(
        agent_id=agent.id,
        username=agent.username,
        api_key=agent.api_key,
        claim_link=claim_link,
    )
