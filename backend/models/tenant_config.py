import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import String, Text, Boolean, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class TenantConfig(Base):
    __tablename__ = "tenant_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    industry: Mapped[Optional[str]] = mapped_column(String(100))

    voice_system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    context_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    companion_mid_call_prompt: Mapped[Optional[str]] = mapped_column(Text)
    companion_acw_prompt: Mapped[Optional[str]] = mapped_column(Text)
    qa_prompt: Mapped[Optional[str]] = mapped_column(Text)
    coaching_prompt: Mapped[Optional[str]] = mapped_column(Text)

    tool_configs: Mapped[dict] = mapped_column(JSONB, default=dict)
    workflow_configs: Mapped[dict] = mapped_column(JSONB, default=dict)
    kb_collections: Mapped[list] = mapped_column(JSONB, default=list)

    escalation_reasons: Mapped[list] = mapped_column(JSONB, default=list)
    support_categories: Mapped[list] = mapped_column(JSONB, default=list)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class TenantConfigMeta(BaseModel):
    """Public-safe view — no prompts."""
    tenant_id: str
    agent_name: str
    industry: Optional[str]
    tool_configs: dict
    workflow_configs: dict
    kb_collections: list
    escalation_reasons: list
    support_categories: list
    is_active: bool
    updated_at: datetime

    class Config:
        from_attributes = True


class TenantConfigFull(TenantConfigMeta):
    """Admin view — includes all prompts."""
    voice_system_prompt: str
    context_prompt: str
    companion_mid_call_prompt: Optional[str]
    companion_acw_prompt: Optional[str]
    qa_prompt: Optional[str]
    coaching_prompt: Optional[str]


class TenantConfigUpdate(BaseModel):
    """Partial update — all fields optional."""
    agent_name: Optional[str] = None
    industry: Optional[str] = None
    voice_system_prompt: Optional[str] = None
    context_prompt: Optional[str] = None
    companion_mid_call_prompt: Optional[str] = None
    companion_acw_prompt: Optional[str] = None
    qa_prompt: Optional[str] = None
    coaching_prompt: Optional[str] = None
    tool_configs: Optional[dict] = None
    workflow_configs: Optional[dict] = None
    kb_collections: Optional[list] = None
    escalation_reasons: Optional[list] = None
    support_categories: Optional[list] = None
