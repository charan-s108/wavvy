"""Initial schema — all tables and indexes

Revision ID: 001
Revises:
Create Date: 2026-05-16
"""
from typing import Sequence, Union

from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    op.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name          VARCHAR(255) NOT NULL,
            phone         VARCHAR(20) UNIQUE NOT NULL,
            email         VARCHAR(255),
            account_type  VARCHAR(50) DEFAULT 'standard',
            address       TEXT,
            order_history JSONB DEFAULT '[]',
            notes         TEXT,
            created_at    TIMESTAMPTZ DEFAULT NOW(),
            updated_at    TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_profiles (
            id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name       VARCHAR(255) NOT NULL,
            email      VARCHAR(255) UNIQUE NOT NULL,
            team       VARCHAR(100),
            status     VARCHAR(20) DEFAULT 'offline',
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS calls (
            id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            customer_id       UUID REFERENCES customers(id),
            agent_id          UUID REFERENCES agent_profiles(id),
            started_at        TIMESTAMPTZ DEFAULT NOW(),
            ended_at          TIMESTAMPTZ,
            duration_secs     INTEGER,
            call_type         VARCHAR(20),
            resolution        VARCHAR(20),
            escalated         BOOLEAN DEFAULT FALSE,
            escalation_reason VARCHAR(100),
            escalation_at     TIMESTAMPTZ,
            voice_ai_summary  TEXT,
            acw_summary       TEXT,
            crm_updated       BOOLEAN DEFAULT FALSE,
            status            VARCHAR(20) DEFAULT 'active'
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS transcripts (
            id        UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            call_id   UUID REFERENCES calls(id) ON DELETE CASCADE,
            speaker   VARCHAR(20),
            content   TEXT NOT NULL,
            sentiment FLOAT,
            timestamp TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS eval_scores (
            id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            call_id              UUID REFERENCES calls(id) ON DELETE CASCADE,
            agent_id             UUID REFERENCES agent_profiles(id),
            guardrail_adherence  INTEGER,
            resolution_rate      INTEGER,
            containment          INTEGER,
            caller_satisfaction  FLOAT,
            handle_time_score    INTEGER,
            disclosure_score     INTEGER,
            overall_score        INTEGER,
            pass_fail            VARCHAR(4),
            violations           JSONB DEFAULT '[]',
            coaching_note        TEXT,
            strengths            JSONB DEFAULT '[]',
            created_at           TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS kb_documents (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            filename    VARCHAR(255) NOT NULL,
            file_type   VARCHAR(10),
            category    VARCHAR(100) DEFAULT 'general',
            chunk_count INTEGER DEFAULT 0,
            status      VARCHAR(20) DEFAULT 'processing',
            uploaded_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS coaching_packs (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            agent_id        UUID REFERENCES agent_profiles(id),
            generated_at    TIMESTAMPTZ DEFAULT NOW(),
            calls_analyzed  INTEGER DEFAULT 0,
            overall_trend   VARCHAR(20),
            strengths       JSONB DEFAULT '[]',
            improvements    JSONB DEFAULT '[]',
            action_items    JSONB DEFAULT '[]',
            score_summary   JSONB DEFAULT '{}'
        )
    """)

    # Indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_calls_customer ON calls(customer_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_calls_agent ON calls(agent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_calls_status ON calls(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_transcripts_call ON transcripts(call_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_eval_scores_call ON eval_scores(call_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_eval_scores_agent ON eval_scores(agent_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS coaching_packs CASCADE")
    op.execute("DROP TABLE IF EXISTS kb_documents CASCADE")
    op.execute("DROP TABLE IF EXISTS eval_scores CASCADE")
    op.execute("DROP TABLE IF EXISTS transcripts CASCADE")
    op.execute("DROP TABLE IF EXISTS calls CASCADE")
    op.execute("DROP TABLE IF EXISTS agent_profiles CASCADE")
    op.execute("DROP TABLE IF EXISTS customers CASCADE")
