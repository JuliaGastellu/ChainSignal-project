"""Identidad, organizaciones y recursos privados por organización (E02).

Agrego organizaciones, usuarios, membresías con rol, invitaciones de un solo
uso, sesiones, cuentas observadas, políticas de alerta y eventos por
organización. Las políticas referencian cuentas con una clave foránea compuesta
(account_id, organization_id) para que la base impida cruzar organizaciones.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

CHECK_ROL = "role IN ('owner', 'operator', 'viewer')"


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("disabled_at", sa.Float(), nullable=True),
    )
    op.create_table(
        "memberships",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("organization_id", sa.String(32), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_memberships_org_user"),
        sa.CheckConstraint(CHECK_ROL, name="ck_memberships_role"),
    )
    op.create_table(
        "invitations",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("organization_id", sa.String(32), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("invited_by_user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("accepted_at", sa.Float(), nullable=True),
        sa.Column("accepted_by_user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("revoked_at", sa.Float(), nullable=True),
        sa.CheckConstraint(CHECK_ROL, name="ck_invitations_role"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("revoked_at", sa.Float(), nullable=True),
        sa.Column("last_seen_at", sa.Float(), nullable=True),
    )
    op.create_table(
        "monitored_accounts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("organization_id", sa.String(32), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("address", sa.String(42), nullable=False),
        sa.Column("label", sa.String(200), nullable=True),
        sa.Column("priority", sa.String(8), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("last_evaluation_at", sa.Float(), nullable=True),
        sa.Column("last_risk_score", sa.Integer(), nullable=True),
        sa.Column("last_decision", sa.String(32), nullable=True),
        sa.UniqueConstraint("organization_id", "chain_id", "address", name="uq_accounts_org_chain_address"),
        sa.UniqueConstraint("id", "organization_id", name="uq_accounts_id_org"),
        sa.CheckConstraint("priority IN ('high', 'medium', 'low')", name="ck_accounts_priority"),
    )
    op.create_table(
        "alert_policies",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("organization_id", sa.String(32), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("account_id", sa.String(32), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("rule", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by_user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id", "organization_id"],
            ["monitored_accounts.id", "monitored_accounts.organization_id"],
            name="fk_policies_account_same_org",
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "org_events",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.String(32), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("actor_user_id", sa.String(32), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=False),
    )
    op.create_index("ix_org_events_org_id_id", "org_events", ["organization_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_org_events_org_id_id", table_name="org_events")
    for tabla in ("org_events", "alert_policies", "monitored_accounts", "sessions", "invitations", "memberships", "users", "organizations"):
        op.drop_table(tabla)
