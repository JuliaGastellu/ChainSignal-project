"""Jobs durables, reglas versionadas, incidentes con evidencia inmutable, alertas y outbox (E05).

- jobs: cola con available_at, attempts y lease; un índice único parcial impide
  dos jobs activos con la misma clave.
- alert_policy_versions: cada cambio de regla crea una versión inmutable; copio
  las reglas existentes como versión 1.
- incidents: un índice único parcial impide dos episodios abiertos para la misma
  política y cuenta.
- incident_evidence: en PostgreSQL un trigger rechaza UPDATE y DELETE; las
  correcciones son filas nuevas que apuntan a la corregida.
- position_snapshots: la unicidad ahora incluye block_hash (tras un reorg, el
  mismo número de bloque es otro bloque).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
_ACTIVOS = sa.text("status IN ('pending', 'running')")
_ABIERTOS = sa.text("status IN ('open', 'acknowledged')")


def upgrade() -> None:
    with op.batch_alter_table("alert_policies") as tabla:
        tabla.add_column(sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"))
        tabla.create_unique_constraint("uq_policies_id_org", ["id", "organization_id"])
    with op.batch_alter_table("monitored_accounts") as tabla:
        tabla.add_column(sa.Column("last_fresh_at", sa.Float(), nullable=True))
    with op.batch_alter_table("position_snapshots") as tabla:
        tabla.drop_constraint("uq_snapshot_posicion_bloque", type_="unique")
        tabla.create_unique_constraint("uq_snapshot_posicion_bloque_hash",
                                       ["chain_id", "protocol", "market", "user_address", "block_number", "block_hash"])

    op.create_table(
        "alert_policy_versions",
        sa.Column("id", _ID, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.String(32), nullable=False, index=True),
        sa.Column("policy_id", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("rule", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("created_by_user_id", sa.String(32), nullable=True),
        sa.UniqueConstraint("policy_id", "version", name="uq_policy_version"),
        sa.ForeignKeyConstraint(["policy_id", "organization_id"], ["alert_policies.id", "alert_policies.organization_id"],
                                name="fk_policy_versions_same_org", ondelete="CASCADE"),
    )
    op.execute(sa.text(
        "INSERT INTO alert_policy_versions (organization_id, policy_id, version, rule, created_at, created_by_user_id) "
        "SELECT organization_id, id, 1, rule, created_at, created_by_user_id FROM alert_policies"
    ))
    op.create_table(
        "policy_account_states",
        sa.Column("id", _ID, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.String(32), nullable=False, index=True),
        sa.Column("policy_id", sa.String(32), nullable=False),
        sa.Column("account_id", sa.String(32), nullable=False),
        sa.Column("baseline_debt_base", sa.String(80), nullable=True),
        sa.Column("baseline_block", sa.BigInteger(), nullable=True),
        sa.Column("consecutive_clear", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.UniqueConstraint("policy_id", "account_id", name="uq_policy_account_state"),
    )
    op.create_table(
        "jobs",
        sa.Column("id", _ID, primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("organization_id", sa.String(32), nullable=False),
        sa.Column("account_id", sa.String(32), nullable=True),
        sa.Column("dedupe_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("available_at", sa.Float(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(64), nullable=True),
        sa.Column("lease_expires_at", sa.Float(), nullable=True),
        sa.Column("last_error", sa.String(300), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.Column("finished_at", sa.Float(), nullable=True),
    )
    op.create_index("uq_jobs_activo_por_clave", "jobs", ["dedupe_key"], unique=True,
                    postgresql_where=_ACTIVOS, sqlite_where=_ACTIVOS)
    op.create_index("ix_jobs_disponibles", "jobs", ["status", "available_at"])
    op.create_table(
        "incidents",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("organization_id", sa.String(32), nullable=False, index=True),
        sa.Column("account_id", sa.String(32), nullable=False),
        sa.Column("policy_id", sa.String(32), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("rule_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("escalation_level", sa.Integer(), nullable=False),
        sa.Column("data_quality", sa.String(16), nullable=False),
        sa.Column("opened_at", sa.Float(), nullable=False),
        sa.Column("escalated_at", sa.Float(), nullable=True),
        sa.Column("acknowledged_at", sa.Float(), nullable=True),
        sa.Column("acknowledged_by_user_id", sa.String(32), nullable=True),
        sa.Column("resolved_at", sa.Float(), nullable=True),
        sa.Column("resolved_by_user_id", sa.String(32), nullable=True),
        sa.Column("resolution", sa.String(32), nullable=True),
        sa.Column("resolution_note", sa.String(500), nullable=True),
        sa.Column("last_evaluated_at", sa.Float(), nullable=False),
        sa.Column("last_observed", sa.JSON(), nullable=False),
        sa.UniqueConstraint("id", "organization_id", name="uq_incidents_id_org"),
        sa.ForeignKeyConstraint(["account_id", "organization_id"], ["monitored_accounts.id", "monitored_accounts.organization_id"],
                                name="fk_incidents_account_same_org"),
        sa.ForeignKeyConstraint(["policy_id", "organization_id"], ["alert_policies.id", "alert_policies.organization_id"],
                                name="fk_incidents_policy_same_org"),
    )
    op.create_index("uq_incidente_abierto_por_politica_cuenta", "incidents", ["policy_id", "account_id"], unique=True,
                    postgresql_where=_ABIERTOS, sqlite_where=_ABIERTOS)
    op.create_table(
        "incident_evidence",
        sa.Column("id", _ID, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.String(32), nullable=False, index=True),
        sa.Column("incident_id", sa.String(32), nullable=False, index=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("snapshot_id", _ID, sa.ForeignKey("position_snapshots.id"), nullable=True),
        sa.Column("block_number", sa.BigInteger(), nullable=True),
        sa.Column("block_hash", sa.String(66), nullable=True),
        sa.Column("observed", sa.JSON(), nullable=False),
        sa.Column("data_quality", sa.String(16), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("corrects_evidence_id", _ID, sa.ForeignKey("incident_evidence.id"), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("created_by_user_id", sa.String(32), nullable=True),
        sa.ForeignKeyConstraint(["incident_id", "organization_id"], ["incidents.id", "incidents.organization_id"],
                                name="fk_evidence_incident_same_org"),
    )
    op.create_table(
        "alerts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("organization_id", sa.String(32), nullable=False, index=True),
        sa.Column("incident_id", sa.String(32), nullable=False, index=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["incident_id", "organization_id"], ["incidents.id", "incidents.organization_id"],
                                name="fk_alerts_incident_same_org"),
    )
    op.create_table(
        "notification_channels",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("organization_id", sa.String(32), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("verified_at", sa.Float(), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.UniqueConstraint("id", "organization_id", name="uq_channels_id_org"),
        sa.CheckConstraint("kind IN ('sandbox', 'webhook')", name="ck_channels_kind"),
    )
    op.create_table(
        "outbox",
        sa.Column("id", _ID, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.String(32), nullable=False, index=True),
        sa.Column("channel_id", sa.String(32), nullable=False),
        sa.Column("alert_id", sa.String(32), sa.ForeignKey("alerts.id"), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.Float(), nullable=False),
        sa.Column("lease_owner", sa.String(64), nullable=True),
        sa.Column("lease_expires_at", sa.Float(), nullable=True),
        sa.Column("last_error", sa.String(300), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("sent_at", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["channel_id", "organization_id"], ["notification_channels.id", "notification_channels.organization_id"],
                                name="fk_outbox_channel_same_org", ondelete="CASCADE"),
    )
    op.create_index("ix_outbox_disponibles", "outbox", ["status", "available_at"])
    op.create_table(
        "notification_deliveries",
        sa.Column("id", _ID, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.String(32), nullable=False, index=True),
        sa.Column("channel_id", sa.String(32), nullable=False, index=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("delivered_at", sa.Float(), nullable=False),
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE FUNCTION evidencia_inmutable() RETURNS trigger AS $$ BEGIN "
            "RAISE EXCEPTION 'incident_evidence is append-only; add a correction instead'; END; $$ LANGUAGE plpgsql"
        )
        op.execute(
            "CREATE TRIGGER tr_evidencia_inmutable BEFORE UPDATE OR DELETE ON incident_evidence "
            "FOR EACH ROW EXECUTE FUNCTION evidencia_inmutable()"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS tr_evidencia_inmutable ON incident_evidence")
        op.execute("DROP FUNCTION IF EXISTS evidencia_inmutable()")
    for tabla in ("notification_deliveries", "outbox", "notification_channels", "alerts", "incident_evidence"):
        op.drop_table(tabla)
    op.drop_index("uq_incidente_abierto_por_politica_cuenta", table_name="incidents")
    op.drop_table("incidents")
    op.drop_index("ix_jobs_disponibles", table_name="jobs")
    op.drop_index("uq_jobs_activo_por_clave", table_name="jobs")
    for tabla in ("jobs", "policy_account_states", "alert_policy_versions"):
        op.drop_table(tabla)
    with op.batch_alter_table("position_snapshots") as tabla:
        tabla.drop_constraint("uq_snapshot_posicion_bloque_hash", type_="unique")
        tabla.create_unique_constraint("uq_snapshot_posicion_bloque", ["chain_id", "protocol", "market", "user_address", "block_number"])
    with op.batch_alter_table("monitored_accounts") as tabla:
        tabla.drop_column("last_fresh_at")
    with op.batch_alter_table("alert_policies") as tabla:
        tabla.drop_constraint("uq_policies_id_org", type_="unique")
        tabla.drop_column("current_version")

