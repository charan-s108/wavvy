import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Integer, Float, Text, ForeignKey, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from database import Base


class EvalScore(Base):
    __tablename__ = "eval_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calls.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_profiles.id"), index=True
    )
    guardrail_adherence: Mapped[Optional[int]] = mapped_column(Integer)
    resolution_rate: Mapped[Optional[int]] = mapped_column(Integer)
    containment: Mapped[Optional[int]] = mapped_column(Integer)
    caller_satisfaction: Mapped[Optional[float]] = mapped_column(Float)
    handle_time_score: Mapped[Optional[int]] = mapped_column(Integer)
    disclosure_score: Mapped[Optional[int]] = mapped_column(Integer)
    overall_score: Mapped[Optional[int]] = mapped_column(Integer)
    pass_fail: Mapped[Optional[str]] = mapped_column(String(4))
    violations: Mapped[list] = mapped_column(JSON, default=list)
    coaching_note: Mapped[Optional[str]] = mapped_column(Text)
    strengths: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
