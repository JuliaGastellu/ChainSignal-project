"""Línea base del estado heredado (planes, historial y presupuestos).

Antes de Alembic estas tablas las creaba metadata.create_all. Las creo solo si
faltan, así la migración corre igual sobre una base nueva y sobre una base que
ya tenía las tablas de create_all, sin pasos manuales de stamp.

Revision ID: 0001
Revises:
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _crear_si_falta(nombre, *columnas, **kwargs):
    if not sa.inspect(op.get_bind()).has_table(nombre):
        op.create_table(nombre, *columnas, **kwargs)


def upgrade() -> None:
    _crear_si_falta(
        "execution_plans",
        sa.Column("fingerprint", sa.String(), primary_key=True),
        sa.Column("wallet", sa.String(), nullable=False, index=True),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("block_number", sa.Integer(), nullable=False),
        sa.Column("lifecycle", sa.String(), nullable=False, index=True),
        sa.Column("actions", sa.JSON(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("recovery", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
    )
    _crear_si_falta(
        "execution_plan_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("fingerprint", sa.String(), nullable=False, index=True),
        sa.Column("timestamp", sa.Float(), nullable=False),
        sa.Column("event", sa.String(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=True),
    )
    _crear_si_falta(
        "executions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("timestamp", sa.String(), nullable=False),
        sa.Column("cycle", sa.Integer(), nullable=False, index=True),
        sa.Column("wallet", sa.String(), nullable=False, index=True),
        sa.Column("decision", sa.String(), nullable=True),
        sa.Column("threat_score", sa.Float(), nullable=True),
        sa.Column("action_type", sa.String(), nullable=True),
        sa.Column("tx_hash", sa.String(), nullable=True),
        sa.Column("contract_address", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error", sa.String(), nullable=True),
    )
    _crear_si_falta(
        "agent_budgets",
        sa.Column("wallet", sa.String(), primary_key=True),
        sa.Column("agent_wallet", sa.String(), nullable=True),
        sa.Column("balance_eth", sa.Float(), nullable=False),
        sa.Column("spent_eth", sa.Float(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.Float(), nullable=True),
        sa.Column("last_funding_tx", sa.String(), nullable=True),
        sa.Column("last_funding_amount_eth", sa.Float(), nullable=False),
    )
    _crear_si_falta(
        "budget_consumptions",
        sa.Column("fingerprint", sa.String(), primary_key=True),
        sa.Column("wallet", sa.String(), nullable=False, index=True),
        sa.Column("amount_eth", sa.Float(), nullable=False),
        sa.Column("timestamp", sa.Float(), nullable=False),
    )
    _crear_si_falta(
        "processed_funding_txs",
        sa.Column("tx_hash", sa.String(), primary_key=True),
        sa.Column("wallet", sa.String(), nullable=False, index=True),
        sa.Column("funded_eth", sa.Float(), nullable=False),
        sa.Column("timestamp", sa.Float(), nullable=False),
    )


def downgrade() -> None:
    # No borro estado heredado al bajar de versión: puede tener datos reales.
    pass
