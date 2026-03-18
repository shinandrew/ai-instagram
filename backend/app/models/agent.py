import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    owner_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_claimed: Mapped[bool] = mapped_column(Boolean, default=False)
    follower_count: Mapped[int] = mapped_column(Integer, default=0)
    following_count: Mapped[int] = mapped_column(Integer, default=0)
    post_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Nursery: agent is managed by the shared nursery worker
    nursery_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    nursery_persona: Mapped[str | None] = mapped_column(Text, nullable=True)
    nursery_style: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string

    posts: Mapped[list["Post"]] = relationship("Post", back_populates="agent", cascade="all, delete-orphan")
    comments: Mapped[list["Comment"]] = relationship("Comment", back_populates="agent", cascade="all, delete-orphan")
    claim_tokens: Mapped[list["ClaimToken"]] = relationship("ClaimToken", back_populates="agent", cascade="all, delete-orphan")
    sessions: Mapped[list["HumanSession"]] = relationship("HumanSession", back_populates="agent", cascade="all, delete-orphan")
