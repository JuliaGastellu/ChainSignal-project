"""Piloto comercial: suscripciones, pagos confirmados, webhooks, eventos de producto y contacto (E09).

Las organizaciones reales existentes reciben una prueba de 14 días desde la
migración; las demo no tienen suscripción (su servicio es sintético y vence solo).

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-04
"""
import time

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

PRUEBA_SEGUNDOS = 14 * 86400


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("organization_id", sa.String(32), sa.ForeignKey("organizations.id"), primary_key=True),
        sa.Column("plan", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("trial_ends_at", sa.Float(), nullable=True),
        sa.Column("current_period_end", sa.Float(), nullable=True),
        sa.Column("grace_ends_at", sa.Float(), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("canceled_at", sa.Float(), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
    )
    op.create_table(
        "payment_records",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.String(32), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("reference", sa.String(100), nullable=False),
        sa.Column("amount_usd", sa.String(20), nullable=False),
        sa.Column("period_start", sa.Float(), nullable=False),
        sa.Column("period_end", sa.Float(), nullable=False),
        sa.Column("confirmed_by", sa.String(100), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.UniqueConstraint("source", "reference", name="uq_payment_source_reference"),
    )
    op.create_index("ix_payment_records_organization_id", "payment_records", ["organization_id"])
    op.create_table(
        "billing_events",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("event_id", sa.String(100), nullable=False),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("organization_id", sa.String(32), nullable=True),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("received_at", sa.Float(), nullable=False),
        sa.UniqueConstraint("provider", "event_id", name="uq_billing_event"),
    )
    op.create_index("ix_billing_events_organization_id", "billing_events", ["organization_id"])
    op.create_table(
        "product_events",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.String(32), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("properties", sa.JSON(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("occurred_at", sa.Float(), nullable=False),
        sa.Column("once_key", sa.String(80), nullable=True),
        sa.UniqueConstraint("once_key", name="uq_product_events_once_key"),
    )
    op.create_index("ix_product_events_organization_id", "product_events", ["organization_id"])
    op.create_index("ix_product_events_name", "product_events", ["name"])
    op.create_index("ix_product_events_occurred_at", "product_events", ["occurred_at"])
    op.create_table(
        "contact_requests",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("organization", sa.String(200), nullable=True),
        sa.Column("message", sa.String(2000), nullable=False),
        sa.Column("consent", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("handled_at", sa.Float(), nullable=True),
    )
    op.create_index("ix_contact_requests_created_at", "contact_requests", ["created_at"])

    # Las organizaciones reales que ya existían empiezan una prueba de 14 días.
    ahora = time.time()
    op.execute(sa.text(
        "INSERT INTO subscriptions (organization_id, plan, status, trial_ends_at, cancel_at_period_end, created_at, updated_at) "
        "SELECT id, 'pilot', 'trialing', :fin, :falso, :ahora, :ahora FROM organizations WHERE is_demo = :falso"
    ).bindparams(fin=ahora + PRUEBA_SEGUNDOS, ahora=ahora, falso=False))


def downgrade() -> None:
    op.drop_index("ix_contact_requests_created_at", table_name="contact_requests")
    op.drop_table("contact_requests")
    op.drop_index("ix_product_events_occurred_at", table_name="product_events")
    op.drop_index("ix_product_events_name", table_name="product_events")
    op.drop_index("ix_product_events_organization_id", table_name="product_events")
    op.drop_table("product_events")
    op.drop_index("ix_billing_events_organization_id", table_name="billing_events")
    op.drop_table("billing_events")
    op.drop_index("ix_payment_records_organization_id", table_name="payment_records")
    op.drop_table("payment_records")
    op.drop_table("subscriptions")
