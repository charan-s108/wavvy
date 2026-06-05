"""Fintech schema redesign — normalized tables, drop JSONB hacks

Revision ID: 009
Revises: 008
Create Date: 2026-05-28

Changes:
  - DROP leads, demo_appointments (Wavvy SaaS tables not used by Fin)
  - ADD 10 account-state columns to customers
  - DROP order_history, notes, address from customers
  - CREATE transactions, refunds, disputes, fraud_cases, incidents, resolutions, account_holds
  - CREATE 5 reference-number sequences
  - Migrate JSONB order_history to transactions rows
"""
from typing import Sequence, Union

from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop Wavvy SaaS tables
    op.execute("DROP TABLE IF EXISTS demo_appointments CASCADE")

    # 2.
    op.execute("DROP TABLE IF EXISTS leads CASCADE")

    # 3. Add fintech account-state columns to customers
    op.execute("""
        ALTER TABLE customers
        ADD COLUMN IF NOT EXISTS account_status VARCHAR(20) NOT NULL DEFAULT 'active'
    """)

    op.execute("""
        ALTER TABLE customers
        ADD COLUMN IF NOT EXISTS account_locked_at TIMESTAMPTZ
    """)

    op.execute("""
        ALTER TABLE customers
        ADD COLUMN IF NOT EXISTS account_locked_reason TEXT
    """)

    op.execute("""
        ALTER TABLE customers
        ADD COLUMN IF NOT EXISTS fraud_hold_active BOOLEAN NOT NULL DEFAULT FALSE
    """)

    op.execute("""
        ALTER TABLE customers
        ADD COLUMN IF NOT EXISTS fraud_hold_placed_at TIMESTAMPTZ
    """)

    op.execute("""
        ALTER TABLE customers
        ADD COLUMN IF NOT EXISTS kyc_status VARCHAR(20) NOT NULL DEFAULT 'pending'
    """)

    op.execute("""
        ALTER TABLE customers
        ADD COLUMN IF NOT EXISTS kyc_verified_at TIMESTAMPTZ
    """)

    op.execute("""
        ALTER TABLE customers
        ADD COLUMN IF NOT EXISTS two_fa_last_reset_at TIMESTAMPTZ
    """)

    op.execute("""
        ALTER TABLE customers
        ADD COLUMN IF NOT EXISTS fraud_team_escalated BOOLEAN NOT NULL DEFAULT FALSE
    """)

    op.execute("""
        ALTER TABLE customers
        ADD COLUMN IF NOT EXISTS fraud_team_escalated_at TIMESTAMPTZ
    """)

    # 4. Create transactions table
    op.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id           UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
            txn_number   TEXT         NOT NULL UNIQUE,
            customer_id  UUID         NOT NULL REFERENCES customers(id),
            amount       NUMERIC(12,2) NOT NULL,
            currency     VARCHAR(3)   NOT NULL DEFAULT 'INR',
            merchant     TEXT         NOT NULL,
            txn_type     VARCHAR(20),
            status       VARCHAR(30),
            gateway_ref  TEXT,
            txn_date     DATE         NOT NULL,
            created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_transactions_customer_id
            ON transactions(customer_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_transactions_txn_number
            ON transactions(txn_number)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_transactions_status
            ON transactions(status)
    """)

    # 5. Create refunds table
    op.execute("""
        CREATE TABLE IF NOT EXISTS refunds (
            id             UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
            rfn_number     TEXT         NOT NULL UNIQUE,
            transaction_id UUID         NOT NULL REFERENCES transactions(id),
            customer_id    UUID         NOT NULL REFERENCES customers(id),
            amount         NUMERIC(12,2) NOT NULL,
            reason         TEXT,
            status         VARCHAR(20)  NOT NULL DEFAULT 'initiated',
            initiated_by   TEXT,
            call_id        TEXT,
            initiated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            completed_at   TIMESTAMPTZ,
            created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_refunds_transaction_id
            ON refunds(transaction_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_refunds_customer_id
            ON refunds(customer_id)
    """)

    # 6. Create disputes table
    op.execute("""
        CREATE TABLE IF NOT EXISTS disputes (
            id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
            dsp_number      TEXT        NOT NULL UNIQUE,
            transaction_id  UUID        NOT NULL REFERENCES transactions(id),
            customer_id     UUID        NOT NULL REFERENCES customers(id),
            reason          TEXT        NOT NULL,
            status          VARCHAR(20) NOT NULL DEFAULT 'open',
            filed_via       TEXT,
            call_id         TEXT,
            opened_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            resolved_at     TIMESTAMPTZ,
            resolution_note TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_disputes_transaction_id
            ON disputes(transaction_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_disputes_customer_id
            ON disputes(customer_id)
    """)

    # 7. Create fraud_cases table
    op.execute("""
        CREATE TABLE IF NOT EXISTS fraud_cases (
            id             UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
            fraud_number   TEXT        NOT NULL UNIQUE,
            transaction_id UUID        REFERENCES transactions(id),
            customer_id    UUID        NOT NULL REFERENCES customers(id),
            fraud_type     VARCHAR(50),
            status         VARCHAR(20) NOT NULL DEFAULT 'under_review',
            risk_level     VARCHAR(10) NOT NULL DEFAULT 'medium',
            reported_via   TEXT,
            call_id        TEXT,
            hold_placed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            cleared_at     TIMESTAMPTZ,
            cleared_by     TEXT,
            notes          TEXT,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_fraud_cases_customer_id
            ON fraud_cases(customer_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_fraud_cases_transaction_id
            ON fraud_cases(transaction_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_fraud_cases_status
            ON fraud_cases(status)
    """)

    # 8. Create incidents table
    op.execute("""
        CREATE TABLE IF NOT EXISTS incidents (
            id             UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
            inc_number     TEXT        NOT NULL UNIQUE,
            customer_id    UUID        NOT NULL REFERENCES customers(id),
            call_id        TEXT,
            inc_type       VARCHAR(50),
            status         VARCHAR(20) NOT NULL DEFAULT 'open',
            priority       VARCHAR(10) NOT NULL DEFAULT 'medium',
            description    TEXT,
            resolution_ref TEXT,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            resolved_at    TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_incidents_customer_id
            ON incidents(customer_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_incidents_call_id
            ON incidents(call_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_incidents_status
            ON incidents(status)
    """)

    # 9. Create resolutions table
    op.execute("""
        CREATE TABLE IF NOT EXISTS resolutions (
            id           UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
            res_number   TEXT        NOT NULL UNIQUE,
            call_id      TEXT        NOT NULL,
            customer_id  UUID        NOT NULL REFERENCES customers(id),
            incident_id  UUID        REFERENCES incidents(id),
            agent_id     UUID        REFERENCES agent_profiles(id),
            action_taken TEXT        NOT NULL,
            action_types TEXT[]      NOT NULL DEFAULT '{}',
            resolved_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_resolutions_customer_id
            ON resolutions(customer_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_resolutions_call_id
            ON resolutions(call_id)
    """)

    # 10. Create account_holds table
    op.execute("""
        CREATE TABLE IF NOT EXISTS account_holds (
            id          UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
            customer_id UUID        NOT NULL REFERENCES customers(id),
            hold_type   VARCHAR(20) NOT NULL,
            status      VARCHAR(10) NOT NULL DEFAULT 'active',
            reason      TEXT,
            placed_by   TEXT,
            placed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            lifted_at   TIMESTAMPTZ,
            lifted_by   TEXT,
            call_id     TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_account_holds_customer_id
            ON account_holds(customer_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_account_holds_status
            ON account_holds(status)
    """)

    # 11-15. Create reference-number sequences
    op.execute("CREATE SEQUENCE IF NOT EXISTS seq_inc_number   START 4413")
    op.execute("CREATE SEQUENCE IF NOT EXISTS seq_res_number   START 523")
    op.execute("CREATE SEQUENCE IF NOT EXISTS seq_rfn_number   START 1")
    op.execute("CREATE SEQUENCE IF NOT EXISTS seq_dsp_number   START 1")
    op.execute("CREATE SEQUENCE IF NOT EXISTS seq_fraud_number START 1")

    # 16. Migrate JSONB order_history → transactions rows
    op.execute("""
        INSERT INTO transactions (customer_id, txn_number, merchant, amount, currency,
                                  txn_type, status, txn_date, created_at, updated_at)
        SELECT
            c.id,
            elem->>'id',
            COALESCE(elem->>'merchant', 'Unknown'),
            COALESCE((elem->>'amount')::NUMERIC, 0),
            'INR',
            elem->>'type',
            elem->>'status',
            COALESCE((elem->>'date')::DATE, CURRENT_DATE),
            NOW(),
            NOW()
        FROM customers c
        CROSS JOIN LATERAL jsonb_array_elements(c.order_history) AS elem
        WHERE c.order_history IS NOT NULL
          AND jsonb_typeof(c.order_history) = 'array'
          AND jsonb_array_length(c.order_history) > 0
          AND elem->>'id' IS NOT NULL
        ON CONFLICT (txn_number) DO NOTHING
    """)

    # 17. Set account-state column defaults from notes text patterns
    op.execute("""
        UPDATE customers
        SET account_status = 'locked',
            account_locked_reason = 'Multiple failed login attempts'
        WHERE LOWER(notes) LIKE '%account locked%'
           OR LOWER(notes) LIKE '%locked after%'
    """)

    op.execute("""
        UPDATE customers
        SET fraud_hold_active = TRUE,
            fraud_hold_placed_at = NOW()
        WHERE LOWER(notes) LIKE '%suspicious transaction flagged%'
           OR LOWER(notes) LIKE '%fraud hold%'
    """)

    op.execute("""
        UPDATE customers
        SET kyc_status = 'rejected'
        WHERE LOWER(notes) LIKE '%kyc verification failed%'
           OR LOWER(notes) LIKE '%document mismatch%'
    """)

    # 18. Drop order_history column
    op.execute("ALTER TABLE customers DROP COLUMN IF EXISTS order_history")

    # 19. Drop notes column
    op.execute("ALTER TABLE customers DROP COLUMN IF EXISTS notes")

    # 20. Drop address column
    op.execute("ALTER TABLE customers DROP COLUMN IF EXISTS address")


def downgrade() -> None:
    raise Exception(
        "Migration 009 is a one-way fintech schema redesign. "
        "Downgrade is not supported — restore from backup if needed."
    )
