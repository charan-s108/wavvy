"""Add tenant_configs table

Revision ID: 007
Revises: 006
Create Date: 2026-05-26
"""
from typing import Sequence, Union

from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS tenant_configs (
            id                        UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id                 VARCHAR(100) UNIQUE NOT NULL,
            agent_name                VARCHAR(100) NOT NULL,
            industry                  VARCHAR(100),

            voice_system_prompt       TEXT NOT NULL,
            context_prompt            TEXT NOT NULL,
            companion_mid_call_prompt TEXT,
            companion_acw_prompt      TEXT,
            qa_prompt                 TEXT,
            coaching_prompt           TEXT,

            tool_configs              JSONB DEFAULT '{}',
            workflow_configs          JSONB DEFAULT '{}',
            kb_collections            JSONB DEFAULT '[]',

            escalation_reasons        JSONB DEFAULT '[]',
            support_categories        JSONB DEFAULT '[]',

            is_active                 BOOLEAN DEFAULT TRUE,
            created_at                TIMESTAMPTZ DEFAULT NOW(),
            updated_at                TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tenant_configs_active "
        "ON tenant_configs(is_active) WHERE is_active = TRUE"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_configs CASCADE")
