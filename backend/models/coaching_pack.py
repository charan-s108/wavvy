import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Integer, ForeignKey, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from database import Base


class CoachingPack(Base):
    __tablename__ = "coaching_packs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_profiles.id")
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    calls_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    overall_trend: Mapped[Optional[str]] = mapped_column(String(20))
    strengths: Mapped[list] = mapped_column(JSON, default=list)
    improvements: Mapped[list] = mapped_column(JSON, default=list)
    action_items: Mapped[list] = mapped_column(JSON, default=list)
    score_summary: Mapped[dict] = mapped_column(JSON, default=dict)
