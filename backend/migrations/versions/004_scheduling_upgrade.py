"""Scheduling upgrade: slot_key race prevention, UTC storage, reschedule tracking

Revision ID: 004
Revises: 003
Create Date: 2026-05-20

Changes:
  - slot_key VARCHAR(32): UTC "YYYY-MM-DD-HH" key for 1-hour slot uniqueness
  - UNIQUE index on slot_key WHERE status = 'confirmed' — prevents concurrent booking races
  - user_timezone VARCHAR(50): caller's inferred timezone for display
  - previous_confirmed_time: original slot before reschedule
  - rescheduled_at / reschedule_count: reschedule history
  - status 'rescheduled' added (was only 'confirmed'|'cancelled'|'pending')
  - Indexes for common query patterns
"""
from typing import Sequence, Union
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New columns on demo_appointments
    op.execute("""
        ALTER TABLE demo_appointments
        ADD COLUMN IF NOT EXISTS slot_key              VARCHAR(32),
        ADD COLUMN IF NOT EXISTS user_timezone         VARCHAR(50) DEFAULT 'Asia/Kolkata',
        ADD COLUMN IF NOT EXISTS previous_confirmed_time TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS rescheduled_at        TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS reschedule_count      INTEGER DEFAULT 0
    """)

    # Backfill slot_key from existing confirmed_time rows (UTC hour bucket)
    op.execute("""
        UPDATE demo_appointments
        SET slot_key = TO_CHAR(confirmed_time AT TIME ZONE 'UTC', 'YYYY-MM-DD-HH24')
        WHERE confirmed_time IS NOT NULL
          AND slot_key IS NULL
    """)

    # UNIQUE index on slot_key for confirmed appointments only.
    # Partial index: cancelled/rescheduled rows don't block the slot.
    # This is the primary race-condition guard — DB enforces uniqueness even under
    # concurrent inserts that both passed the pre-check query.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_confirmed_slot
        ON demo_appointments(slot_key)
        WHERE status = 'confirmed'
    """)

    # Supporting indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_appointments_call   ON demo_appointments(call_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_appointments_status ON demo_appointments(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_appointments_time   ON demo_appointments(confirmed_time)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uniq_confirmed_slot")
    op.execute("DROP INDEX IF EXISTS idx_appointments_call")
    op.execute("DROP INDEX IF EXISTS idx_appointments_status")
    op.execute("DROP INDEX IF EXISTS idx_appointments_time")
    op.execute("""
        ALTER TABLE demo_appointments
        DROP COLUMN IF EXISTS slot_key,
        DROP COLUMN IF EXISTS user_timezone,
        DROP COLUMN IF EXISTS previous_confirmed_time,
        DROP COLUMN IF EXISTS rescheduled_at,
        DROP COLUMN IF EXISTS reschedule_count
    """)
