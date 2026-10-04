"""Ingesta con checkpoints, historial on-chain y calidad de la última evaluación (E03).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "chain_transactions",
        sa.Column("id", _ID, primary_key=True, autoincrement=True),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("address", sa.String(42), nullable=False),
        sa.Column("stream", sa.String(16), nullable=False),
        sa.Column("block_number", sa.BigInteger(), nullable=False),
        sa.Column("block_hash", sa.String(66), nullable=True),
        sa.Column("tx_hash", sa.String(66), nullable=False),
        sa.Column("timestamp", sa.BigInteger(), nullable=False),
        sa.Column("from_addr", sa.String(42), nullable=False),
        sa.Column("to_addr", sa.String(42), nullable=False),
        sa.Column("value_raw", sa.String(80), nullable=False),
        sa.Column("gas_used", sa.BigInteger(), nullable=True),
        sa.Column("is_error", sa.Boolean(), nullable=False),
        sa.Column("is_contract_call", sa.Boolean(), nullable=False),
        sa.Column("token_contract", sa.String(42), nullable=True),
        sa.Column("token_decimals", sa.Integer(), nullable=True),
        sa.Column("token_symbol", sa.String(32), nullable=True),
    )
    op.create_index("ix_chain_tx_cuenta_bloque", "chain_transactions", ["chain_id", "address", "stream", "block_number"])
    op.create_table(
        "ingestion_checkpoints",
        sa.Column("id", _ID, primary_key=True, autoincrement=True),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("address", sa.String(42), nullable=False),
        sa.Column("stream", sa.String(16), nullable=False),
        sa.Column("covered_from_block", sa.BigInteger(), nullable=True),
        sa.Column("confirmed_block", sa.BigInteger(), nullable=True),
        sa.Column("confirmed_block_hash", sa.String(66), nullable=True),
        sa.Column("complete_history", sa.Boolean(), nullable=False),
        sa.Column("reference_block", sa.BigInteger(), nullable=True),
        sa.Column("reference_block_hash", sa.String(66), nullable=True),
        sa.Column("reference_block_timestamp", sa.BigInteger(), nullable=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("synced_at", sa.Float(), nullable=True),
        sa.Column("pages", sa.Integer(), nullable=False),
        sa.UniqueConstraint("chain_id", "address", "stream", name="uq_checkpoint_cuenta_flujo"),
    )
    with op.batch_alter_table("monitored_accounts") as tabla:
        tabla.add_column(sa.Column("last_data_quality", sa.String(16), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("monitored_accounts") as tabla:
        tabla.drop_column("last_data_quality")
    op.drop_table("ingestion_checkpoints")
    op.drop_index("ix_chain_tx_cuenta_bloque", table_name="chain_transactions")
    op.drop_table("chain_transactions")
