"""Add action_audit_logs table for orchestration HITL audit trail

Revision ID: 008
Revises: 007
Create Date: 2026-05-28
"""
from typing import Sequence, Union

from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS action_audit_logs (
            id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            call_id      VARCHAR(64)  NOT NULL,
            action_name  VARCHAR(64)  NOT NULL,
            approved_by  VARCHAR(128) NOT NULL,
            execution_id VARCHAR(64)  NOT NULL,
            payload      JSONB        NOT NULL DEFAULT '{}',
            result       JSONB        NOT NULL DEFAULT '{}',
            success      BOOLEAN      NOT NULL DEFAULT TRUE,
            created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_action_audit_execution_id UNIQUE (execution_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_action_audit_logs_call_id
            ON action_audit_logs(call_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_action_audit_logs_created_at
            ON action_audit_logs(created_at)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS action_audit_logs;")
