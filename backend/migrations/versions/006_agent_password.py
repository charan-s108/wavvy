"""Add password_hash to agent_profiles

Revision ID: 006
Revises: 005
Create Date: 2026-05-25

Changes:
  - password_hash VARCHAR(255) nullable: bcrypt hash of the agent's login password
    NULL = agent not yet given a password (legacy seed rows)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_profiles", sa.Column("password_hash", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_profiles", "password_hash")
