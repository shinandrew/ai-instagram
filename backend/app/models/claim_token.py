import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


def _expires_at() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=7)


class ClaimToken(Base):
    __tablename__ = "claim_tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_expires_at
    )

    agent: Mapped["Agent"] = relationship("Agent", back_populates="claim_tokens")
