"""workflow_definitions table — configurable node-graph workflows

Revision ID: 010
Revises: 009
Create Date: 2026-06-07

Changes:
  - CREATE workflow_definitions table (JSONB node graph, intent embedding, tenant scoped)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str   = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    op.create_table(
        "workflow_definitions",
        sa.Column("id",                sa.UUID(),           nullable=False,
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("tenant_id",         sa.String(100),      nullable=False),
        sa.Column("name",              sa.String(255),      nullable=False),
        sa.Column("description",       sa.Text(),           nullable=True),
        sa.Column("intent_definition", sa.Text(),           nullable=True),
        sa.Column("few_shot_examples", sa.JSON(),           nullable=False,
                  server_default="[]"),
        # float array stored as JSON; NULL until first PUT (embedding computed)
        sa.Column("intent_embedding",  sa.JSON(),           nullable=True),
        sa.Column("intent_threshold",  sa.Float(),          nullable=False,
                  server_default="0.72"),
        # The full node graph — serialized WorkflowDefinition dict
        sa.Column("definition",        sa.JSON(),           nullable=False,
                  server_default="{}"),
        sa.Column("is_active",         sa.Boolean(),        nullable=False,
                  server_default="true"),
        sa.Column("version",           sa.Integer(),        nullable=False,
                  server_default="1"),
        sa.Column("created_at",        sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at",        sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )

    op.create_index(
        "idx_wf_tenant_active",
        "workflow_definitions",
        ["tenant_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("idx_wf_tenant_active", table_name="workflow_definitions")
    op.drop_table("workflow_definitions")
