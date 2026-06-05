import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Boolean, Integer, Text, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from database import Base


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), index=True
    )
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_profiles.id"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_secs: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    call_type: Mapped[Optional[str]] = mapped_column(String(20))  # voice_ai | escalated | agent_direct
    resolution: Mapped[Optional[str]] = mapped_column(String(20))  # resolved | escalated | unresolved
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    escalation_reason: Mapped[Optional[str]] = mapped_column(String(100))
    escalation_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    voice_ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    acw_summary: Mapped[Optional[str]] = mapped_column(Text)
    crm_updated: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    customer_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    customer_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feedback_submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
