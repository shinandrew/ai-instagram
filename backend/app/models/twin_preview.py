import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class TwinPreview(Base):
    """An unclaimed twin persona generated before sign-up (funnel inversion).

    Created by the public preview endpoint; converted into a real Agent when
    the visitor signs in and claims it. Expires if never claimed.
    """

    __tablename__ = "twin_previews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="twitter")
    handle: Mapped[str] = mapped_column(String(100), nullable=False)
    persona_json: Mapped[str] = mapped_column(Text, nullable=False)  # persona dict as JSON
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    sample_caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    sample_subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")

    # Friend-twin invite: the agent whose owner shared the invite link
    invited_by_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )

    # Set once claimed — prevents double-claiming
    claimed_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
