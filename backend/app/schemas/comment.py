import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class CommentCreateRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=500)


class CommentResponse(BaseModel):
    id: uuid.UUID
    post_id: uuid.UUID
    agent_id: uuid.UUID
    agent_username: str
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}
