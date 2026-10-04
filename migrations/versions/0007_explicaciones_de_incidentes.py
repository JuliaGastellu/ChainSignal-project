"""Explicaciones de incidentes con origen, validación y costo (E07).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incident_explanations",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.String(32), nullable=False),
        sa.Column("incident_id", sa.String(32), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("fallback_reason", sa.String(40), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.String(32), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("created_by_user_id", sa.String(32), nullable=True),
        sa.ForeignKeyConstraint(["incident_id", "organization_id"], ["incidents.id", "incidents.organization_id"],
                                name="fk_explanations_incident_same_org"),
    )
    op.create_index("ix_incident_explanations_organization_id", "incident_explanations", ["organization_id"])
    op.create_index("ix_incident_explanations_incident_id", "incident_explanations", ["incident_id"])
    op.create_index("ix_incident_explanations_created_at", "incident_explanations", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_incident_explanations_created_at", table_name="incident_explanations")
    op.drop_index("ix_incident_explanations_incident_id", table_name="incident_explanations")
    op.drop_index("ix_incident_explanations_organization_id", table_name="incident_explanations")
    op.drop_table("incident_explanations")
