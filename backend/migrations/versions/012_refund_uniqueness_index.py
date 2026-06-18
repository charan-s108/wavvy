"""Add partial unique index: one active refund per transaction

Revision ID: 012
Revises: 011
Create Date: 2026-06-11

Prevents duplicate active refund records at the database level.
A transaction can have at most one refund row with status in
('initiated', 'processing', 'approved').  Completed, failed, and
cancelled refunds are excluded — they are terminal and a new refund
attempt on the same transaction would require a human review path anyway.

This is a belt-and-suspenders guard: application code in wavvy_tools.py
checks the refunds table before inserting, but this index makes duplicate
creation structurally impossible even if that check is bypassed.
"""
from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Partial unique index: only one active refund per transaction.
    # Terminal statuses (completed, failed, cancelled, rejected) are excluded
    # so historical records don't block re-opening a case if needed.
    op.execute("""
        CREATE UNIQUE INDEX uq_refunds_active_per_transaction
        ON refunds (transaction_id)
        WHERE status IN ('initiated', 'processing', 'approved')
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_refunds_active_per_transaction")
