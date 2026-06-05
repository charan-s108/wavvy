import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    account_type: Mapped[str] = mapped_column(String(50), default="standard")

    # Fintech account state columns
    account_status: Mapped[str] = mapped_column(String(20), default="active")
    account_locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    account_locked_reason: Mapped[Optional[str]] = mapped_column(Text)
    fraud_hold_active: Mapped[bool] = mapped_column(Boolean, default=False)
    fraud_hold_placed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    kyc_status: Mapped[str] = mapped_column(String(20), default="pending")
    kyc_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    two_fa_last_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    fraud_team_escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    fraud_team_escalated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
