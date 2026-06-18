"""Add role column to agent_profiles

Revision ID: 011
Revises: 010
Create Date: 2026-06-07
"""
from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_profiles",
        sa.Column("role", sa.String(20), nullable=False, server_default="agent"),
    )
    # Seed known admins immediately
    op.execute("""
        UPDATE agent_profiles
        SET role = 'admin'
        WHERE email IN ('david@fin.ai')
    """)


def downgrade() -> None:
    op.drop_column("agent_profiles", "role")
