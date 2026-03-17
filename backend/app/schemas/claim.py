import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr


class ClaimTokenInfo(BaseModel):
    agent_id: uuid.UUID
    username: str
    display_name: str
    is_used: bool
    expires_at: datetime


class ClaimVerifyRequest(BaseModel):
    email: EmailStr


class ClaimVerifyResponse(BaseModel):
    success: bool
    session_key: str
    agent_id: uuid.UUID
