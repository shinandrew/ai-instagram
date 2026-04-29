import uuid
from datetime import datetime, timezone
from sqlalchemy import Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class AgentMemory(Base):
    __tablename__ = "agent_memories"
    __table_args__ = (
        UniqueConstraint("agent_id", "target_agent_id", name="uq_agent_memory"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # The agent who holds this memory
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # The other agent being remembered
    target_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Newline-separated raw-fact log, newest last, capped at MAX_FACTS lines
    memory_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


MAX_FACTS = 12  # keep at most this many lines per agent-pair


async def append_memory(
    db,
    agent_id: uuid.UUID,
    target_agent_id: uuid.UUID,
    fact: str,
) -> None:
    """Upsert one raw-fact line into the memory record for this agent pair."""
    from sqlalchemy import select

    existing = await db.scalar(
        select(AgentMemory).where(
            AgentMemory.agent_id == agent_id,
            AgentMemory.target_agent_id == target_agent_id,
        )
    )
    if existing:
        lines = [l for l in existing.memory_text.strip().split("\n") if l]
        lines.append(fact)
        lines = lines[-MAX_FACTS:]
        existing.memory_text = "\n".join(lines)
        existing.updated_at = datetime.now(timezone.utc)
    else:
        db.add(AgentMemory(
            agent_id=agent_id,
            target_agent_id=target_agent_id,
            memory_text=fact,
        ))
