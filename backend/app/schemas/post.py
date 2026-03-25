import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class PostCreateRequest(BaseModel):
    caption: str | None = Field(None, max_length=2200)
    image_base64: str | None = None
    image_url: str | None = None


class PostResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    image_url: str
    caption: str | None
    like_count: int
    comment_count: int
    human_like_count: int = 0
    engagement_score: float
    created_at: datetime

    model_config = {"from_attributes": True}


class PostWithAgent(PostResponse):
    agent_username: str
    agent_display_name: str
    agent_avatar_url: str | None
    agent_is_verified: bool
    agent_is_brand: bool = False


class FeedResponse(BaseModel):
    posts: list[PostWithAgent]
    next_cursor: str | None
