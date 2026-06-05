import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB

from database import Base


class ActionAuditLog(Base):
    __tablename__ = "action_audit_logs"
    __table_args__ = (UniqueConstraint("execution_id", name="uq_action_audit_execution_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    call_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action_name: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_by: Mapped[str] = mapped_column(String(128), nullable=False)
    execution_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
