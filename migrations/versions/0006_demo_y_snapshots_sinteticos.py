"""Demo aislada y snapshots sintéticos separados de las lecturas reales (E06).

- organizations.is_demo / expires_at: la demo es una organización propia, con
  vencimiento, que el worker no programa.
- position_snapshots.is_synthetic: un snapshot sintético de la demo nunca se
  sirve como lectura real de la misma dirección; entra en la unicidad.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("organizations") as tabla:
        tabla.add_column(sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()))
        tabla.add_column(sa.Column("expires_at", sa.Float(), nullable=True))
    with op.batch_alter_table("position_snapshots") as tabla:
        tabla.add_column(sa.Column("is_synthetic", sa.Boolean(), nullable=False, server_default=sa.false()))
        tabla.drop_constraint("uq_snapshot_posicion_bloque_hash", type_="unique")
        tabla.create_unique_constraint("uq_snapshot_posicion_bloque_hash",
                                       ["chain_id", "protocol", "market", "user_address", "block_number", "block_hash", "is_synthetic"])


def downgrade() -> None:
    with op.batch_alter_table("position_snapshots") as tabla:
        tabla.drop_constraint("uq_snapshot_posicion_bloque_hash", type_="unique")
        tabla.create_unique_constraint("uq_snapshot_posicion_bloque_hash",
                                       ["chain_id", "protocol", "market", "user_address", "block_number", "block_hash"])
        tabla.drop_column("is_synthetic")
    with op.batch_alter_table("organizations") as tabla:
        tabla.drop_column("expires_at")
        tabla.drop_column("is_demo")
