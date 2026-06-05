"""Add customer_rating, customer_feedback, feedback_submitted_at to calls

Revision ID: 005
Revises: 004
Create Date: 2026-05-24

Changes:
  - customer_rating INTEGER CHECK (1–5): optional post-call star rating from visitor
  - customer_feedback TEXT: optional freeform comment, max 1000 chars enforced in app layer
  - feedback_submitted_at TIMESTAMPTZ: when feedback was submitted (NULL = not submitted)

Existing rows migrate cleanly: all three columns are nullable with no default.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("calls", sa.Column("customer_rating", sa.Integer(), nullable=True))
    op.add_column("calls", sa.Column("customer_feedback", sa.Text(), nullable=True))
    op.add_column("calls", sa.Column("feedback_submitted_at", sa.DateTime(timezone=True), nullable=True))

    op.create_check_constraint(
        "ck_calls_customer_rating_range",
        "calls",
        "customer_rating IS NULL OR (customer_rating >= 1 AND customer_rating <= 5)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_calls_customer_rating_range", "calls", type_="check")
    op.drop_column("calls", "feedback_submitted_at")
    op.drop_column("calls", "customer_feedback")
    op.drop_column("calls", "customer_rating")
