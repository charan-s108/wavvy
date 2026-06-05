"""Add confirmed_time to demo_appointments

Revision ID: 003
Revises: 002
Create Date: 2026-05-20
"""
from typing import Sequence, Union
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE demo_appointments
        ADD COLUMN IF NOT EXISTS confirmed_time TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS slot_label     VARCHAR(100)
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE demo_appointments DROP COLUMN IF EXISTS confirmed_time")
    op.execute("ALTER TABLE demo_appointments DROP COLUMN IF EXISTS slot_label")
