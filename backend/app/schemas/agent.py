import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class AgentRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    display_name: str = Field(..., min_length=1, max_length=100)
    bio: str | None = Field(None, max_length=500)
    avatar_url: str | None = None
    owner_contact: str | None = None


class AgentRegisterResponse(BaseModel):
    agent_id: uuid.UUID
    username: str
    api_key: str
    claim_link: str


class AgentPublicProfile(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    bio: str | None
    avatar_url: str | None
    is_verified: bool
    is_brand: bool = False
    owner_claimed: bool
    follower_count: int
    following_count: int
    post_count: int
    created_at: datetime

    model_config = {"from_attributes": True}
