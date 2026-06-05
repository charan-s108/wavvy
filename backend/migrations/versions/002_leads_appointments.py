"""Add leads and demo_appointments tables

Revision ID: 002
Revises: 001
Create Date: 2026-05-19
"""
from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            call_id        UUID REFERENCES calls(id) ON DELETE SET NULL,
            name           VARCHAR(255),
            email          VARCHAR(255),
            phone          VARCHAR(50),
            company        VARCHAR(255),
            intent         VARCHAR(100),
            interest_notes TEXT,
            status         VARCHAR(20) DEFAULT 'new',
            created_at     TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_leads_call  ON leads(call_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS demo_appointments (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            lead_id         UUID REFERENCES leads(id) ON DELETE CASCADE,
            call_id         UUID REFERENCES calls(id) ON DELETE SET NULL,
            requested_time  VARCHAR(255),
            status          VARCHAR(20) DEFAULT 'pending',
            created_at      TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_appointments_lead ON demo_appointments(lead_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS demo_appointments")
    op.execute("DROP TABLE IF EXISTS leads")
