"""Snapshots de posiciones de protocolos a bloque explícito (E04).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "position_snapshots",
        sa.Column("id", _ID, primary_key=True, autoincrement=True),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("protocol", sa.String(32), nullable=False),
        sa.Column("market", sa.String(64), nullable=False),
        sa.Column("user_address", sa.String(42), nullable=False),
        sa.Column("block_number", sa.BigInteger(), nullable=False),
        sa.Column("block_hash", sa.String(66), nullable=False),
        sa.Column("block_timestamp", sa.BigInteger(), nullable=False),
        sa.Column("quality", sa.String(16), nullable=False),
        sa.Column("quality_reason", sa.String(32), nullable=False),
        sa.Column("quality_detail", sa.String(300), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("total_collateral_base", sa.String(80), nullable=False),
        sa.Column("total_debt_base", sa.String(80), nullable=False),
        sa.Column("available_borrows_base", sa.String(80), nullable=False),
        sa.Column("current_liquidation_threshold_bps", sa.Integer(), nullable=False),
        sa.Column("ltv_bps", sa.Integer(), nullable=False),
        sa.Column("health_factor_wad", sa.String(80), nullable=False),
        sa.Column("base_currency_unit", sa.String(80), nullable=False),
        sa.Column("base_currency", sa.String(42), nullable=False),
        sa.Column("emode_category", sa.Integer(), nullable=False),
        sa.Column("contracts", sa.JSON(), nullable=False),
        sa.Column("reconciliation", sa.JSON(), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("unread_reserves", sa.JSON(), nullable=False),
        sa.Column("read_at", sa.Float(), nullable=False),
        sa.UniqueConstraint("chain_id", "protocol", "market", "user_address", "block_number", name="uq_snapshot_posicion_bloque"),
    )
    op.create_index("ix_snapshots_usuario", "position_snapshots", ["chain_id", "user_address", "block_number"])
    op.create_table(
        "position_snapshot_assets",
        sa.Column("id", _ID, primary_key=True, autoincrement=True),
        sa.Column("snapshot_id", _ID, sa.ForeignKey("position_snapshots.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("asset", sa.String(42), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("decimals", sa.Integer(), nullable=False),
        sa.Column("a_token_balance", sa.String(80), nullable=False),
        sa.Column("stable_debt", sa.String(80), nullable=False),
        sa.Column("variable_debt", sa.String(80), nullable=False),
        sa.Column("used_as_collateral", sa.Boolean(), nullable=False),
        sa.Column("price_base", sa.String(80), nullable=False),
        sa.Column("oracle_source", sa.String(42), nullable=False),
        sa.Column("ltv_bps", sa.Integer(), nullable=False),
        sa.Column("liquidation_threshold_bps", sa.Integer(), nullable=False),
        sa.UniqueConstraint("snapshot_id", "asset", name="uq_snapshot_activo"),
    )


def downgrade() -> None:
    op.drop_table("position_snapshot_assets")
    op.drop_index("ix_snapshots_usuario", table_name="position_snapshots")
    op.drop_table("position_snapshots")
