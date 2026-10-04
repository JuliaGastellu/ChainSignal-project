"""Latido de workers para liveness y métricas operativas (E08).

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.String(64), primary_key=True),
        sa.Column("hostname", sa.String(100), nullable=False),
        sa.Column("started_at", sa.Float(), nullable=False),
        sa.Column("last_seen_at", sa.Float(), nullable=False),
        sa.Column("last_step", sa.JSON(), nullable=False),
        sa.Column("last_error", sa.String(100), nullable=True),
    )
    op.create_index("ix_worker_heartbeats_hostname", "worker_heartbeats", ["hostname"])
    op.create_index("ix_worker_heartbeats_last_seen_at", "worker_heartbeats", ["last_seen_at"])


def downgrade() -> None:
    op.drop_index("ix_worker_heartbeats_last_seen_at", table_name="worker_heartbeats")
    op.drop_index("ix_worker_heartbeats_hostname", table_name="worker_heartbeats")
    op.drop_table("worker_heartbeats")
